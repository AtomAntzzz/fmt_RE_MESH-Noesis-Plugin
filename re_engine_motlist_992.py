"""Bounded Wilds MOTLIST992/MOT932 observed profiles, independent of Noesis."""
import math
import struct

from re_engine_binary import checked_range, read_scalar, read_utf16z, sha256_bytes
from re_engine_motlist_1057 import (
    _motlist_multi_carrier_bones,
    _motlist_animation_decode_value,
    _MOTLIST_ANIMATION_VALUE_WIDTH,
)


# Full observed flags, not a promise that every encoding with the same suffix works.
_FLAGS = {
    'translation': frozenset((
        0x2000F2,0x2200F2,0x2210F2,0x2220F2,0x2230F2,0x2260F2,
        0x2250F2,0x2300F2,0x2310F2,0x2320F2,0x2330F2,0x2360F2,0x2400F2,
        0x2410F2,0x2420F2,0x2430F2,0x2450F2,0x2460F2,0x2470F2,0x2500F2,
        0x2550F2,0x2560F2,0x2570F2,0x2600F2,0x2670F2,0x2700F2,0x2800F2,0x2850F2,
        0x2860F2,0x2870F2,0x4000F2,0x4200F2,0x4230F2,0x4260F2,
        0x4250F2,0x4300F2,0x4320F2,0x4330F2,0x4400F2,0x4420F2,0x4430F2,
        0x4470F2,0x4500F2,0x4550F2,0x4560F2,0x4570F2,0x4600F2,0x4700F2,
        0x4800F2,0x4860F2,0x4870F2)),
    'rotation': frozenset((
        0x220112,0x221112,0x222112,0x223112,0x230112,0x240112,
        0x241112,0x242112,0x243112,0x250112,0x260112,0x270112,
        0x280112,0x2C0112,0x420112,0x421112,0x422112,0x423112,
        0x430112,0x440112,0x441112,0x442112,0x443112,0x450112,
        0x460112,0x470112,0x480112,0x4C0112)),
}


# Wilds-only evidence must not widen the shared 1057 decoder's profile.
_VALUE_WIDTH = dict(_MOTLIST_ANIMATION_VALUE_WIDTH)
_VALUE_WIDTH.update({('translation', recipe): width for recipe, width in (
    (0x25000, 2), (0x55000, 5), (0x67000, 6), (0x80000, 8))})


def _unpack_count(kind, recipe):
    # Coefficients actually read by each proven recipe. Wilds parameter blocks
    # are compact (8/12/16/20/24 bytes); an unconditional 8-float read overruns.
    if kind == 'rotation':
        if recipe in (0xC0000,0x41000,0x42000,0x43000):
            return 0
        return 2 if recipe in (0x21000,0x22000,0x23000) else 7
    if recipe == 0:
        return 0
    if recipe in (0x21000,0x22000,0x23000,0x31000,0x32000,0x33000):
        return 4
    if recipe in (0x41000,0x42000,0x43000,0x85000,0x86000,0x87000):
        return 3
    if recipe in (0x20000,0x30000,0x40000,0x50000,0x60000,0x70000,0x80000):
        return 6
    return 5


def parse_wilds_motlist_992(data, source_name, error_type=ValueError):
    if not source_name.lower().endswith('.motlist.992'):
        raise error_type('suffix-mismatch')
    checked_range(data, 0, 54, 'motlist-header', error_type)
    if struct.unpack_from('<I4s', data) != (992, b'mlst'):
        raise error_type('motlist-identity-mismatch')
    pointers, ids, name, source = struct.unpack_from('<4Q', data, 16)
    count = read_scalar(data, 48, '<I', 'slot-count', error_type)
    if not count or pointers < 54 or pointers % 8 or ids % 8:
        raise error_type('invalid-motlist-tables')
    checked_range(data, pointers, count * 8, 'pointer-table', error_type)
    checked_range(data, ids, count * 72, 'id-table', error_type)
    if pointers + count * 8 > ids or not 54 <= name < (source or pointers):
        raise error_type('motlist-table-overlap')
    list_name = read_utf16z(data, name, source or pointers, 'list-name', error_type)
    source_path = None
    if source:
        if not name < source < pointers:
            raise error_type('source-path-out-of-bounds')
        source_path = read_utf16z(data, source, pointers, 'source-path', error_type)
    values = [struct.unpack_from('<Q', data, pointers + i*8)[0] for i in range(count)]
    unique = sorted(set(v for v in values if v))
    ends = dict(zip(unique, unique[1:] + [ids]))
    slots, entries, first = [], [], {}
    for i, offset in enumerate(values):
        motion_id = struct.unpack_from('<I', data, ids+i*72+8)[0]
        collision = struct.unpack_from('<H', data, ids+i*72+20)[0]
        row = {'slot_index': i, 'pointer': offset, 'motion_id': motion_id,
               'collision_kind': collision, 'alias_of_slot': first.get(offset)}
        if not offset:
            if collision not in (1, 0xFFFF):
                raise error_type('empty-slot-kind-mismatch')
            row['kind'] = 'empty'
        else:
            end = ends[offset]
            if offset % 8 or offset < pointers+count*8 or offset+8 > end:
                raise error_type('entry-pointer-out-of-bounds')
            version, magic = struct.unpack_from('<I4s', data, offset)
            if (version, magic, collision) in ((932,b'mot ',1),(932,b'mot ',257)):
                kind = 'mot'
                if offset + 128 > end:
                    raise error_type('truncated-mot-header')
            elif (version, magic, collision) == (21,b'mtre',2):
                kind = 'mtre'
            else:
                raise error_type('unsupported-entry-identity')
            row['kind'] = kind
            entry = dict(row)
            entry.update(offset=offset, end=end, version=version)
            entries.append(entry)
            first.setdefault(offset, i)
        slots.append(row)
    return {'motlist': {'version':992, 'name':list_name, 'source_path':source_path,
                        'entry_count':count, 'pointer_table_offset':pointers,
                        'collision_table_offset':ids},
            'slots':slots, 'entries':entries}


class _ActionBounds:
    def __init__(self, data, start, end, error_type):
        self.data, self.start, self.end, self.error = data, start, end, error_type
        self.regions = []

    def range(self, relative, size, label):
        if relative < 128 or self.start + relative + size > self.end or size <= 0:
            raise self.error('offset-out-of-bounds:' + label)
        checked_range(self.data, self.start+relative, size, label, self.error)
        return self.start + relative

    def metadata(self, relative, size, label):
        absolute = self.range(relative, size, label)
        region = (relative, relative+size)
        if any(region[0] < b and a < region[1] for a,b in self.regions):
            raise self.error('range-overlap:' + label)
        self.regions.append(region)
        return absolute

    def string(self, relative, label):
        absolute = self.range(relative, 2, label)
        value = read_utf16z(self.data, absolute, self.end, label, self.error)
        region = (relative, relative+len(value.encode('utf-16le'))+2)
        if region not in self.regions:
            self.metadata(relative, region[1]-region[0], label)
        return value


def _action(data, entry, error):
    start, end = entry['offset'], entry['end']
    bounds = _ActionBounds(data, start, end, error)
    carrier, clips = struct.unpack_from('<QQ', data, start+16)
    name = struct.unpack_from('<Q', data, start+88)[0]
    frames = struct.unpack_from('<f', data, start+96)[0]
    bones, clip_count = struct.unpack_from('<HH', data, start+112)
    rate = struct.unpack_from('<H', data, start+120)[0]
    if not math.isfinite(frames) or frames <= 0 or rate != 60 or not bones or not clip_count:
        raise error('unsupported-action-count-or-time')
    joint = struct.unpack_from('<Q', data, start+56)[0]
    action = {'mot_start':start, 'action_end':end, 'bone_indirection_relative':carrier,
              'clip_table_relative':clips, 'action_name_relative':name,
              'frame_count':frames, 'frame_rate':rate, 'bone_count':bones,
              'bone_clip_count':clip_count, 'name':bounds.string(name,'action-name'),
              'joint_map_path':bounds.string(joint,'joint-map') if joint else None,
              'bounds':bounds}
    bounds.metadata(clips, clip_count*12, 'clip-table')
    # The 80-byte carrier rows and quaternion normalization were independently
    # revalidated for 932; the 1057 container/action parser is never called.
    bone_rows = _motlist_multi_carrier_bones(data, action, error)
    if bone_rows is not None:
        at = bounds.metadata(carrier,16,'carrier-indirection')
        table = struct.unpack_from('<Q',data,at)[0]
        bounds.metadata(table,bones*80,'bone-table')
        for i in range(bones):
            bounds.string(struct.unpack_from('<Q',data,start+table+i*80)[0],'bone-name')
    action['bones'] = bone_rows
    return action


def _tracks(data, action, bones, error):
    bounds = action['bounds']
    start = action['mot_start']
    descriptors, keys, seen = [], set(), set()
    unsupported = None
    for i in range(action['bone_clip_count']):
        index, mask, bone_hash, relative = struct.unpack_from(
            '<HHII',data,start+action['clip_table_relative']+i*12)
        if index >= len(bones) or bone_hash != bones[index]['hash']:
            raise error('bone-clip-index-or-hash-mismatch')
        if index in seen or mask not in (0xFF02,0xFF03):
            raise error('unsupported-or-duplicate-bone-components')
        seen.add(index)
        kinds = ('translation','rotation') if mask==0xFF03 else ('rotation',)
        absolute = bounds.metadata(relative,len(kinds)*20,'track-descriptors')
        for j,kind in enumerate(kinds):
            flags,count,times,values,unpack = struct.unpack_from('<5I',data,absolute+j*20)
            if not count or count > math.ceil(action['frame_count'])+1:
                raise error('invalid-track-key-count')
            width = {2:1,4:2}.get(flags >> 20)
            if width is None:
                raise error('unsupported-time-index-width')
            if flags not in _FLAGS[kind]:
                unsupported = 'unsupported-track-flags:%s:0x%X' % (kind,flags)
            parameter_size = _unpack_count(kind,flags & 0xFF000)*4
            for ptr,size,label in ((times,count*width,'times'),(values,1,'values'),
                                   (unpack,max(1,parameter_size),'unpack')):
                if ptr:
                    bounds.range(ptr,size,label)
                    keys.add(ptr)
                elif label=='values' or label=='times' and count!=1:
                    raise error('missing-track-'+label)
            descriptors.append((index,bone_hash,kind,flags,count,times,values,unpack,width))
    landmarks = sorted(keys | set(a for a,b in bounds.regions) | {bounds.end-start})
    shared_payloads = {}
    def payload(relative,size,label,signature=None):
        absolute = bounds.range(relative,size,label)
        if any(relative < b and a < relative+size for a,b in bounds.regions):
            raise error('range-overlap:'+label)
        end = next(v for v in landmarks if v > relative)
        if relative+size > end:
            raise error('payload-overrun:'+label)
        identity = (size,label,signature)
        if relative in shared_payloads and shared_payloads[relative] != identity:
            raise error('incompatible-shared-payload:'+label)
        shared_payloads[relative] = identity
        return absolute
    # All action structure is checked even when one codec is unavailable.
    for index,bh,kind,flags,count,times,values,unpack,width in descriptors:
        if times: payload(times,count*width,'times',width)
        if unpack:
            parameter_count = _unpack_count(kind,flags & 0xFF000)
            at = payload(unpack,max(1,parameter_count*4),'unpack')
            if not all(math.isfinite(v) for v in struct.unpack_from('<%df' % parameter_count,data,at)):
                raise error('non-finite-unpack')
        value_width = _VALUE_WIDTH.get((kind,flags & 0xFF000))
        payload(values,count*value_width if value_width else 1,'values',(kind,flags))
    if unsupported:
        return None, unsupported
    tracks = []
    for index,bh,kind,flags,count,times,values,unpack,width in descriptors:
        t = [struct.unpack_from('<B' if width==1 else '<H',data,start+times+k*width)[0]
             for k in range(count)] if times else [0]
        if any(v > math.ceil(action['frame_count']) for v in t) or any(a>b for a,b in zip(t,t[1:])):
            raise error('invalid-track-time')
        recipe = flags & 0xFF000
        packed21 = kind=='translation' and recipe==0x80000
        size = _VALUE_WIDTH[(kind,recipe)]
        parameter_count = _unpack_count(kind,recipe)
        params = struct.unpack_from('<%df' % parameter_count,data,start+unpack) if unpack else ()
        if parameter_count and not unpack:
            raise error('missing-track-unpack')
        result = []
        for k in range(count):
            raw = data[start+values+k*size:start+values+(k+1)*size]
            if packed21:
                bits = int.from_bytes(raw,'little')
                value = tuple(params[a]*((bits>>(21*a))&2097151)/2097151.0+params[a+3] for a in range(3))
            elif kind == 'translation' and recipe in (0x25000,0x55000,0x67000):
                # Five parameters: two scales followed by XYZ offsets. The
                # byte pair is XY; big-endian packed pairs are XY20 or ZX24.
                bits = {0x25000:8, 0x55000:20, 0x67000:24}[recipe]
                packed = int.from_bytes(raw, 'little' if bits == 8 else 'big')
                mask = (1 << bits) - 1
                axes = (2, 0) if recipe == 0x67000 else (0, 1)
                value = list(params[2:5])
                for component, axis in enumerate(axes):
                    value[axis] += params[component] * ((packed >> (bits*component)) & mask) / float(mask)
                value = tuple(value)
            else:
                value,_ = _motlist_animation_decode_value(kind,recipe,raw,params,error)
            if not all(math.isfinite(v) for v in value):
                raise error('non-finite-track-value')
            result.append(value)
        tracks.append({'bone_index':index,'bone_hash':bh,'kind':kind,'flags':flags,
                       'key_count':count,'times':t,'values':result,'binding_status':'bound'})
    return tracks,None


def decode_wilds_motlist_992(data, source_name, error_type=ValueError):
    profile = parse_wilds_motlist_992(data,source_name,error_type)
    unique = {}
    for entry in profile['entries']:
        if entry['kind']=='mot' and entry['offset'] not in unique:
            unique[entry['offset']] = _action(data,entry,error_type)
    carriers = [a for a in unique.values() if a['bones'] is not None]
    if unique and len(carriers)!=1:
        raise error_type('skeleton-carrier-count')
    bones = carriers[0]['bones'] if carriers else []
    decoded = {}
    for offset,action in unique.items():
        if action['bone_count']!=len(bones):
            raise error_type('shared-bone-count-mismatch')
        tracks,reason = _tracks(data,action,bones,error_type)
        decoded[offset] = {'name':action['name'],'frame_count':action['frame_count'],
                           'frame_rate':60,'duration_seconds':action['frame_count']/60.0,
                           'tracks':tracks,'reason':reason,'offset':offset,
                           'joint_map_path':action['joint_map_path']}
    actions,skipped = [],[]
    for entry in profile['entries']:
        row = dict(entry)
        if entry['kind']=='mtre':
            row['reason']='unsupported-mtre-semantics'
            skipped.append(row)
            continue
        row.update(decoded[entry['offset']])
        if row['reason']:
            row.pop('tracks')
            skipped.append(row)
        else:
            actions.append(row)
    return {'schema':'wilds-motlist-animation-set/v1','source_name':source_name,
            'sha256':sha256_bytes(data),'size':len(data),'time_unit':'frames',
            'motlist':profile['motlist'],'slots':profile['slots'],'entries':profile['entries'],
            'bones':bones,'actions':actions,'skipped_entries':skipped}
