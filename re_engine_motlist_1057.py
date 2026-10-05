"""Observed MOTLIST 1057 profiles and animation codecs; pure data."""

import hashlib
import json
import math
import struct
from re_engine_binary import checked_range, read_scalar, read_utf16z, sha256_bytes


MOTLIST_1057_VERSION = 1057
MOT_993_VERSION = 993
MTRE_22_VERSION = 22
MOTLIST_1057_HEADER_SIZE = 0x3E
MOT_993_HEADER_SIZE = 0x7A
MOTLIST_BONE_ROW_SIZE = 80
MOTLIST_CLIP_ROW_SIZE = 12
MOTLIST_TRACK_DESCRIPTOR_SIZE = 20
MOTLIST_TRACK_DESCRIPTOR_COUNT = 3
MOTLIST_TRACK_HEADER_SIZE = (
	MOTLIST_TRACK_DESCRIPTOR_SIZE * MOTLIST_TRACK_DESCRIPTOR_COUNT)
MOTLIST_MOTION_ID_ROW_SIZE = 72


def _motlist_fail(detail, error_type):
	raise error_type("structural-profile-mismatch:" + detail)


def _motlist_source_basename(source_name):
	return source_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _motlist_read_utf16z(data, offset, limit, label, error_type):
	try:
		return read_utf16z(data, offset, limit, label, error_type)
	except error_type as exc:
		detail = str(exc)
		if detail == label + "-out-of-bounds":
			raise error_type("offset-out-of-bounds:" + label)
		if detail == label + "-unterminated":
			raise error_type("unterminated-utf16:" + label)
		if detail == label + "-invalid-utf16":
			raise error_type("invalid-utf16:" + label)
		if detail == label + "-empty":
			raise error_type("empty-utf16:" + label)
		raise


def _motlist_relative_offset(data, mot_start, relative, size, action_end,
						 label, error_type):
	absolute = mot_start + relative
	checked_range(data, absolute, size, label, error_type)
	if relative == 0 or absolute < mot_start or absolute + size > action_end:
		raise error_type("offset-out-of-bounds:" + label)
	return absolute


def parse_pragmata_motlist_1057_multi(data, source_name,
								  error_type=ValueError):
	if not _motlist_source_basename(source_name).lower().endswith(
			".motlist.1057"):
		raise error_type("suffix-mismatch")
	if len(data) < MOTLIST_1057_HEADER_SIZE:
		raise error_type("truncated-motlist-header")

	version = read_scalar(data, 0, "<I", "motlist-version", error_type)
	if version != MOTLIST_1057_VERSION:
		raise error_type("motlist-version-mismatch")
	if data[4:8] != b"mlst":
		raise error_type("motlist-magic-mismatch")

	pointer_table = read_scalar(data, 0x10, "<Q", "pointer-table", error_type)
	collision_table = read_scalar(data, 0x18, "<Q", "collision-table", error_type)
	list_name_offset = read_scalar(data, 0x20, "<Q", "list-name", error_type)
	source_path_offset = read_scalar(data, 0x28, "<Q", "source-path", error_type)
	reserved_30 = read_scalar(data, 0x30, "<Q", "reserved-30", error_type)
	entry_count = read_scalar(data, 0x38, "<I", "entry-count", error_type)
	if reserved_30:
		_motlist_fail("reserved-header-fields", error_type)
	if pointer_table == 0 or pointer_table % 8:
		_motlist_fail("pointer-table-alignment", error_type)
	pointer_table_size = entry_count * 8
	checked_range(data, pointer_table, pointer_table_size, "pointer-table",
				  error_type)
	pointer_table_end = pointer_table + pointer_table_size
	if collision_table % 8:
		_motlist_fail("collision-table-alignment", error_type)
	if collision_table < pointer_table_end:
		_motlist_fail("collision-table-order", error_type)
	checked_range(data, collision_table,
				  entry_count * MOTLIST_MOTION_ID_ROW_SIZE,
				  "collision-table", error_type)

	name_limit = source_path_offset if source_path_offset else pointer_table
	if not (MOTLIST_1057_HEADER_SIZE <= list_name_offset < name_limit):
		raise error_type("offset-out-of-bounds:list-name")
	list_name = _motlist_read_utf16z(
		data, list_name_offset, name_limit, "list-name", error_type)
	source_path = None
	if source_path_offset:
		if (source_path_offset % 2 or
				not (MOTLIST_1057_HEADER_SIZE <= source_path_offset < pointer_table)):
			raise error_type("offset-out-of-bounds:source-path")
		source_path = _motlist_read_utf16z(
			data, source_path_offset, pointer_table, "source-path", error_type)

	pointers = []
	seen_pointers = set()
	for slot_index in range(entry_count):
		pointer = read_scalar(
			data, pointer_table + slot_index * 8, "<Q", "entry-pointer",
			error_type)
		if pointer:
			seen_pointers.add(pointer)
		pointers.append(pointer)

	ordered_pointers = sorted(seen_pointers)
	entry_ends = {}
	for pointer_index, pointer in enumerate(ordered_pointers):
		entry_ends[pointer] = (
			ordered_pointers[pointer_index + 1]
			if pointer_index + 1 < len(ordered_pointers)
			else collision_table)

	slots = []
	entries = []
	pointer_first_slots = {}
	mot_count = 0
	mtre_count = 0
	for slot_index, pointer in enumerate(pointers):
		collision_row = collision_table + slot_index * MOTLIST_MOTION_ID_ROW_SIZE
		motion_id = read_scalar(
			data, collision_row + 8, "<I", "motion-id", error_type)
		collision_kind = read_scalar(
			data, collision_row + 0x14, "<H", "collision-entry-kind",
			error_type)
		if pointer == 0:
			if collision_kind not in (1, 0xFFFF):
				_motlist_fail("collision-entry-kind", error_type)
			slots.append({
				"slot_index": slot_index,
				"pointer": 0,
				"kind": "empty",
				"motion_id": motion_id,
				"collision_kind": collision_kind,
			})
			continue
		if pointer < pointer_table_end:
			_motlist_fail("entry-pointer", error_type)
		if pointer + 8 > collision_table:
			raise error_type("offset-out-of-bounds:entry-header")
		if pointer % 8:
			_motlist_fail("entry-pointer", error_type)
		checked_range(data, pointer, 8, "entry-header", error_type)
		entry_end = entry_ends[pointer]
		if entry_end <= pointer:
			raise error_type("offset-out-of-bounds:entry-header")
		entry_version = read_scalar(
			data, pointer, "<I", "entry-version", error_type)
		entry_magic = data[pointer + 4:pointer + 8]
		if entry_magic == b"mot ":
			kind = "mot"
			expected_version = MOT_993_VERSION
			expected_collision_kinds = (1, 0x101)
			mot_count += 1
		elif entry_magic == b"mtre":
			kind = "mtre"
			expected_version = MTRE_22_VERSION
			expected_collision_kinds = (2,)
			mtre_count += 1
		else:
			raise error_type("unsupported-entry-kind:slot-" + str(slot_index))
		if entry_version != expected_version:
			raise error_type(
				"unsupported-entry-version:" + kind + ":" + str(entry_version))
		if collision_kind not in expected_collision_kinds:
			_motlist_fail("collision-entry-kind", error_type)
		alias_of_slot = pointer_first_slots.get(pointer)
		if alias_of_slot is None:
			pointer_first_slots[pointer] = slot_index
		slot = {
			"slot_index": slot_index,
			"pointer": pointer,
			"kind": kind,
			"motion_id": motion_id,
			"collision_kind": collision_kind,
			"alias_of_slot": alias_of_slot,
		}
		slots.append(slot)
		entries.append({
			"slot_index": slot_index,
			"offset": pointer,
			"end": entry_end,
			"kind": kind,
			"version": entry_version,
			"motion_id": motion_id,
			"collision_kind": collision_kind,
			"alias_of_slot": alias_of_slot,
		})

	return {
		"schema": "pragmata-motlist-multi-profile/v1",
		"capability": "pragmata-motlist-1057-multi-container-v1",
		"source_name": source_name,
		"size": len(data),
		"sha256": sha256_bytes(data),
		"motlist": {
			"version": version,
			"name": list_name,
			"source_path": source_path,
			"entry_count": entry_count,
			"pointer_table_offset": pointer_table,
			"collision_table_offset": collision_table,
		},
		"slots": slots,
		"entries": entries,
		"counts": {
			"slots": entry_count,
			"nonzero": len(entries),
			"empty": entry_count - len(entries),
			"mot": mot_count,
			"mtre": mtre_count,
		},
	}


def parse_pragmata_motlist_1057_exact(data, source_name,
							  error_type=ValueError):
	if not _motlist_source_basename(source_name).lower().endswith(
			".motlist.1057"):
		raise error_type("suffix-mismatch")
	if len(data) < MOTLIST_1057_HEADER_SIZE:
		raise error_type("truncated-motlist-header")

	version = read_scalar(data, 0, "<I", "motlist-version", error_type)
	if version != MOTLIST_1057_VERSION:
		raise error_type("motlist-version-mismatch")
	if data[4:8] != b"mlst":
		raise error_type("motlist-magic-mismatch")

	pointer_table = read_scalar(data, 0x10, "<Q", "pointer-table", error_type)
	collision_table = read_scalar(data, 0x18, "<Q", "collision-table", error_type)
	list_name_offset = read_scalar(data, 0x20, "<Q", "list-name", error_type)
	reserved_28 = read_scalar(data, 0x28, "<Q", "reserved-28", error_type)
	reserved_30 = read_scalar(data, 0x30, "<Q", "reserved-30", error_type)
	entry_count = read_scalar(data, 0x38, "<I", "entry-count", error_type)
	if entry_count != 1:
		_motlist_fail("entry-count", error_type)
	if reserved_28 or reserved_30:
		_motlist_fail("reserved-header-fields", error_type)
	if pointer_table == 0 or pointer_table % 8:
		_motlist_fail("pointer-table-alignment", error_type)
	checked_range(data, pointer_table, 8, "pointer-table", error_type)
	checked_range(data, collision_table, MOTLIST_MOTION_ID_ROW_SIZE,
				  "collision-table", error_type)
	if collision_table <= pointer_table + 8:
		_motlist_fail("collision-table-order", error_type)
	if not (MOTLIST_1057_HEADER_SIZE <= list_name_offset < pointer_table):
		raise error_type("offset-out-of-bounds:list-name")
	list_name = _motlist_read_utf16z(data, list_name_offset, pointer_table,
								  "list-name", error_type)

	mot_start = read_scalar(data, pointer_table, "<Q", "mot-pointer", error_type)
	if mot_start == 0 or mot_start % 8 or mot_start < pointer_table + 8:
		_motlist_fail("mot-pointer", error_type)
	checked_range(data, mot_start, MOT_993_HEADER_SIZE, "mot-header", error_type)
	if mot_start + MOT_993_HEADER_SIZE > collision_table:
		raise error_type("offset-out-of-bounds:mot-header")
	mot_version = read_scalar(data, mot_start, "<I", "mot-version", error_type)
	if mot_version != MOT_993_VERSION:
		raise error_type("mot-version-mismatch")
	if data[mot_start + 4:mot_start + 8] != b"mot ":
		raise error_type("mot-magic-mismatch")

	bone_indirection_relative = read_scalar(
		data, mot_start + 0x10, "<Q", "bone-table-indirection", error_type)
	clip_table_relative = read_scalar(
		data, mot_start + 0x18, "<Q", "clip-table", error_type)
	action_name_relative = read_scalar(
		data, mot_start + 0x58, "<Q", "action-name", error_type)
	frame_count = read_scalar(data, mot_start + 0x60, "<f", "frame-count", error_type)
	bone_count = read_scalar(data, mot_start + 0x70, "<H", "bone-count", error_type)
	bone_clip_count = read_scalar(
		data, mot_start + 0x72, "<H", "bone-clip-count", error_type)
	frame_rate = read_scalar(data, mot_start + 0x78, "<H", "frame-rate", error_type)
	if not math.isfinite(frame_count) or frame_count <= 0:
		_motlist_fail("frame-count", error_type)
	if frame_rate != 60:
		_motlist_fail("frame-rate", error_type)
	if bone_count == 0 or bone_clip_count == 0:
		_motlist_fail("empty-action", error_type)

	action_name_offset = _motlist_relative_offset(
		data, mot_start, action_name_relative, 2, collision_table, "action-name",
		error_type)
	action_name = _motlist_read_utf16z(data, action_name_offset, collision_table,
									"action-name", error_type)

	bone_indirection = _motlist_relative_offset(
		data, mot_start, bone_indirection_relative, 16, collision_table,
		"bone-table-indirection", error_type)
	bone_table_relative, bone_table_count = struct.unpack_from(
		"<QQ", data, bone_indirection)
	if bone_table_count != bone_count:
		_motlist_fail("bone-table-count", error_type)
	bone_table = _motlist_relative_offset(
		data, mot_start, bone_table_relative, bone_count * MOTLIST_BONE_ROW_SIZE,
		collision_table, "bone-table", error_type)

	bones = []
	bone_hashes = set()
	bone_names = set()
	root_count = 0
	for expected_index in range(bone_count):
		row = bone_table + expected_index * MOTLIST_BONE_ROW_SIZE
		name_relative, parent_relative = struct.unpack_from("<QQ", data, row)
		values = struct.unpack_from("<8f", data, row + 32)
		declared_index, bone_hash = struct.unpack_from("<II", data, row + 64)
		if declared_index != expected_index:
			_motlist_fail("bone-index", error_type)
		if not all(math.isfinite(value) for value in values):
			_motlist_fail("bone-transform", error_type)
		name_offset = _motlist_relative_offset(
			data, mot_start, name_relative, 2, collision_table, "bone-name",
			error_type)
		name = _motlist_read_utf16z(data, name_offset, collision_table,
									 "bone-name", error_type)
		if name in bone_names:
			_motlist_fail("duplicate-bone-name", error_type)
		if bone_hash in bone_hashes:
			_motlist_fail("duplicate-bone-hash", error_type)
		bone_names.add(name)
		bone_hashes.add(bone_hash)

		if parent_relative == 0:
			parent_index = None
			root_count += 1
		else:
			parent_absolute = mot_start + parent_relative
			delta = parent_absolute - bone_table
			if delta < 0 or delta % MOTLIST_BONE_ROW_SIZE:
				_motlist_fail("bone-parent", error_type)
			parent_index = delta // MOTLIST_BONE_ROW_SIZE
			if parent_index >= expected_index:
				_motlist_fail("bone-parent", error_type)
		bones.append({
			"index": expected_index,
			"parent_index": parent_index,
			"name": name,
			"hash": bone_hash,
			"reference_translation": list(values[:4]),
			"reference_rotation": list(values[4:]),
		})
	if root_count != 1:
		_motlist_fail("root-count", error_type)

	clip_table = _motlist_relative_offset(
		data, mot_start, clip_table_relative,
		bone_clip_count * MOTLIST_CLIP_ROW_SIZE, collision_table, "clip-table",
		error_type)
	track_groups = []
	payload_offsets = set()
	track_header_end = 0
	for clip_index in range(bone_clip_count):
		row = clip_table + clip_index * MOTLIST_CLIP_ROW_SIZE
		bone_index, track_flags, bone_hash, track_relative = struct.unpack_from(
			"<HHII", data, row)
		if bone_index >= bone_count:
			raise error_type("bone-clip-index-out-of-range")
		if bone_hash != bones[bone_index]["hash"]:
			raise error_type("bone-clip-hash-mismatch")
		if track_flags & 0x7 != 0x7:
			_motlist_fail("track-components", error_type)
		track_header = _motlist_relative_offset(
			data, mot_start, track_relative, MOTLIST_TRACK_HEADER_SIZE,
			collision_table, "track-header", error_type)
		track_header_end = max(track_header_end,
						   track_relative + MOTLIST_TRACK_HEADER_SIZE)
		descriptors = []
		for descriptor_index, kind in enumerate(
				("translation", "rotation", "scale")):
			descriptor = (track_header + descriptor_index *
						  MOTLIST_TRACK_DESCRIPTOR_SIZE)
			flags, key_count, frame_indices, frame_data, unpack_data = (
				struct.unpack_from("<IIIII", data, descriptor))
			if key_count == 0 or key_count > math.ceil(frame_count) + 1:
				_motlist_fail("track-key-count", error_type)
			index_class = flags >> 20
			if frame_indices:
				if index_class not in (2, 4, 5):
					_motlist_fail("track-index-compression", error_type)
				frame_index_width = {2: 1, 4: 2, 5: 4}[index_class]
				frame_index_size = key_count * frame_index_width
				_motlist_relative_offset(
					data, mot_start, frame_indices, frame_index_size,
					collision_table, "track-frame-indices", error_type)
				payload_offsets.add(frame_indices)
			else:
				frame_index_width = 0
				frame_index_size = 0
			_motlist_relative_offset(
				data, mot_start, frame_data, 1, collision_table,
				"track-frame-data", error_type)
			payload_offsets.add(frame_data)
			if unpack_data:
				_motlist_relative_offset(
					data, mot_start, unpack_data, 32, collision_table,
					"track-unpack-data", error_type)
				payload_offsets.add(unpack_data)
			descriptors.append({
				"kind": kind,
				"flags": flags,
				"key_count": key_count,
				"frame_index_relative_offset": frame_indices,
				"frame_index_width": frame_index_width,
				"frame_index_size": frame_index_size,
				"frame_data_relative_offset": frame_data,
				"unpack_data_relative_offset": unpack_data,
				"unpack_data_size": 32 if unpack_data else 0,
			})
		track_groups.append({
			"bone_index": bone_index,
			"track_flags": track_flags,
			"track_header_relative_offset": track_relative,
			"tracks": descriptors,
		})

	structural_landmarks = {
		collision_table - mot_start,
		action_name_relative,
		bone_indirection_relative,
		bone_table_relative,
	}
	ordered_landmarks = sorted(payload_offsets | structural_landmarks)
	for group in track_groups:
		for descriptor in group["tracks"]:
			for pointer_key in (
					"frame_index_relative_offset",
					"unpack_data_relative_offset",
			):
				start = descriptor[pointer_key]
				if not start:
					continue
				if start < track_header_end:
					label = ("track-frame-indices" if
							 pointer_key.startswith("frame_index") else
							 "track-unpack-data")
					raise error_type("offset-out-of-bounds:" + label)
			frame_data_start = descriptor["frame_data_relative_offset"]
			frame_data_end = next(
				(value for value in ordered_landmarks if value > frame_data_start),
				None)
			if (frame_data_start < track_header_end or
					frame_data_end is None or
					frame_data_end <= frame_data_start):
				raise error_type("offset-out-of-bounds:track-frame-data")
			descriptor["frame_data_bound_end"] = frame_data_end

	motion_id = read_scalar(data, collision_table + 8, "<H", "motion-id",
						error_type)
	return {
		"schema": "pragmata-motlist-profile/v1",
		"capability": "pragmata-motlist-1057-mot-993-single-action-local-bones-v1",
		"source_name": source_name,
		"size": len(data),
		"sha256": sha256_bytes(data),
		"motlist": {
			"version": version,
			"name": list_name,
			"entry_count": entry_count,
			"pointer_table_offset": pointer_table,
			"collision_table_offset": collision_table,
		},
		"action": {
			"version": mot_version,
			"name": action_name,
			"motion_id": motion_id,
			"frame_count": frame_count,
			"frame_rate": frame_rate,
			"bone_count": bone_count,
			"bone_clip_count": bone_clip_count,
		},
		"bones": bones,
		"tracks": track_groups,
		"mapping": {
			"mapped_clip_count": bone_clip_count,
			"all_clip_indices_and_hashes_match": True,
		},
	}


_MOTLIST_ANIMATION_VALUE_WIDTH = {
	("translation", 0x00000): 12,
	("scale", 0x00000): 12,
	("translation", 0x20000): 2,
	("translation", 0x21000): 2,
	("translation", 0x22000): 2,
	("translation", 0x23000): 2,
	("translation", 0x26000): 2,
	("translation", 0x27000): 2,
	("translation", 0x30000): 3,
	("translation", 0x31000): 3,
	("translation", 0x32000): 3,
	("translation", 0x33000): 3,
	("translation", 0x35000): 3,
	("translation", 0x36000): 3,
	("translation", 0x37000): 3,
	("translation", 0x40000): 4,
	("translation", 0x41000): 4,
	("translation", 0x42000): 4,
	("translation", 0x43000): 4,
	("translation", 0x45000): 4,
	("translation", 0x46000): 4,
	("translation", 0x47000): 4,
	("translation", 0x50000): 5,
	("translation", 0x56000): 5,
	("translation", 0x57000): 5,
	("translation", 0x60000): 6,
	("translation", 0x66000): 6,
	("translation", 0x70000): 7,
	("translation", 0x85000): 8,
	("translation", 0x86000): 8,
	("translation", 0x87000): 8,
	("rotation", 0x20000): 2,
	("rotation", 0x21000): 2,
	("rotation", 0x22000): 2,
	("rotation", 0x23000): 2,
	("rotation", 0x30000): 3,
	("rotation", 0x40000): 4,
	("rotation", 0x41000): 4,
	("rotation", 0x42000): 4,
	("rotation", 0x43000): 4,
	("rotation", 0x50000): 5,
	("rotation", 0x60000): 6,
	("rotation", 0x70000): 7,
	("rotation", 0x80000): 8,
	("rotation", 0xC0000): 12,
}
_MOTLIST_ANIMATION_FLAG_SUFFIX = dict(
	(identity, 0x112 if identity[0] == "rotation" else 0x0F2)
	for identity in _MOTLIST_ANIMATION_VALUE_WIDTH)
_MOTLIST_ANIMATION_EXACT_IDENTITIES = frozenset((
	("translation", 0x00000),
	("scale", 0x00000),
	("translation", 0x22000),
	("rotation", 0x22000),
	("rotation", 0x23000),
	("translation", 0x32000),
	("translation", 0x35000),
	("translation", 0x36000),
	("rotation", 0x40000),
	("rotation", 0xC0000),
))
_MOTLIST_ANIMATION_INDEX_FORMAT = {
	1: "<B",
	2: "<H",
	4: "<I",
}
_MOTLIST_1057_OBSERVED_FULL_FLAGS = {
	"translation": frozenset((
		0x2000F2, 0x2200F2, 0x2210F2, 0x2220F2, 0x2230F2,
		0x2260F2, 0x2270F2, 0x2300F2, 0x2310F2, 0x2320F2,
		0x2330F2, 0x2350F2, 0x2370F2, 0x2400F2, 0x2410F2,
		0x2420F2, 0x2430F2, 0x2450F2, 0x2460F2, 0x2470F2,
		0x2500F2, 0x2560F2, 0x2570F2, 0x2600F2, 0x2660F2,
		0x2700F2, 0x2850F2, 0x2860F2, 0x2870F2, 0x4000F2,
		0x4200F2, 0x4210F2, 0x4220F2, 0x4230F2, 0x4260F2,
		0x4270F2, 0x4300F2, 0x4310F2, 0x4320F2, 0x4350F2,
		0x4370F2, 0x4400F2, 0x4410F2, 0x4420F2, 0x4460F2,
		0x4470F2, 0x4500F2, 0x4570F2, 0x4600F2, 0x4700F2,
		0x4860F2,
	)),
	"rotation": frozenset((
		0x220112, 0x221112, 0x222112, 0x223112, 0x230112,
		0x240112, 0x241112, 0x242112, 0x243112, 0x250112,
		0x260112, 0x270112, 0x280112, 0x2C0112, 0x420112,
		0x421112, 0x422112, 0x423112, 0x430112, 0x440112,
		0x441112, 0x442112, 0x443112, 0x450112, 0x460112,
		0x470112, 0x480112, 0x4C0112,
	)),
	"scale": frozenset((0x2000F2, 0x4000F2)),
}


def _motlist_animation_canonical_time_sha256(times, error_type):
	payload = bytearray()
	try:
		for value in times:
			payload.extend(struct.pack("<I", value))
	except (OverflowError, struct.error):
		raise error_type("invalid-track-time")
	return hashlib.sha256(bytes(payload)).hexdigest()


def _motlist_animation_canonical_value_sha256(values, kind, error_type):
	payload = bytearray()
	try:
		for value in values:
			for component in value:
				if not math.isfinite(component):
					raise ValueError
				payload.extend(struct.pack("<f", component))
	except (ValueError, OverflowError, struct.error):
		raise error_type("non-finite-track-value:" + kind)
	return hashlib.sha256(bytes(payload)).hexdigest()


def _motlist_animation_normalize_rotation_xyz(values, error_type):
	if not all(math.isfinite(value) for value in values):
		raise error_type("non-finite-track-value:rotation")
	squared = sum(value * value for value in values)
	if not math.isfinite(squared) or squared > 1.001:
		raise error_type("invalid-quaternion:rotation")
	w = math.sqrt(max(0.0, 1.0 - squared))
	length = math.sqrt(squared + w * w)
	if not math.isfinite(length) or length == 0.0:
		raise error_type("invalid-quaternion:rotation")
	return (tuple(value / length for value in values) + (w / length,), squared)


def _motlist_animation_normalize_bind_rotation(values, error_type):
	if not all(math.isfinite(value) for value in values):
		raise error_type("invalid-quaternion:bone")
	squared = sum(value * value for value in values)
	if not math.isfinite(squared) or squared <= 0.0:
		raise error_type("invalid-quaternion:bone")
	length = math.sqrt(squared)
	return tuple(value / length for value in values)


def _motlist_animation_decode_times(data, mot_start, descriptor, frame_count,
								 error_type):
	kind = descriptor["kind"]
	key_count = descriptor["key_count"]
	relative = descriptor["frame_index_relative_offset"]
	if not relative:
		if key_count == 1:
			return [0]
		raise error_type("track-time-index-missing:" + kind)
	width = descriptor["frame_index_width"]
	fmt = _MOTLIST_ANIMATION_INDEX_FORMAT.get(width)
	if fmt is None or descriptor["frame_index_size"] != key_count * width:
		raise error_type("unsupported-track-flags:" + kind + ":0x%X" %
						 descriptor["flags"])
	start = mot_start + relative
	times = [struct.unpack_from(fmt, data, start + index * width)[0]
			 for index in range(key_count)]
	previous = None
	maximum_time = int(math.ceil(frame_count))
	for value in times:
		if value < 0 or value > maximum_time:
			raise error_type("track-time-out-of-domain:" + kind)
		if previous is not None and value < previous:
			raise error_type("track-time-descending:" + kind)
		previous = value
	return times


def _motlist_animation_packed_components(payload, bits, byte_order):
	raw = int.from_bytes(payload, byte_order)
	mask = (1 << bits) - 1
	return tuple(
		((raw >> (index * bits)) & mask) / float(mask) for index in range(3))


def _motlist_animation_decode_rotation_components(compression, payload, unpack):
	if compression == 0xC0000:
		return struct.unpack("<3f", payload)
	if compression == 0x20000:
		raw = _motlist_animation_packed_components(payload, 5, "little")
		return tuple(unpack[index] * raw[index] + unpack[index + 4]
					 for index in range(3))
	if compression in (0x21000, 0x22000, 0x23000):
		raw = struct.unpack("<H", payload)[0] / float(0xFFFF)
		components = [0.0, 0.0, 0.0]
		components[(compression - 0x21000) // 0x1000] = (
			unpack[0] * raw + unpack[1])
		return tuple(components)
	if compression == 0x30000:
		raw = tuple(value / float(0xFF) for value in bytearray(payload))
	elif compression == 0x40000:
		raw = _motlist_animation_packed_components(payload, 10, "little")
	elif compression in (0x41000, 0x42000, 0x43000):
		components = [0.0, 0.0, 0.0]
		components[(compression - 0x41000) // 0x1000] = struct.unpack(
			"<f", payload)[0]
		return tuple(components)
	elif compression == 0x50000:
		raw = _motlist_animation_packed_components(payload, 13, "big")
	elif compression == 0x60000:
		raw = _motlist_animation_packed_components(payload, 16, "big")
	elif compression == 0x70000:
		raw = _motlist_animation_packed_components(payload, 18, "big")
	else:
		raw = _motlist_animation_packed_components(payload, 21, "little")
	return tuple(unpack[index] * raw[index] + unpack[index + 4]
				 for index in range(3))


def _motlist_animation_decode_value(kind, compression, payload, unpack,
								 error_type):
	if kind == "rotation":
		components = _motlist_animation_decode_rotation_components(
			compression, payload, unpack)
		return _motlist_animation_normalize_rotation_xyz(components, error_type)
	if compression == 0x00000:
		value = struct.unpack("<3f", payload)
	elif compression == 0x20000:
		raw = _motlist_animation_packed_components(payload, 5, "little")
		value = tuple(unpack[index] * raw[index] + unpack[index + 3]
					  for index in range(3))
	elif compression in (0x21000, 0x22000, 0x23000):
		raw = struct.unpack("<H", payload)[0] / float(0xFFFF)
		axis = (compression - 0x21000) // 0x1000
		value = [unpack[1], unpack[2], unpack[3]]
		value[axis] = unpack[0] * raw + unpack[axis + 1]
		value = tuple(value)
	elif compression in (0x26000, 0x27000):
		raw = tuple(value / float(0xFF) for value in bytearray(payload))
		if compression == 0x26000:
			value = (unpack[0] * raw[0] + unpack[2], unpack[3],
					 unpack[1] * raw[1] + unpack[4])
		else:
			value = (unpack[2], unpack[0] * raw[0] + unpack[3],
					 unpack[1] * raw[1] + unpack[4])
	elif compression == 0x30000:
		raw = tuple(value / float(0xFF) for value in bytearray(payload))
		value = tuple(unpack[index] * raw[index] + unpack[index + 3]
					  for index in range(3))
	elif compression in (0x31000, 0x32000, 0x33000):
		raw = int.from_bytes(payload, "big") / float(0xFFFFFF)
		axis = (compression - 0x31000) // 0x1000
		value = [unpack[1], unpack[2], unpack[3]]
		value[axis] = unpack[0] * raw + unpack[axis + 1]
		value = tuple(value)
	elif compression in (0x35000, 0x36000, 0x37000):
		raw = int.from_bytes(payload, "big")
		first = unpack[0] * (raw & 0xFFF) / float(0xFFF)
		second = unpack[1] * ((raw >> 12) & 0xFFF) / float(0xFFF)
		if compression == 0x35000:
			value = (unpack[2], first + unpack[3], second + unpack[4])
		elif compression == 0x36000:
			value = (first + unpack[2], unpack[3], second + unpack[4])
		else:
			value = (first + unpack[2], second + unpack[3], unpack[4])
	elif compression == 0x40000:
		raw = _motlist_animation_packed_components(payload, 10, "little")
		value = tuple(unpack[index] * raw[index] + unpack[index + 3]
					  for index in range(3))
	elif compression in (0x41000, 0x42000, 0x43000):
		axis = (compression - 0x41000) // 0x1000
		value = [unpack[0], unpack[1], unpack[2]]
		value[axis] = struct.unpack("<f", payload)[0]
		value = tuple(value)
	elif compression in (0x45000, 0x46000, 0x47000):
		raw = struct.unpack("<HH", payload)
		raw = tuple(value / float(0xFFFF) for value in raw)
		if compression == 0x45000:
			value = (unpack[0] * raw[0] + unpack[2],
					 unpack[1] * raw[1] + unpack[3], unpack[4])
		elif compression == 0x46000:
			value = (unpack[0] * raw[0] + unpack[2], unpack[3],
					 unpack[1] * raw[1] + unpack[4])
		else:
			value = (unpack[2], unpack[0] * raw[0] + unpack[3],
					 unpack[1] * raw[1] + unpack[4])
	elif compression in (0x50000, 0x60000, 0x70000):
		bits = {0x50000: 13, 0x60000: 16, 0x70000: 18}[compression]
		raw = _motlist_animation_packed_components(payload, bits, "big")
		value = tuple(unpack[index] * raw[index] + unpack[index + 3]
					  for index in range(3))
	elif compression in (0x56000, 0x57000, 0x66000):
		bits = 24 if compression == 0x66000 else 20
		raw = int.from_bytes(payload, "big")
		mask = (1 << bits) - 1
		low = (raw & mask) / float(mask)
		high = ((raw >> bits) & mask) / float(mask)
		if compression in (0x56000, 0x66000):
			value = (unpack[2], unpack[0] * low + unpack[3],
					 unpack[1] * high + unpack[4])
		else:
			value = (unpack[1] * high + unpack[2], unpack[3],
					 unpack[0] * low + unpack[4])
	elif compression in (0x85000, 0x86000, 0x87000):
		first, second = struct.unpack("<2f", payload)
		if compression == 0x85000:
			value = (first, second, unpack[2])
		elif compression == 0x86000:
			value = (unpack[0], first, second)
		else:
			value = (second, unpack[1], first)
	if not all(math.isfinite(component) for component in value):
		raise error_type("non-finite-track-value:" + kind)
	return (tuple(value), 0.0)


def _motlist_animation_decode_track(data, mot_start, descriptor, frame_count,
								bone_index, bone_hash, error_type,
								accepted_full_flags=None):
	kind = descriptor["kind"]
	flags = descriptor["flags"]
	compression = flags & 0xFF000
	identity = (kind, compression)
	width = _MOTLIST_ANIMATION_VALUE_WIDTH.get(identity)
	if (width is None or
			accepted_full_flags is None and
			identity not in _MOTLIST_ANIMATION_EXACT_IDENTITIES):
		raise error_type("unsupported-track-compression:%s:0x%X" %
						 (kind, compression))
	expected_suffix = _MOTLIST_ANIMATION_FLAG_SUFFIX[identity]
	if accepted_full_flags is not None:
		flags_valid = flags in accepted_full_flags
	else:
		flags_valid = (
			(flags >> 20) in (2, 4, 5) and
			(flags & 0xFFFFF) == (compression | expected_suffix))
	if not flags_valid:
		raise error_type("unsupported-track-flags:%s:0x%X" % (kind, flags))
	times = _motlist_animation_decode_times(
		data, mot_start, descriptor, frame_count, error_type)
	key_count = descriptor["key_count"]
	payload_relative = descriptor["frame_data_relative_offset"]
	required_size = key_count * width
	required_end = mot_start + payload_relative + required_size
	if required_end > len(data):
		raise error_type("track-payload-truncated:" + kind)
	if payload_relative + required_size > descriptor["frame_data_bound_end"]:
		raise error_type("track-payload-overrun:" + kind)
	payload_start = mot_start + payload_relative
	unpack_relative = descriptor["unpack_data_relative_offset"]
	if unpack_relative:
		unpack = struct.unpack_from("<8f", data, mot_start + unpack_relative)
	else:
		unpack = (0.0,) * 8
	values = []
	maximum_rotation_squared = 0.0
	for index in range(key_count):
		start = payload_start + index * width
		payload = data[start:start + width]
		value, rotation_squared = _motlist_animation_decode_value(
			kind, compression, payload, unpack, error_type)
		values.append(value)
		maximum_rotation_squared = max(
			maximum_rotation_squared, rotation_squared)
	component_count = len(values[0])
	return ({
		"bone_index": bone_index,
		"bone_hash": bone_hash,
		"kind": kind,
		"flags": flags,
		"key_count": key_count,
		"times": times,
		"values": values,
		"time_sha256": _motlist_animation_canonical_time_sha256(
			times, error_type),
		"value_sha256": _motlist_animation_canonical_value_sha256(
			values, kind, error_type),
		"minimum": [min(value[index] for value in values)
					for index in range(component_count)],
		"maximum": [max(value[index] for value in values)
					for index in range(component_count)],
		"all_finite": True,
	}, maximum_rotation_squared)


def _motlist_multi_action_header(data, entry, error_type):
	mot_start = entry["offset"]
	action_end = entry["end"]
	checked_range(data, mot_start, MOT_993_HEADER_SIZE, "mot-header", error_type)
	if mot_start + MOT_993_HEADER_SIZE > action_end:
		raise error_type("offset-out-of-bounds:mot-header")
	if read_scalar(data, mot_start, "<I", "mot-version", error_type) != MOT_993_VERSION:
		raise error_type("mot-version-mismatch")
	if data[mot_start + 4:mot_start + 8] != b"mot ":
		raise error_type("mot-magic-mismatch")

	bone_indirection_relative = read_scalar(
		data, mot_start + 0x10, "<Q", "bone-table-indirection", error_type)
	clip_table_relative = read_scalar(
		data, mot_start + 0x18, "<Q", "clip-table", error_type)
	action_name_relative = read_scalar(
		data, mot_start + 0x58, "<Q", "action-name", error_type)
	joint_map_relative = read_scalar(
		data, mot_start + 0x38, "<Q", "joint-map-path", error_type)
	frame_count = read_scalar(
		data, mot_start + 0x60, "<f", "frame-count", error_type)
	bone_count = read_scalar(data, mot_start + 0x70, "<H", "bone-count", error_type)
	bone_clip_count = read_scalar(
		data, mot_start + 0x72, "<H", "bone-clip-count", error_type)
	frame_rate = read_scalar(data, mot_start + 0x78, "<H", "frame-rate", error_type)
	if not math.isfinite(frame_count) or frame_count <= 0:
		_motlist_fail("frame-count", error_type)
	if frame_rate != 60:
		_motlist_fail("frame-rate", error_type)
	if bone_count == 0 or bone_clip_count == 0:
		_motlist_fail("empty-action", error_type)
	action_name_offset = _motlist_relative_offset(
		data, mot_start, action_name_relative, 2, action_end, "action-name",
		error_type)
	action_name = _motlist_read_utf16z(
		data, action_name_offset, action_end, "action-name", error_type)
	joint_map_path = None
	if joint_map_relative:
		joint_map_offset = _motlist_relative_offset(
			data, mot_start, joint_map_relative, 2, action_end,
			"joint-map-path", error_type)
		joint_map_path = _motlist_read_utf16z(
			data, joint_map_offset, action_end, "joint-map-path", error_type)
	return {
		"mot_start": mot_start,
		"action_end": action_end,
		"bone_indirection_relative": bone_indirection_relative,
		"clip_table_relative": clip_table_relative,
		"action_name_relative": action_name_relative,
		"name": action_name,
		"joint_map_path": joint_map_path,
		"frame_count": frame_count,
		"frame_rate": frame_rate,
		"bone_count": bone_count,
		"bone_clip_count": bone_clip_count,
	}


def _motlist_multi_carrier_bones(data, action, error_type):
	mot_start = action["mot_start"]
	action_end = action["action_end"]
	relative = action["bone_indirection_relative"]
	absolute = mot_start + relative
	if relative == 0 or absolute == action_end:
		return None
	if absolute < mot_start or absolute + 16 > action_end:
		raise error_type("offset-out-of-bounds:bone-table-indirection")
	bone_table_relative, bone_table_count = struct.unpack_from("<QQ", data, absolute)
	bone_count = action["bone_count"]
	if bone_table_count != bone_count:
		_motlist_fail("bone-table-count", error_type)
	bone_table = _motlist_relative_offset(
		data, mot_start, bone_table_relative,
		bone_count * MOTLIST_BONE_ROW_SIZE, action_end, "bone-table", error_type)

	bones = []
	bone_hashes = set()
	bone_names = set()
	root_count = 0
	for expected_index in range(bone_count):
		row = bone_table + expected_index * MOTLIST_BONE_ROW_SIZE
		name_relative, parent_relative = struct.unpack_from("<QQ", data, row)
		values = struct.unpack_from("<8f", data, row + 32)
		declared_index, bone_hash = struct.unpack_from("<II", data, row + 64)
		if declared_index != expected_index:
			_motlist_fail("bone-index", error_type)
		if not all(math.isfinite(value) for value in values):
			_motlist_fail("bone-transform", error_type)
		name_offset = _motlist_relative_offset(
			data, mot_start, name_relative, 2, action_end, "bone-name",
			error_type)
		name = _motlist_read_utf16z(
			data, name_offset, action_end, "bone-name", error_type)
		if name in bone_names:
			_motlist_fail("duplicate-bone-name", error_type)
		if bone_hash in bone_hashes:
			_motlist_fail("duplicate-bone-hash", error_type)
		bone_names.add(name)
		bone_hashes.add(bone_hash)
		if parent_relative == 0:
			parent_index = None
			root_count += 1
		else:
			parent_absolute = mot_start + parent_relative
			delta = parent_absolute - bone_table
			if delta < 0 or delta % MOTLIST_BONE_ROW_SIZE:
				_motlist_fail("bone-parent", error_type)
			parent_index = delta // MOTLIST_BONE_ROW_SIZE
			if parent_index >= expected_index:
				_motlist_fail("bone-parent", error_type)
		bones.append({
			"index": expected_index,
			"parent_index": parent_index,
			"name": name,
			"hash": bone_hash,
			"local_translation": tuple(values[:3]),
			"local_rotation": _motlist_animation_normalize_bind_rotation(
				tuple(values[4:]), error_type),
			"local_scale": (1.0, 1.0, 1.0),
		})
	if root_count != 1:
		_motlist_fail("root-count", error_type)
	action["bone_table_relative"] = bone_table_relative
	return bones


def _motlist_multi_descriptors(data, action, bone_hash_to_index, error_type,
							   allow_external_bones=False):
	mot_start = action["mot_start"]
	action_end = action["action_end"]
	action_relative_end = action_end - mot_start
	clip_table = _motlist_relative_offset(
		data, mot_start, action["clip_table_relative"],
		action["bone_clip_count"] * MOTLIST_CLIP_ROW_SIZE, action_end,
		"clip-table", error_type)
	groups = []
	payload_offsets = set()
	track_header_end = 0
	kind_bits = (("translation", 1), ("rotation", 2), ("scale", 4))
	for clip_index in range(action["bone_clip_count"]):
		row = clip_table + clip_index * MOTLIST_CLIP_ROW_SIZE
		bone_index, track_flags, bone_hash, track_relative = struct.unpack_from(
			"<HHII", data, row)
		if bone_index >= action["bone_count"]:
			raise error_type("bone-clip-index-out-of-range")
		component_mask = track_flags & 0x7
		if track_flags & ~0x7 != 0xFF00 or component_mask == 0:
			_motlist_fail("track-components", error_type)
		kinds = [kind for kind, bit in kind_bits if component_mask & bit]
		header_size = len(kinds) * MOTLIST_TRACK_DESCRIPTOR_SIZE
		track_header = _motlist_relative_offset(
			data, mot_start, track_relative, header_size, action_end,
			"track-header", error_type)
		track_header_end = max(track_header_end, track_relative + header_size)
		if bone_hash not in bone_hash_to_index and not allow_external_bones:
			raise error_type("bone-clip-hash-mismatch")
		mapped_bone_index = bone_hash_to_index.get(bone_hash)
		descriptors = []
		for descriptor_index, kind in enumerate(kinds):
			descriptor_offset = (
				track_header + descriptor_index * MOTLIST_TRACK_DESCRIPTOR_SIZE)
			flags, key_count, frame_indices, frame_data, unpack_data = (
				struct.unpack_from("<IIIII", data, descriptor_offset))
			if flags not in _MOTLIST_1057_OBSERVED_FULL_FLAGS[kind]:
				raise error_type("unsupported-track-flags:%s:0x%X" %
							 (kind, flags))
			if key_count == 0 or key_count > math.ceil(action["frame_count"]) + 1:
				_motlist_fail("track-key-count", error_type)
			index_class = flags >> 20
			if frame_indices:
				if index_class not in (2, 4, 5):
					_motlist_fail("track-index-compression", error_type)
				frame_index_width = {2: 1, 4: 2, 5: 4}[index_class]
				frame_index_size = key_count * frame_index_width
				_motlist_relative_offset(
					data, mot_start, frame_indices, frame_index_size, action_end,
					"track-frame-indices", error_type)
				payload_offsets.add(frame_indices)
			else:
				frame_index_width = 0
				frame_index_size = 0
			_motlist_relative_offset(
				data, mot_start, frame_data, 1, action_end,
				"track-frame-data", error_type)
			payload_offsets.add(frame_data)
			if unpack_data:
				_motlist_relative_offset(
					data, mot_start, unpack_data, 32, action_end,
					"track-unpack-data", error_type)
				payload_offsets.add(unpack_data)
			descriptors.append({
				"kind": kind,
				"flags": flags,
				"key_count": key_count,
				"frame_index_relative_offset": frame_indices,
				"frame_index_width": frame_index_width,
				"frame_index_size": frame_index_size,
				"frame_data_relative_offset": frame_data,
				"unpack_data_relative_offset": unpack_data,
				"unpack_data_size": 32 if unpack_data else 0,
			})
		groups.append({
			"bone_index": mapped_bone_index,
			"bone_hash": bone_hash,
			"binding_status": ("bound" if mapped_bone_index is not None else
							   "external-skeleton-required"),
			"tracks": descriptors,
		})

	structural_landmarks = {
		action_relative_end,
		action["action_name_relative"],
		action["bone_indirection_relative"],
		action["clip_table_relative"],
	}
	if "bone_table_relative" in action:
		structural_landmarks.add(action["bone_table_relative"])
	ordered_landmarks = sorted(payload_offsets | structural_landmarks)
	for group in groups:
		for descriptor in group["tracks"]:
			for pointer_key in (
					"frame_index_relative_offset", "unpack_data_relative_offset"):
				start = descriptor[pointer_key]
				if not start:
					continue
				if start < track_header_end:
					label = ("track-frame-indices" if
							 pointer_key.startswith("frame_index") else
							 "track-unpack-data")
					raise error_type("offset-out-of-bounds:" + label)
			frame_data_start = descriptor["frame_data_relative_offset"]
			frame_data_end = next(
				(value for value in ordered_landmarks if value > frame_data_start),
				None)
			if (frame_data_start < track_header_end or
					frame_data_end is None or frame_data_end <= frame_data_start):
				raise error_type("offset-out-of-bounds:track-frame-data")
			descriptor["frame_data_bound_end"] = frame_data_end
	return groups


def _decode_motlist_1057_multi(data, source_name, error_type=ValueError):
	profile = parse_pragmata_motlist_1057_multi(
		data, source_name, error_type=error_type)
	mot_entries = [entry for entry in profile["entries"] if entry["kind"] == "mot"]
	unique_actions = {}
	for entry in mot_entries:
		if entry["offset"] not in unique_actions:
			unique_actions[entry["offset"]] = _motlist_multi_action_header(
				data, entry, error_type)

	carriers = []
	for offset, action in unique_actions.items():
		bones = _motlist_multi_carrier_bones(data, action, error_type)
		if bones is not None:
			carriers.append((offset, bones))
	if mot_entries and len(carriers) != 1:
		_motlist_fail("skeleton-carrier-count", error_type)
	if carriers:
		carrier_offset, bones = carriers[0]
		carrier_slot = next(
			entry["slot_index"] for entry in mot_entries
			if entry["offset"] == carrier_offset)
	else:
		bones = []
		carrier_slot = None
	bone_hash_to_index = {bone["hash"]: bone["index"] for bone in bones}

	decoded_actions = {}
	for offset, action in unique_actions.items():
		groups = _motlist_multi_descriptors(
			data, action, bone_hash_to_index, error_type,
			allow_external_bones=offset != carrier_offset)
		tracks = []
		maximum_rotation_squared = 0.0
		for group in groups:
			for descriptor in group["tracks"]:
				track, rotation_squared = _motlist_animation_decode_track(
					data, action["mot_start"], descriptor,
					action["frame_count"], group["bone_index"],
					group["bone_hash"], error_type,
					_MOTLIST_1057_OBSERVED_FULL_FLAGS[descriptor["kind"]])
				track["binding_status"] = group["binding_status"]
				tracks.append(track)
				maximum_rotation_squared = max(
					maximum_rotation_squared, rotation_squared)
		all_times = [value for track in tracks for value in track["times"]]
		decoded_actions[offset] = {
			"name": action["name"],
			"joint_map_path": action["joint_map_path"],
			"frame_count": action["frame_count"],
			"frame_rate": action["frame_rate"],
			"duration_seconds": (
				action["frame_count"] / float(action["frame_rate"])),
			"minimum_key_time": min(all_times),
			"maximum_key_time": max(all_times),
			"maximum_pre_normalization_rotation_norm_squared":
				maximum_rotation_squared,
			"unbound_track_count": sum(
				1 for track in tracks if track["bone_index"] is None),
			"tracks": tracks,
		}

	actions = []
	for entry in mot_entries:
		action = dict(decoded_actions[entry["offset"]])
		action.update({
			"slot_index": entry["slot_index"],
			"alias_of_slot": entry["alias_of_slot"],
			"motion_id": entry["motion_id"],
		})
		actions.append(action)
	skipped_entries = [{
		"slot_index": entry["slot_index"],
		"kind": "mtre",
		"version": entry["version"],
		"motion_id": entry["motion_id"],
		"reason": "unsupported-mtre-semantics",
	} for entry in profile["entries"] if entry["kind"] == "mtre"]
	external_bone_hashes = sorted(set(
		track["bone_hash"] for action in actions for track in action["tracks"]
		if track["bone_index"] is None))
	return {
		"schema": "pragmata-motlist-animation-set/v1",
		"capability":
			"pragmata-motlist-1057-mot-993-multi-shared-bones-v1",
		"source_name": source_name,
		"size": len(data),
		"sha256": sha256_bytes(data),
		"motlist": profile["motlist"],
		"carrier_slot": carrier_slot,
		"bones": bones,
		"actions": actions,
		"external_bone_hashes": external_bone_hashes,
		"entries": profile["entries"],
		"skipped_entries": skipped_entries,
	}


decode_pragmata_motlist_1057_multi = _decode_motlist_1057_multi


def _decode_motlist_1057_exact(data, source_name, error_type=ValueError):
	profile = parse_pragmata_motlist_1057_exact(
		data, source_name, error_type=error_type)
	pointer_table = profile["motlist"]["pointer_table_offset"]
	mot_start = read_scalar(data, pointer_table, "<Q", "mot-pointer", error_type)
	frame_count = profile["action"]["frame_count"]
	frame_rate = profile["action"]["frame_rate"]
	bones = []
	for bone in profile["bones"]:
		bones.append({
			"index": bone["index"],
			"parent_index": bone["parent_index"],
			"name": bone["name"],
			"hash": bone["hash"],
			"local_translation": tuple(bone["reference_translation"][:3]),
			"local_rotation": _motlist_animation_normalize_bind_rotation(
				tuple(bone["reference_rotation"]), error_type),
			"local_scale": (1.0, 1.0, 1.0),
		})
	tracks = []
	maximum_rotation_squared = 0.0
	for group in profile["tracks"]:
		bone_index = group["bone_index"]
		bone_hash = bones[bone_index]["hash"]
		for descriptor in group["tracks"]:
			track, track_rotation_squared = _motlist_animation_decode_track(
				data, mot_start, descriptor, frame_count, bone_index, bone_hash,
				error_type)
			tracks.append(track)
			maximum_rotation_squared = max(
				maximum_rotation_squared, track_rotation_squared)
	all_times = [value for track in tracks for value in track["times"]]
	return {
		"schema": "pragmata-motlist-animation/v1",
		"source_name": source_name,
		"size": len(data),
		"sha256": sha256_bytes(data),
		"action": {
			"name": profile["action"]["name"],
			"motion_id": profile["action"]["motion_id"],
			"frame_count": frame_count,
			"frame_rate": frame_rate,
			"duration_seconds": frame_count / float(frame_rate),
			"minimum_key_time": min(all_times),
			"maximum_key_time": max(all_times),
			"maximum_pre_normalization_rotation_norm_squared":
				maximum_rotation_squared,
		},
		"bones": bones,
		"tracks": tracks,
	}


decode_pragmata_motlist_1057_exact = _decode_motlist_1057_exact
