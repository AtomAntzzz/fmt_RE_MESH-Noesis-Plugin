"""Observed MESH profiles and geometry decoding; independent of the host."""

import hashlib
import math
import re_engine_common as re_common
import struct
from re_engine_config import (
	PRAGMATA_250707828,
	PRAGMATA_HEADER_FIELDS,
	PRAGMATA_MESH_RANGE_LABELS,
	PRAGMATA_MPLY_250707828,
	PRAGMATA_MPLY_VERTEX_FLAGS,
	WILDS_240704828,
	WILDS_MPLY_240704828,
)
from re_engine_types import (
	MeshProfileError,
)

def _detectPragmataIdentity(data, path):
	lower_path = path.lower()
	if not lower_path.endswith(".251121828"):
		return None
	if len(data) < 0xB0:
		raise MeshProfileError("truncated-late-header")
	magic = data[0:4]
	if magic not in (b"MESH", b"MPLY"):
		raise MeshProfileError("mesh-magic-mismatch")
	if struct.unpack_from("<I", data, 4)[0] != 250707828:
		raise MeshProfileError("internal-version-mismatch")
	if struct.unpack_from("<I", data, 8)[0] != len(data):
		raise MeshProfileError("declared-size-mismatch")
	return PRAGMATA_MPLY_250707828 if magic == b"MPLY" else PRAGMATA_250707828

def detectWildsMeshIdentity(data, path):
	if not path.lower().endswith(".mesh.241111606"):
		return None
	_checkedRange(data, 0, 176, "wilds-header")
	magic = data[:4]
	if magic not in (b"MESH", b"MPLY"):
		raise MeshProfileError("mesh-magic-mismatch")
	if _readMeshScalar(data, 4, "<I", "version") != 240704828:
		raise MeshProfileError("internal-version-mismatch")
	if _readMeshScalar(data, 8, "<I", "size") != len(data):
		raise MeshProfileError("declared-size-mismatch")
	return WILDS_MPLY_240704828 if magic == b"MPLY" else WILDS_240704828

def parseWildsMeshHeader(data, path):
	capability = detectWildsMeshIdentity(data, path)
	if capability != WILDS_240704828:
		raise MeshProfileError("unsupported-mesh-profile")
	header = {"capability": capability,
		"name_count": _readMeshScalar(data, 20, "<H", "name-count")}
	for name, offset in (("vertices_offset", 40), ("lod_offset", 48),
			("blend_shape_offset", 80), ("mesh_offset", 88),
			("skeleton_offset", 120), ("material_remap_offset", 128),
			("bone_remap_offset", 136), ("blend_name_offset", 144),
			("names_offset", 152), ("streaming_offset", 160)):
		value = _readMeshScalar(data, offset, "<Q", name)
		if value and (value < 176 or value >= len(data)):
			raise MeshProfileError("offset-out-of-bounds:" + name)
		header[name] = value
	for name in ("vertices_offset", "lod_offset", "mesh_offset",
			"material_remap_offset", "names_offset", "streaming_offset"):
		if not header[name]:
			raise MeshProfileError("offset-out-of-bounds:" + name)
	if not header["name_count"]:
		raise MeshProfileError("structural-profile-mismatch:name-count")
	_checkedRange(data, header["streaming_offset"], 16, "streaming-info")
	count, unknown, entries = struct.unpack_from("<IIQ", data, header["streaming_offset"])
	if count > 7 or unknown != 0:
		raise MeshProfileError("unsupported-streaming-entry-count")
	if count:
		_checkedRange(data, entries, count * 8, "streaming-entries")
	header["streaming_entry_count"] = count
	header["streaming_entries_offset"] = entries
	return header

def _readMeshScalar(data, offset, fmt, label):
	return re_common.read_scalar(data, offset, fmt, label, MeshProfileError)

def _checkedRange(data, start, size, label):
	return re_common.checked_range(data, start, size, label, MeshProfileError)

def _validatePragmataBoneMapCount(bone_map_count):
	if isinstance(bone_map_count, bool) or not isinstance(bone_map_count, int) or bone_map_count <= 0 or bone_map_count > 1024:
		raise MeshProfileError("structural-profile-mismatch:bone-map-count")
	return bone_map_count

def decodeSixU10(value, bone_map_count, expected_separator=3):
	return re_common.decode_six_u10(
		value, bone_map_count, expected_separator, MeshProfileError)

def parsePragmataSubmesh(data, offset):
	_checkedRange(data, offset, 32, "submesh-record")
	values = struct.unpack_from("<BBBBIIIIIII", data, offset)
	return {
		"material_index": values[0],
		"index_count": values[5],
		"index_start": values[6],
		"vertex_start": values[7],
		"streaming_offset": values[8],
		"platform_streaming_offset": values[9],
	}

def _validatePragmataWeights(weight_elements, bone_map_count):
	if len(weight_elements) % 16:
		raise MeshProfileError("structural-profile-mismatch:weight-stride")
	bone_map_count = _validatePragmataBoneMapCount(bone_map_count)
	weighted_vertices = 0
	weighted_bones = set()
	max_influences = 0
	max_error = 0.0
	for offset in range(0, len(weight_elements), 16):
		indices = decodeSixU10(
			struct.unpack_from("<Q", weight_elements, offset)[0], bone_map_count
		)
		weights = struct.unpack_from("8B", weight_elements, offset + 8)
		if weights[6] != 0 or weights[7] != 0:
			raise MeshProfileError("unsupported-extra-weight-profile")
		active = [index for index, weight in zip(indices, weights[:6]) if weight != 0]
		if active:
			weighted_vertices += 1
			weighted_bones.update(active)
			max_influences = max(max_influences, len(active))
			max_error = max(max_error, abs(sum(weight / 255.0 for weight in weights[:6]) - 1.0))
	return {
		"weighted_vertex_count": weighted_vertices,
		"weighted_bone_count": len(weighted_bones),
		"max_influences": max_influences,
		"weight_sum_max_error": max_error,
	}

def _decodePragmataWeightProfile(weight_elements, extra_weight_elements, bone_map_count):
	if len(weight_elements) % 16:
		raise MeshProfileError("structural-profile-mismatch:weight-stride")
	if extra_weight_elements is not None and len(extra_weight_elements) != len(weight_elements):
		raise MeshProfileError("structural-profile-mismatch:extra-weight-stride")
	_validatePragmataBoneMapCount(bone_map_count)
	index_rows = []
	weight_rows = []
	weighted_vertices = 0
	weighted_bones = set()
	max_influences = 0
	max_error = 0.0
	for offset in range(0, len(weight_elements), 16):
		primary_indices = decodeSixU10(
			struct.unpack_from("<Q", weight_elements, offset)[0], bone_map_count)
		weights = struct.unpack_from("8B", weight_elements, offset + 8)
		if extra_weight_elements is None:
			if weights[6] != 0 or weights[7] != 0:
				raise MeshProfileError("unsupported-extra-weight-profile")
			indices = primary_indices + (0, 0)
			combined_weights = weights
		else:
			extra_indices = decodeSixU10(
				struct.unpack_from("<Q", extra_weight_elements, offset)[0],
				bone_map_count, 0)
			extra_weights = struct.unpack_from("8B", extra_weight_elements, offset + 8)
			if any(extra_weights[4:]):
				raise MeshProfileError("unsupported-extra-weight-profile")
			indices = primary_indices + extra_indices
			combined_weights = weights + extra_weights[:4]
		active = [
			index for index, weight in zip(indices, combined_weights)
			if weight != 0
		]
		if active:
			weighted_vertices += 1
			weighted_bones.update(active)
			max_influences = max(max_influences, len(active))
			max_error = max(max_error, abs(
				sum(weight / 255.0 for weight in combined_weights) - 1.0))
		index_rows.append(indices)
		weight_rows.append(combined_weights)
	return index_rows, weight_rows, {
		"weighted_vertex_count": weighted_vertices,
		"weighted_bone_count": len(weighted_bones),
		"max_influences": max_influences,
		"weight_sum_max_error": max_error,
	}

def _rangesOverlap(left, right):
	return re_common.ranges_overlap(left, right)

def parsePragmataMeshBufferHeader(data, mesh_offset, streaming_offset=None,
		streaming_entry_count=0):
	mesh_range = _checkedRange(data, mesh_offset, 96, "mesh-header")
	values = struct.unpack_from("<QQQIIHHQQIIhhQQQQ", data, mesh_offset)
	vertex_element_offset = values[0]
	vertex_buffer_offset = values[1]
	total_buffer_size = values[3]
	vertex_buffer_size = values[4]
	main_element_count = values[5]
	element_count = values[6]
	extra_offset0 = values[7]
	extra_offset1 = values[8]
	block2_face_offset = values[9]
	streaming_vertex_element_offset = values[15]
	blend_packed_field = values[13]
	if main_element_count == 0 or element_count == 0 or main_element_count > element_count:
		raise MeshProfileError("structural-profile-mismatch:vertex-element-count")
	if streaming_entry_count:
		if streaming_offset is None:
			raise MeshProfileError(
				"structural-profile-mismatch:streaming-info-offset")
		stream_header_size = struct.calcsize("<QIIHHQQ" + "I" * 11)
		stream_headers_end = mesh_offset + 96 + streaming_entry_count * stream_header_size
		if streaming_offset not in (stream_headers_end, stream_headers_end + 16):
			raise MeshProfileError(
				"structural-profile-mismatch:streaming-info-offset")
		_checkedRange(data, streaming_offset, 16, "streaming-info-header")
		stream_info_count, stream_info_unknown, stream_info_entry_offset = \
			struct.unpack_from("<IIQ", data, streaming_offset)
		if (stream_info_count != streaming_entry_count or
				stream_info_unknown != 0):
			raise MeshProfileError(
				"structural-profile-mismatch:streaming-info-header")
		if stream_info_entry_offset != streaming_offset - 16:
			raise MeshProfileError(
				"structural-profile-mismatch:streaming-info-entry-offset")
		if vertex_element_offset != streaming_offset + 16:
			raise MeshProfileError(
				"structural-profile-mismatch:vertex-element-offset")
		expected_streaming_elements = (
			vertex_element_offset + element_count * 8 + 15) & ~15
		if streaming_vertex_element_offset != expected_streaming_elements:
			raise MeshProfileError(
				"structural-profile-mismatch:streaming-vertex-element-offset")
	elif vertex_element_offset != mesh_offset + 96:
		# Some unstreamed files retain an empty 16-byte streaming-info record.
		if (vertex_element_offset != mesh_offset + 112 or
				streaming_offset != mesh_offset + 96 or
				bytes(data[mesh_offset + 96:mesh_offset + 112]) != bytes(16)):
			raise MeshProfileError("structural-profile-mismatch:vertex-elements-96")
		mesh_range = _checkedRange(data, mesh_offset, 112, "mesh-header")
	for label, value in (("mesh-extra-0", extra_offset0), ("mesh-extra-1", extra_offset1)):
		if value != 0 and value >= len(data):
			raise MeshProfileError("offset-out-of-bounds:" + label)
	if vertex_buffer_size == 0:
		raise MeshProfileError("structural-profile-mismatch:vertex-buffer-size")
	if block2_face_offset <= vertex_buffer_size or total_buffer_size < block2_face_offset:
		raise MeshProfileError("structural-profile-mismatch:face-buffer-size")
	face_buffer_offset = vertex_buffer_offset + vertex_buffer_size
	face_buffer_size = block2_face_offset - vertex_buffer_size
	ranges = {
		"mesh-header": mesh_range,
		"vertex-elements": _checkedRange(data, vertex_element_offset, element_count * 8, "vertex-elements"),
		"vertex-buffer": _checkedRange(data, vertex_buffer_offset, vertex_buffer_size, "vertex-buffer"),
		"face-buffer": _checkedRange(data, face_buffer_offset, face_buffer_size, "face-buffer"),
	}
	total_buffer_range = _checkedRange(data, vertex_buffer_offset, total_buffer_size, "total-buffer")
	for left_index in range(len(PRAGMATA_MESH_RANGE_LABELS)):
		for right_index in range(left_index + 1, len(PRAGMATA_MESH_RANGE_LABELS)):
			left = PRAGMATA_MESH_RANGE_LABELS[left_index]
			right = PRAGMATA_MESH_RANGE_LABELS[right_index]
			if _rangesOverlap(ranges[left], ranges[right]):
				raise MeshProfileError("range-overlap:" + left + ":" + right)
	return {
		"vertex_element_offset": vertex_element_offset,
		"vertex_buffer_offset": vertex_buffer_offset,
		"vertex_buffer_size": vertex_buffer_size,
		"vertex_buffer_range": ranges["vertex-buffer"],
		"total_buffer_range": total_buffer_range,
		"face_buffer_offset": face_buffer_offset,
		"face_buffer_size": face_buffer_size,
		"face_buffer_range": ranges["face-buffer"],
		"main_element_count": main_element_count,
		"element_count": element_count,
		"blend_packed_field": blend_packed_field,
		"blend_payload_relative_offset": blend_packed_field >> 32,
		"streaming_vertex_element_offset": streaming_vertex_element_offset,
	}

def parsePragmataBlendShapeProfile(data, offset):
	_checkedRange(data, offset, 32, "blend-shape-header")
	count, reserved, main_offset, _profile_hash = struct.unpack_from(
		"<QQQQ", data, offset)
	if count <= 0 or count > 64:
		raise MeshProfileError("structural-profile-mismatch:blend-shape-count")
	if reserved != 0:
		raise MeshProfileError("structural-profile-mismatch:blend-shape-reserved")
	if main_offset != offset + 32:
		raise MeshProfileError("structural-profile-mismatch:blend-shape-main-offset")
	_checkedRange(data, main_offset, count * 8, "blend-shape-offset-table")
	name_count = 0
	payload_element_count = 0
	submeshes = []
	targets = []
	shape_indices = []
	profile_encoding_type = None
	payload_stride = None
	for shape_index in range(count):
		shape_offset = struct.unpack_from(
			"<Q", data, main_offset + shape_index * 8)[0]
		_checkedRange(data, shape_offset, 48, "blend-shape-record")
		(target_count, encoding_type, flags, padding1, padding2,
			target_offset, aabb_offset, blend_s_offset,
			blend_ss_offset) = struct.unpack_from("<HHIIIQQQQ", data, shape_offset)
		if target_count <= 0 or target_count > 256:
			raise MeshProfileError("structural-profile-mismatch:blend-target-count")
		if encoding_type not in (1, 2):
			raise MeshProfileError("unsupported-blend-shape-encoding")
		expected_padding1 = 0 if encoding_type == 1 else 1
		if padding1 != expected_padding1 or padding2 != 0:
			raise MeshProfileError("structural-profile-mismatch:blend-shape-padding")
		if (profile_encoding_type is not None and
				encoding_type != profile_encoding_type):
			raise MeshProfileError(
				"structural-profile-mismatch:blend-shape-encoding-mix")
		profile_encoding_type = encoding_type
		payload_stride = 4 if encoding_type == 1 else 8
		_checkedRange(data, target_offset, target_count * 16, "blend-target-table")
		_checkedRange(data, aabb_offset, target_count * 32, "blend-target-aabb")
		_checkedRange(data, blend_s_offset, 12, "blend-shape-scale")
		shape_name_count = 0
		for target_index in range(target_count):
			(blend_ss_index, blend_shape_count, target_reserved, submesh_count,
				target_marker, submesh_offset) = struct.unpack_from(
					"<HHHBBQ", data, target_offset + target_index * 16)
			if blend_shape_count <= 0 or blend_ss_index != shape_name_count:
				raise MeshProfileError(
					"structural-profile-mismatch:blend-shape-name-range")
			if target_reserved != 0:
				raise MeshProfileError(
					"structural-profile-mismatch:blend-target-reserved")
			if target_marker != 1:
				raise MeshProfileError(
					"structural-profile-mismatch:blend-target-marker")
			if submesh_count <= 0:
				raise MeshProfileError(
					"structural-profile-mismatch:blend-submesh-count")
			_checkedRange(
				data, submesh_offset, submesh_count * 16, "blend-submesh-table")
			target_submeshes = []
			target_vertex_count = 0
			for submesh_index in range(submesh_count):
				vertex_start, delta_offset, vertex_count, reserved = struct.unpack_from(
					"<IIII", data, submesh_offset + submesh_index * 16)
				if vertex_count <= 0:
					raise MeshProfileError(
						"structural-profile-mismatch:blend-submesh-vertex-count")
				if delta_offset != target_vertex_count:
					raise MeshProfileError(
						"structural-profile-mismatch:blend-delta-offset")
				expected_reserved = 0 if encoding_type == 1 else 0x100
				if reserved != expected_reserved:
					raise MeshProfileError(
						"structural-profile-mismatch:blend-submesh-reserved")
				descriptor = {
					"vertex_start": vertex_start,
					"delta_offset": delta_offset,
					"vertex_count": vertex_count,
					"reserved": reserved,
				}
				target_submeshes.append(descriptor)
				submeshes.append(descriptor)
				target_vertex_count += vertex_count
			aabb_values = struct.unpack_from(
				"<8f", data, aabb_offset + target_index * 32)
			aabb = {
				"min": tuple(aabb_values[:3]),
				"max": tuple(aabb_values[4:7]),
			}
			if encoding_type == 1:
				decodePragmataBlendDelta(0, aabb)
			else:
				decodePragmataBlendHalfDelta((0, 0, 0, 0), aabb)
			targets.append({
				"record_index": shape_index,
				"target_index": target_index,
				"blend_ss_index": blend_ss_index,
				"shape_count": blend_shape_count,
				"target_marker": target_marker,
				"aabb": aabb,
				"scale": struct.unpack_from(
					"<3I", data, blend_s_offset + target_index * 12),
				"vertex_count": target_vertex_count,
				"payload_element_offset": payload_element_count,
				"submeshes": target_submeshes,
			})
			payload_element_count += blend_shape_count * target_vertex_count
			shape_name_count += blend_shape_count
		if flags != shape_name_count << 16:
			raise MeshProfileError("structural-profile-mismatch:blend-shape-flag")
		_checkedRange(
			data, blend_ss_offset, shape_name_count * 4, "blend-shape-index-table")
		record_shape_indices = list(struct.unpack_from(
			"<" + "I" * shape_name_count, data, blend_ss_offset))
		if record_shape_indices != list(range(name_count, name_count + shape_name_count)):
			raise MeshProfileError(
				"structural-profile-mismatch:blend-shape-index-table")
		shape_indices.extend(record_shape_indices)
		name_count += shape_name_count
	return {
		"count": count,
		"name_count": name_count,
		"shape_count": name_count,
		"encoding_type": profile_encoding_type,
		"payload_stride": payload_stride,
		"payload_size": payload_element_count * payload_stride,
		"shape_indices": shape_indices,
		"submeshes": submeshes,
		"targets": targets,
	}

def _finalizePragmataBlendPayloadProfile(data, blend_shape, mesh_buffer):
	if blend_shape is None:
		return None
	relative_offset = mesh_buffer["blend_payload_relative_offset"]
	if relative_offset <= 0:
		raise MeshProfileError(
			"structural-profile-mismatch:blend-payload-relative-offset")
	element_offsets = []
	for element_index in range(mesh_buffer["element_count"]):
		_element_type, _stride, buffer_offset = struct.unpack_from(
			"<HHI", data,
			mesh_buffer["vertex_element_offset"] + element_index * 8)
		element_offsets.append(buffer_offset)
	if not element_offsets or relative_offset <= max(element_offsets):
		raise MeshProfileError(
			"structural-profile-mismatch:blend-payload-before-vertex-elements")
	payload_end = relative_offset + blend_shape["payload_size"]
	if payload_end > mesh_buffer["vertex_buffer_size"]:
		raise MeshProfileError(
			"structural-profile-mismatch:blend-payload-truncated")
	payload_tail_size = mesh_buffer["vertex_buffer_size"] - payload_end
	allowed_tail_sizes = ((0, 4)
		if blend_shape["encoding_type"] == 1 else (0,))
	if payload_tail_size not in allowed_tail_sizes:
		raise MeshProfileError(
			"structural-profile-mismatch:blend-payload-tail")
	payload_offset = mesh_buffer["vertex_buffer_offset"] + relative_offset
	_checkedRange(data, payload_offset, blend_shape["payload_size"], "blend-payload")
	result = dict(blend_shape)
	result.update({
		"payload_relative_offset": relative_offset,
		"payload_offset": payload_offset,
		"payload_tail_size": payload_tail_size,
		"payload_sha256": hashlib.sha256(bytes(
			data[payload_offset:payload_offset + blend_shape["payload_size"]]
		)).hexdigest(),
	})
	return result

def decodePragmataBlendDelta(packed, aabb):
	minimum = aabb.get("min", ())
	maximum = aabb.get("max", ())
	if (len(minimum) != 3 or len(maximum) != 3 or
			any(not math.isfinite(value) for value in minimum + maximum) or
			any(minimum[axis] > maximum[axis] for axis in range(3))):
		raise MeshProfileError(
			"structural-profile-mismatch:blend-target-aabb")
	quantized = (
		packed & 0x7FF,
		(packed >> 11) & 0x3FF,
		(packed >> 21) & 0x7FF,
	)
	maximum_quantized = (2047.0, 1023.0, 2047.0)
	result = tuple(
		minimum[axis] + quantized[axis] *
		(maximum[axis] - minimum[axis]) / maximum_quantized[axis]
		for axis in range(3)
	)
	if any(not math.isfinite(value) for value in result):
		raise MeshProfileError(
			"structural-profile-mismatch:blend-target-aabb")
	return result

def _meshHalfBitsToFloat(bits):
	sign = -1.0 if bits & 0x8000 else 1.0
	exponent = (bits >> 10) & 0x1F
	fraction = bits & 0x3FF
	if exponent == 0x1F:
		raise MeshProfileError(
			"structural-profile-mismatch:blend-half-nonfinite")
	if exponent == 0:
		return sign * math.ldexp(float(fraction), -24)
	return sign * math.ldexp(float(0x400 + fraction), exponent - 25)

def decodePragmataBlendHalfDelta(raw_components, aabb):
	if len(raw_components) != 4 or raw_components[3] != 0:
		raise MeshProfileError(
			"structural-profile-mismatch:blend-half-padding")
	minimum = aabb.get("min", ())
	maximum = aabb.get("max", ())
	if (len(minimum) != 3 or len(maximum) != 3 or
			any(not math.isfinite(value) for value in minimum + maximum) or
			any(minimum[axis] > maximum[axis] for axis in range(3))):
		raise MeshProfileError(
			"structural-profile-mismatch:blend-target-aabb")
	result = tuple(
		_meshHalfBitsToFloat(raw_components[axis])
		for axis in range(3)
	)
	if any(result[axis] < minimum[axis] or result[axis] > maximum[axis]
			for axis in range(3)):
		raise MeshProfileError(
			"structural-profile-mismatch:blend-half-out-of-range")
	return result

def _pragmataNeutralBlendValue(aabb):
	maximum_quantized = (2047, 1023, 2047)
	quantized = []
	for axis in range(3):
		minimum = aabb["min"][axis]
		maximum = aabb["max"][axis]
		if maximum == minimum:
			value = 0
		else:
			value = int((0.0 - minimum) * maximum_quantized[axis] /
				(maximum - minimum))
		value = max(0, min(maximum_quantized[axis], value))
		quantized.append(value)
	return (quantized[0] | (quantized[1] << 11) |
		(quantized[2] << 21))

def _decodePragmataBlendShapes(data, blend_shape, blend_shape_names):
	if blend_shape is None:
		return []
	if (len(blend_shape_names) != blend_shape["shape_count"] or
			len(set(blend_shape_names)) != len(blend_shape_names)):
		raise MeshProfileError(
			"structural-profile-mismatch:blend-shape-name-identity")
	result = []
	payload_offset = blend_shape["payload_offset"]
	encoding_type = blend_shape["encoding_type"]
	payload_stride = blend_shape["payload_stride"]
	for target in blend_shape["targets"]:
		neutral = (_pragmataNeutralBlendValue(target["aabb"])
			if encoding_type == 1 else None)
		for local_shape_index in range(target["shape_count"]):
			name_table_index = target["blend_ss_index"] + local_shape_index
			shape_index = blend_shape["shape_indices"][name_table_index]
			for submesh in target["submeshes"]:
				element_offset = (
					target["payload_element_offset"] +
					local_shape_index * target["vertex_count"] +
					submesh["delta_offset"]
				)
				packed_offset = payload_offset + element_offset * payload_stride
				packed_size = submesh["vertex_count"] * payload_stride
				_checkedRange(data, packed_offset, packed_size, "blend-shape-deltas")
				packed_bytes = bytes(data[packed_offset:packed_offset + packed_size])
				deltas = []
				non_neutral_count = 0
				for vertex_index in range(submesh["vertex_count"]):
					if encoding_type == 1:
						packed = struct.unpack_from(
							"<I", packed_bytes, vertex_index * 4)[0]
						if packed != neutral:
							non_neutral_count += 1
						delta = decodePragmataBlendDelta(packed, target["aabb"])
					else:
						raw_components = struct.unpack_from(
							"<4H", packed_bytes, vertex_index * 8)
						if any(value & 0x7FFF for value in raw_components[:3]):
							non_neutral_count += 1
						delta = decodePragmataBlendHalfDelta(
							raw_components, target["aabb"])
					deltas.append(delta)
				delta_bytes = b"".join(
					struct.pack("<3f", *delta) for delta in deltas)
				result.append({
					"name": blend_shape_names[shape_index],
					"shape_index": shape_index,
					"target_index": target["target_index"],
					"vertex_start": submesh["vertex_start"],
					"vertex_count": submesh["vertex_count"],
					"deltas": tuple(deltas),
					"aabb": target["aabb"],
					"packed_sha256": hashlib.sha256(packed_bytes).hexdigest(),
					"delta_sha256": hashlib.sha256(delta_bytes).hexdigest(),
					"non_neutral_count": non_neutral_count,
				})
	return result

def parsePragmataHeader(data, path):
	capability = _detectPragmataIdentity(data, path)
	if capability != PRAGMATA_250707828:
		raise MeshProfileError("unsupported-mesh-profile")
	header = {
		"capability": capability,
		"name_count": _readMeshScalar(data, 0x14, "<H", "name_count"),
	}
	if header["name_count"] == 0:
		raise MeshProfileError("structural-profile-mismatch:name-count")
	for label, offset in PRAGMATA_HEADER_FIELDS:
		value = _readMeshScalar(data, offset, "<Q", label)
		if label in ("blend_shape_offset", "blend_name_offset", "aabb_offset",
				"skeleton_offset", "bone_remap_offset"):
			if value >= len(data):
				raise MeshProfileError("offset-out-of-bounds:" + label)
		elif value <= 0 or value >= len(data):
			raise MeshProfileError("offset-out-of-bounds:" + label)
		header[label] = value
	if header["skeleton_offset"]:
		for label in ("bone_remap_offset", "aabb_offset"):
			if not header[label]:
				raise MeshProfileError("offset-out-of-bounds:" + label)
	elif any(header[label] for label in (
			"bone_remap_offset", "aabb_offset", "blend_shape_offset", "blend_name_offset")):
		raise MeshProfileError("structural-profile-mismatch:static-skeleton-offsets")
	if bool(header["blend_shape_offset"]) != bool(header["blend_name_offset"]):
		raise MeshProfileError("structural-profile-mismatch:blend-shape-offset-pair")
	header["blend_shape"] = (
		parsePragmataBlendShapeProfile(data, header["blend_shape_offset"])
		if header["blend_shape_offset"] else None
	)
	if header["names_offset"] + header["name_count"] * 8 > len(data):
		raise MeshProfileError("offset-out-of-bounds:name-table")
	header["streaming_entry_count"] = _readMeshScalar(
		data, header["streaming_offset"], "<I", "streaming-entry-count")
	header["mesh_buffer"] = parsePragmataMeshBufferHeader(
		data, header["mesh_offset"], header["streaming_offset"],
		header["streaming_entry_count"])
	header["blend_shape"] = _finalizePragmataBlendPayloadProfile(
		data, header["blend_shape"], header["mesh_buffer"])
	if header["vertices_offset"] != header["mesh_buffer"]["vertex_buffer_offset"]:
		raise MeshProfileError("structural-profile-mismatch:vertices-offset")
	return header

def parsePragmataMplyHeader(data, path):
	capability = _detectPragmataIdentity(data, path)
	if capability != PRAGMATA_MPLY_250707828:
		raise MeshProfileError("unsupported-mesh-profile")
	name_count = _readMeshScalar(data, 0x14, "<H", "name-count")
	if name_count <= 0:
		raise MeshProfileError("structural-profile-mismatch:name-count")
	pointers = {}
	for label, offset in (
			("gpu-meshlet", 0x28),
			("meshlet-layout", 0x38),
			("meshlet-bvh", 0x40),
			("meshlet-parts", 0x48),
			("material-remap", 0x80),
			("names", 0x98),
			("streaming", 0xA0),
			("sdf-path", 0xA8)):
		value = _readMeshScalar(data, offset, "<Q", label)
		if (value == 0 and label != "sdf-path") or value >= len(data):
			raise MeshProfileError("offset-out-of-bounds:" + label)
		pointers[label] = value
	_checkedRange(data, pointers["names"], name_count * 8, "name-table")

	meshlet_layout = pointers["meshlet-layout"]
	_checkedRange(data, meshlet_layout, 144, "meshlet-layout")
	if _readMeshScalar(data, meshlet_layout, "<Q", "layout-gpu-meshlet") != pointers["gpu-meshlet"]:
		raise MeshProfileError("structural-profile-mismatch:gpu-meshlet-offset")
	lod_count = _readMeshScalar(data, meshlet_layout + 20, "<B", "lod-count")
	if lod_count <= 0 or lod_count > 8:
		raise MeshProfileError("structural-profile-mismatch:lod-count")
	lod_offsets = list(struct.unpack_from("<8I", data, meshlet_layout + 40))
	if any(offset <= 0 for offset in lod_offsets[:lod_count]):
		raise MeshProfileError("structural-profile-mismatch:lod-cluster-offset")

	meshlet_bvh = pointers["meshlet-bvh"]
	_checkedRange(data, meshlet_bvh, 64, "meshlet-bvh")
	cluster_headers_offset, quantize_centers_offset = struct.unpack_from(
		"<QQ", data, meshlet_bvh)
	_checkedRange(data, cluster_headers_offset, 1, "cluster-headers")
	_checkedRange(data, quantize_centers_offset, 1, "quantize-centers")
	bvh_offset = struct.unpack_from("<3f", data, meshlet_bvh + 16)
	bvh_scale = _readMeshScalar(data, meshlet_bvh + 28, "<f", "meshlet-bvh-scale")
	if (any(not math.isfinite(value) for value in bvh_offset) or
			not math.isfinite(bvh_scale) or bvh_scale <= 0.0):
		raise MeshProfileError("structural-profile-mismatch:meshlet-bvh-transform")
	# Observed newer clusters store per-LOD count/flags and independent offsets.
	# Their 4/8-unit quantization families share the bounded packed decoder.
	if bvh_scale in (3.99993896484375, 7.9998779296875):
		result = _parsePackedMplyHeader(data, capability)
		result["packed_mply_layout"] = True
		return result
	if abs((bvh_scale + (1.0 / 2048.0)) - 32.0) > 1.0e-7:
		raise MeshProfileError("unsupported-meshlet-quantization-scale")
	cluster_counts = list(struct.unpack_from("<8I", data, meshlet_bvh + 32))
	if any(count <= 0 for count in cluster_counts[:lod_count]):
		raise MeshProfileError("structural-profile-mismatch:cluster-count")
	if any(cluster_counts[lod_count:]):
		raise MeshProfileError("structural-profile-mismatch:unused-cluster-count")
	total_clusters = sum(cluster_counts)
	_checkedRange(data, cluster_headers_offset, total_clusters * 16, "cluster-headers")
	_checkedRange(data, quantize_centers_offset, total_clusters * 6, "quantize-centers")

	streaming_offset = pointers["streaming"]
	streaming_count, _streaming_unknown, streaming_entry_offset = struct.unpack_from(
		"<IIQ", data, streaming_offset)
	if streaming_count != 1:
		raise MeshProfileError("unsupported-streaming-entry-count")
	_checkedRange(data, streaming_entry_offset, 8, "streaming-info-entry")
	streaming_start, streaming_size = struct.unpack_from("<II", data, streaming_entry_offset)
	if streaming_size <= 0:
		raise MeshProfileError("structural-profile-mismatch:streaming-buffer-size")

	return {
		"capability": capability,
		"name_count": name_count,
		"names_offset": pointers["names"],
		"gpu_meshlet_offset": pointers["gpu-meshlet"],
		"lod_count": lod_count,
		"lod_offsets": lod_offsets[:lod_count],
		"cluster_counts": cluster_counts[:lod_count],
		"cluster_headers_offset": cluster_headers_offset,
		"quantize_centers_offset": quantize_centers_offset,
		"bvh_offset": bvh_offset,
		"bvh_scale": bvh_scale,
		"streaming_start": streaming_start,
		"streaming_size": streaming_size,
	}

def parseWildsMplyHeader(data, path):
	"""Read the bounded Wilds MPLY tables needed by the cluster decoder."""
	capability = detectWildsMeshIdentity(data, path)
	if capability != WILDS_MPLY_240704828:
		raise MeshProfileError("unsupported-mesh-profile")
	return _parsePackedMplyHeader(data, capability)


def _parsePackedMplyHeader(data, capability):
	name_count = _readMeshScalar(data, 0x14, "<H", "name-count")
	if name_count <= 0:
		raise MeshProfileError("structural-profile-mismatch:name-count")
	pointers = {}
	for label, offset in (
			("gpu-meshlet", 0x28), ("meshlet-layout", 0x38),
			("meshlet-bvh", 0x40), ("meshlet-parts", 0x48),
			("material-remap", 0x80), ("names", 0x98),
			("streaming", 0xA0)):
		value = _readMeshScalar(data, offset, "<Q", label)
		if value <= 0 or value >= len(data):
			raise MeshProfileError("offset-out-of-bounds:" + label)
		pointers[label] = value
	_checkedRange(data, pointers["names"], name_count * 8, "name-table")

	layout = pointers["meshlet-layout"]
	_checkedRange(data, layout, 160, "meshlet-layout")
	if _readMeshScalar(data, layout, "<Q", "layout-gpu-meshlet") != pointers["gpu-meshlet"]:
		raise MeshProfileError("structural-profile-mismatch:gpu-meshlet-offset")
	lod_count = _readMeshScalar(data, layout + 20, "<B", "lod-count")
	if not 1 <= lod_count <= 8:
		raise MeshProfileError("structural-profile-mismatch:lod-count")
	lod_offsets = list(struct.unpack_from("<8I", data, layout + 40))
	if any(offset <= 0 for offset in lod_offsets[:lod_count]):
		raise MeshProfileError("structural-profile-mismatch:lod-cluster-offset")
	if any(lod_offsets[lod_count:]):
		raise MeshProfileError("structural-profile-mismatch:unused-lod-cluster-offset")

	bvh = pointers["meshlet-bvh"]
	_checkedRange(data, bvh, 128, "meshlet-bvh")
	cluster_headers_offset, quantize_centers_offset = struct.unpack_from("<QQ", data, bvh)
	bvh_offset = struct.unpack_from("<3f", data, bvh + 16)
	bvh_scale = _readMeshScalar(data, bvh + 28, "<f", "meshlet-bvh-scale")
	if (any(not math.isfinite(value) for value in bvh_offset) or
			not math.isfinite(bvh_scale) or bvh_scale <= 0.0):
		raise MeshProfileError("structural-profile-mismatch:meshlet-bvh-transform")
	cluster_counts = []
	for index in range(8):
		count, _unknown0, _unknown1 = struct.unpack_from("<HBB", data, bvh + 32 + index * 4)
		cluster_counts.append(count)
	if any(count <= 0 for count in cluster_counts[:lod_count]) or any(cluster_counts[lod_count:]):
		raise MeshProfileError("structural-profile-mismatch:cluster-count")
	cluster_offsets = list(struct.unpack_from("<8I", data, bvh + 64))
	for index in range(lod_count):
		_checkedRange(data, cluster_headers_offset + cluster_offsets[index],
			cluster_counts[index] * 16, "cluster-headers")
	_checkedRange(data, quantize_centers_offset, sum(cluster_counts) * 6,
		"quantize-centers")

	streaming_count, streaming_unknown, streaming_entry_offset = struct.unpack_from(
		"<IIQ", data, pointers["streaming"])
	if streaming_count != 1 or streaming_unknown != 0:
		raise MeshProfileError("unsupported-streaming-entry-count")
	_checkedRange(data, streaming_entry_offset, 8, "streaming-info-entry")
	streaming_start, streaming_size = struct.unpack_from("<II", data, streaming_entry_offset)
	if streaming_size <= 0:
		raise MeshProfileError("structural-profile-mismatch:streaming-buffer-size")
	return {
		"capability": capability,
		"name_count": name_count,
		"names_offset": pointers["names"],
		"gpu_meshlet_offset": pointers["gpu-meshlet"],
		"lod_count": lod_count,
		"lod_offsets": lod_offsets[:lod_count],
		"cluster_counts": cluster_counts[:lod_count],
		"cluster_offsets": cluster_offsets[:lod_count],
		"cluster_headers_offset": cluster_headers_offset,
		"quantize_centers_offset": quantize_centers_offset,
		"bvh_offset": bvh_offset,
		"bvh_scale": bvh_scale,
		"streaming_start": streaming_start,
		"streaming_size": streaming_size,
	}

def _meshFloat32(value):
	return re_common.float32(value, MeshProfileError)

def _decodePragmataMplyPositions(position_data, vertex_count, flags, center, scale):
	if flags & 0x2000:
		stride = 3
		offsets = (
			tuple((0.0 - 0.5) * scale for _axis in range(3))
			for _index in range(vertex_count)
		)
	elif flags & 0x1000:
		stride = 4
		def packedOffsets():
			for index in range(vertex_count):
				packed = struct.unpack_from("<I", position_data, index * stride)[0]
				values = (packed & 0x3FF, (packed >> 10) & 0x3FF,
					(packed >> 20) & 0x3FF)
				yield tuple((float(value) - 0.5) * scale for value in values)
		offsets = packedOffsets()
	else:
		stride = 6
		def normalizedOffsets():
			for index in range(vertex_count):
				raw = struct.unpack_from("<3H", position_data, index * stride)
				result = []
				for value in raw:
					normalized = _meshFloat32(
						_meshFloat32(value) / _meshFloat32(65535.0))
					centered = _meshFloat32(
						normalized - _meshFloat32(0.5))
					result.append(_meshFloat32(
						centered * _meshFloat32(scale)))
				yield tuple(result)
		offsets = normalizedOffsets()
	_checkedRange(position_data, 0, vertex_count * stride, "meshlet-position-buffer")
	positions = []
	for offset in offsets:
		position = tuple(center[axis] + offset[axis] for axis in range(3))
		if any(not math.isfinite(coordinate) for coordinate in position):
			raise MeshProfileError("structural-profile-mismatch:non-finite-position")
		positions.append(position)
	return positions

def _decodeWildsMplyPositions(position_data, vertex_count, flags, part_center,
		bbox_center):
	"""Decode the observed Wilds 16-bit and 10:10:10 position layouts."""
	if flags & 0x2000:
		raise MeshProfileError("unsupported-meshlet-24bit-position-layout")
	stride = 4 if flags & 0x1000 else 6
	_checkedRange(position_data, 0, vertex_count * stride, "meshlet-position-buffer")
	div_byte = (flags >> 24) & 0xFF
	mult_byte = (flags >> 16) & 0xFF
	scale = math.ldexp(1.0, div_byte - 127)
	relative_scale = math.ldexp(1.0, mult_byte - div_byte)
	relative = tuple(value / 65535.0 - 0.5 for value in bbox_center)
	positions = []
	for index in range(vertex_count):
		if stride == 4:
			packed = struct.unpack_from("<I", position_data, index * 4)[0]
			raw = (packed & 0x3FF, (packed >> 10) & 0x3FF,
				(packed >> 20) & 0x3FF)
		else:
			raw = tuple(
				_meshFloat32(_meshFloat32(value) / _meshFloat32(65535.0))
				for value in struct.unpack_from("<3H", position_data, index * 6))
		centered = tuple(
			_meshFloat32(raw[axis] - _meshFloat32(0.5))
			if stride == 6 else raw[axis] - 0.5 for axis in range(3))
		position = tuple(
			(centered[axis] + relative[axis] * relative_scale) * scale +
			part_center[axis] for axis in range(3))
		if any(not math.isfinite(value) for value in position):
			raise MeshProfileError("structural-profile-mismatch:non-finite-position")
		positions.append(position)
	return positions

def _meshTopologyHash(positions, indices):
	return re_common.topology_hash(positions, indices, MeshProfileError)

def _meshHalfAwayFromZero(value):
	return re_common.round_half_away_from_zero(value, MeshProfileError)

def _meshQuantizeSnorm(value):
	return re_common.quantize_snorm(value, MeshProfileError)

def _meshQuantizeColor(value):
	return re_common.quantize_color(value, MeshProfileError)

def _meshRoundShiftRightToEven(value, shift):
	return re_common.round_shift_right_to_even(value, shift)

def _meshFloatToHalfBits(value):
	return re_common.float_to_half_bits(value, MeshProfileError)

def _meshQuantizeWeights(values):
	return re_common.quantize_weights(values, MeshProfileError)

def _meshPackSixU10(slots, bone_map_count):
	return re_common.pack_six_u10(
		slots, bone_map_count, 3, MeshProfileError)

def _meshValidateVector(value, count, token):
	return re_common.validate_vector(value, count, token, MeshProfileError)

def _meshTransformPointRowVector(position, matrix):
	return re_common.transform_point_row_vector(position, matrix)

def _readPragmataCString(data, offset, label):
	_checkedRange(data, offset, 1, label)
	end = data.find(b"\0", offset)
	if end == -1:
		raise MeshProfileError("offset-out-of-bounds:" + label)
	try:
		return bytes(data[offset:end]).decode("utf-8")
	except UnicodeDecodeError:
		raise MeshProfileError("structural-profile-mismatch:" + label)

def _newPragmataImportStats(capability):
	return {
		"schema": "noesis-mesh-stats/v1",
		"capability": capability.key,
		"lod_count": 0,
		"group_count": 0,
		"submesh_count": 0,
		"vertex_count": 0,
		"index_count": 0,
		"triangle_count": 0,
		"normal_count": 0,
		"tangent_count": 0,
		"uv_count": 0,
		"color_count": 0,
		"material_binding_count": 0,
		"bone_count": 0,
		"weighted_bone_count": 0,
		"weighted_vertex_count": 0,
		"max_influences": 0,
		"weight_sum_max_error": 0.0,
		"aabb": None,
		"topology_hash": None,
	}

def _parsePragmataMplyData(data, header, streaming_data=None):
	if header.get("capability") != PRAGMATA_MPLY_250707828:
		raise MeshProfileError("unsupported-mesh-profile")
	if header.get("packed_mply_layout"):
		return _parsePackedMplyData(data, header, streaming_data)
	if streaming_data is None:
		raise MeshProfileError("missing-streaming-companion")
	streaming_start = header["streaming_start"]
	streaming_size = header["streaming_size"]
	_checkedRange(streaming_data, streaming_start, streaming_size, "streaming-buffer")
	if streaming_start + streaming_size != len(streaming_data):
		raise MeshProfileError("structural-profile-mismatch:streaming-buffer-size")

	material_names = []
	for index in range(header["name_count"]):
		name_offset = struct.unpack_from("<Q", data, header["names_offset"] + index * 8)[0]
		material_names.append(_readPragmataCString(data, name_offset, "material-name"))
	if len(set(material_names)) != len(material_names):
		raise MeshProfileError("structural-profile-mismatch:duplicate-material-name")

	positions = []
	indices = []
	normal_parts = []
	uv_parts = []
	color_parts = []
	submeshes = []
	groups = []
	cluster_global_index = 0
	gpu_base = header["gpu_meshlet_offset"]
	for lod_index in range(header["lod_count"]):
		cluster_count = header["cluster_counts"][lod_index]
		lod_table_offset = gpu_base + header["lod_offsets"][lod_index]
		_checkedRange(data, lod_table_offset, 4 + cluster_count * 4, "meshlet-lod-table")
		if struct.unpack_from("<I", data, lod_table_offset)[0] != cluster_count:
			raise MeshProfileError("structural-profile-mismatch:cluster-count")
		entry_offsets = struct.unpack_from(
			"<" + "I" * cluster_count, data, lod_table_offset + 4)
		lod_vertex_start = len(positions)
		lod_index_start = len(indices)
		for cluster_index, entry_relative in enumerate(entry_offsets):
			compact_offset = header["cluster_headers_offset"] + cluster_global_index * 16
			bitfield, vertex_relative, index_relative = struct.unpack_from(
				"<QII", data, compact_offset)
			vertex_count = bitfield & 0xFF
			index_count = (bitfield >> 8) & 0x3FF
			material_index = (bitfield >> 23) & 0xFF
			if vertex_count <= 0 or vertex_count > 128:
				raise MeshProfileError("structural-profile-mismatch:meshlet-vertex-count")
			if index_count <= 0 or index_count % 3:
				raise MeshProfileError("structural-profile-mismatch:index-count")
			if material_index >= len(material_names):
				raise MeshProfileError("structural-profile-mismatch:material-index")

			entry_offset = gpu_base + entry_relative
			_checkedRange(data, entry_offset, 32 + index_count, "meshlet-cluster-entry")
			part_center = struct.unpack_from("<3f", data, entry_offset)
			if any(not math.isfinite(value) for value in part_center):
				raise MeshProfileError("structural-profile-mismatch:meshlet-part-center")
			center_offset = header["quantize_centers_offset"] + cluster_global_index * 6
			center_raw = struct.unpack_from("<3H", data, center_offset)
			quantize_scale = header["bvh_scale"] + (1.0 / 2048.0)
			center = tuple(
				part_center[axis] +
				(center_raw[axis] / 65535.0 - 0.5) * quantize_scale
				for axis in range(3)
			)
			metadata_count = struct.unpack_from("<I", data, entry_offset + 12)[0]
			if ((metadata_count & 0xFF) != vertex_count or
					((metadata_count >> 8) & 0xFF) * 3 != index_count):
				raise MeshProfileError("structural-profile-mismatch:meshlet-entry-count")
			flags = struct.unpack_from("<I", data, entry_offset + 28)[0]
			if flags not in PRAGMATA_MPLY_VERTEX_FLAGS:
				raise MeshProfileError("unsupported-meshlet-vertex-layout")
			embedded_indices = list(data[entry_offset + 32:entry_offset + 32 + index_count])
			if any(index >= vertex_count for index in embedded_indices):
				raise MeshProfileError("index-out-of-range")

			stream_index_offset = streaming_start + index_relative
			_checkedRange(streaming_data, stream_index_offset, index_count * 2,
				"streaming-index-buffer")
			stream_indices = list(struct.unpack_from(
				"<" + "H" * index_count, streaming_data, stream_index_offset))
			if stream_indices != embedded_indices:
				raise MeshProfileError("streaming-index-copy-mismatch")

			position_stride = 3 if flags & 0x2000 else 4 if flags & 0x1000 else 6
			position_offset = gpu_base + vertex_relative
			position_size = position_stride * vertex_count
			_checkedRange(data, position_offset, position_size, "meshlet-position-buffer")
			cluster_positions = _decodePragmataMplyPositions(
				bytes(data[position_offset:position_offset + position_size]),
				vertex_count, flags, center, quantize_scale)
			normal_offset = (position_offset + position_size + 3) & ~3
			normal_size = vertex_count * 8
			uv_offset = normal_offset + normal_size
			uv_size = vertex_count * 4
			uv2_offset = uv_offset + uv_size
			_checkedRange(data, normal_offset, normal_size, "meshlet-normal-buffer")
			_checkedRange(data, uv_offset, uv_size, "meshlet-uv-buffer")
			_checkedRange(data, uv2_offset, uv_size, "meshlet-uv2-buffer")

			vertex_start = len(positions)
			positions.extend(cluster_positions)
			indices.extend(index + vertex_start for index in embedded_indices)
			normal_parts.append(bytes(data[normal_offset:normal_offset + normal_size]))
			uv_parts.append(bytes(data[uv_offset:uv_offset + uv_size]))
			color_parts.append(bytes((255, 255, 255, 255)) * vertex_count)
			submeshes.append({
				"lod_index": lod_index,
				"group_id": 0,
				"submesh_index": cluster_index,
				"material_index": material_index,
				"vertex_start": vertex_start,
				"vertex_count": vertex_count,
				"index_count": index_count,
				"indices": embedded_indices,
				"index_buffer": struct.pack(
					"<" + "H" * index_count, *embedded_indices),
			})
			cluster_global_index += 1
		groups.append({
			"lod_index": lod_index,
			"group_id": 0,
			"submesh_count": cluster_count,
			"vertex_count": len(positions) - lod_vertex_start,
			"index_count": len(indices) - lod_index_start,
		})

	if cluster_global_index != sum(header["cluster_counts"]):
		raise MeshProfileError("structural-profile-mismatch:cluster-count")
	if not positions:
		raise MeshProfileError("structural-profile-mismatch:vertex-count")
	position_buffer = b"".join(struct.pack("<3f", *position) for position in positions)
	normal_buffer = b"".join(normal_parts)
	uv_buffer = b"".join(uv_parts)
	color_buffer = b"".join(color_parts)
	vertex_buffer = position_buffer + normal_buffer + uv_buffer + color_buffer
	vertex_elements = {
		0: {"type": 0, "stride": 12, "offset": 0},
		1: {"type": 1, "stride": 8, "offset": len(position_buffer)},
		2: {"type": 2, "stride": 4,
			"offset": len(position_buffer) + len(normal_buffer)},
		5: {"type": 5, "stride": 4,
			"offset": len(position_buffer) + len(normal_buffer) + len(uv_buffer)},
	}
	mins = [min(position[axis] for position in positions) for axis in range(3)]
	maxs = [max(position[axis] for position in positions) for axis in range(3)]
	stats = _newPragmataImportStats(PRAGMATA_MPLY_250707828)
	stats.update({
		"lod_count": header["lod_count"],
		"group_count": header["lod_count"],
		"submesh_count": len(submeshes),
		"vertex_count": len(positions),
		"index_count": len(indices),
		"triangle_count": len(indices) // 3,
		"normal_count": len(positions),
		"tangent_count": len(positions),
		"uv_count": len(positions),
		"color_count": len(positions),
		"material_binding_count": len(submeshes),
		"aabb": {"min": mins, "max": maxs},
		"topology_hash": _meshTopologyHash(positions, indices),
	})
	return {
		"stats": stats,
		"positions": positions,
		"indices": indices,
		"groups": groups,
		"submeshes": submeshes,
		"vertex_buffer": vertex_buffer,
		"vertex_elements": vertex_elements,
		"bone_indices": [],
		"bone_weights": [],
		"bone_map": [],
		"bones": [],
		"material_names": material_names,
	}

def parseWildsMplyData(data, header, streaming_data=None):
	"""Normalize observed Wilds MPLY clusters for shared Noesis submission."""
	if header.get("capability") != WILDS_MPLY_240704828:
		raise MeshProfileError("unsupported-mesh-profile")
	return _parsePackedMplyData(data, header, streaming_data)


def _parsePackedMplyData(data, header, streaming_data=None):
	if streaming_data is None:
		raise MeshProfileError("missing-streaming-companion")
	streaming_start = header["streaming_start"]
	streaming_size = header["streaming_size"]
	_checkedRange(streaming_data, streaming_start, streaming_size, "streaming-buffer")
	if streaming_start + streaming_size != len(streaming_data):
		raise MeshProfileError("structural-profile-mismatch:streaming-buffer-size")

	material_names = []
	for index in range(header["name_count"]):
		name_offset = _readMeshScalar(
			data, header["names_offset"] + index * 8, "<Q", "material-name-pointer")
		name = _readPragmataCString(data, name_offset, "material-name")
		if not name:
			raise MeshProfileError("structural-profile-mismatch:empty-material-name")
		material_names.append(name)

	positions, indices = [], []
	normal_parts, uv_parts, color_parts = [], [], []
	submeshes, groups = [], []
	has_color = False
	tangent_count = 0
	cluster_global_index = 0
	gpu_base = header["gpu_meshlet_offset"]
	for lod_index in range(header["lod_count"]):
		cluster_count = header["cluster_counts"][lod_index]
		lod_table_offset = gpu_base + header["lod_offsets"][lod_index]
		_checkedRange(data, lod_table_offset, 4 + cluster_count * 4, "meshlet-lod-table")
		if _readMeshScalar(data, lod_table_offset, "<I", "meshlet-lod-count") != cluster_count:
			raise MeshProfileError("structural-profile-mismatch:cluster-count")
		entry_offsets = struct.unpack_from(
			"<" + "I" * cluster_count, data, lod_table_offset + 4)
		lod_vertex_start, lod_index_start = len(positions), len(indices)
		for cluster_index, entry_relative in enumerate(entry_offsets):
			compact_offset = (header["cluster_headers_offset"] +
				header["cluster_offsets"][lod_index] + cluster_index * 16)
			bitfield, vertex_relative, index_relative = struct.unpack_from(
				"<QII", data, compact_offset)
			vertex_count = bitfield & 0xFF
			index_count = (bitfield >> 8) & 0x1FF
			material_index = (bitfield >> 23) & 0xFF
			if not 1 <= vertex_count <= 255:
				raise MeshProfileError("structural-profile-mismatch:meshlet-vertex-count")
			if index_count <= 0 or index_count % 3:
				raise MeshProfileError("structural-profile-mismatch:index-count")
			if material_index >= len(material_names):
				raise MeshProfileError("structural-profile-mismatch:material-index")

			entry_offset = gpu_base + entry_relative
			_checkedRange(data, entry_offset, 32 + index_count, "meshlet-cluster-entry")
			part_center = struct.unpack_from("<3f", data, entry_offset)
			if any(not math.isfinite(value) for value in part_center):
				raise MeshProfileError("structural-profile-mismatch:meshlet-part-center")
			entry_vertex_count, face_count, entry_material, _part_index = \
				struct.unpack_from("<4B", data, entry_offset + 12)
			if (entry_vertex_count != vertex_count or face_count * 3 != index_count or
					entry_material != material_index):
				raise MeshProfileError("structural-profile-mismatch:meshlet-entry-count")
			bbox_values = struct.unpack_from("<6H", data, entry_offset + 16)
			bbox_center = (bbox_values[0], bbox_values[2], bbox_values[4])
			flags = _readMeshScalar(data, entry_offset + 28, "<I", "meshlet-flags")
			if flags & 0x800:
				raise MeshProfileError("unsupported-meshlet-skin-layout")
			embedded_indices = list(
				data[entry_offset + 32:entry_offset + 32 + index_count])
			if any(index >= vertex_count for index in embedded_indices):
				raise MeshProfileError("index-out-of-range")

			stream_index_offset = streaming_start + index_relative
			_checkedRange(streaming_data, stream_index_offset, index_count * 2,
				"streaming-index-buffer")
			stream_indices = list(struct.unpack_from(
				"<" + "H" * index_count, streaming_data, stream_index_offset))
			if stream_indices != embedded_indices:
				raise MeshProfileError("streaming-index-copy-mismatch")

			position_stride = 3 if flags & 0x2000 else 4 if flags & 0x1000 else 6
			position_offset = gpu_base + vertex_relative
			position_size = position_stride * vertex_count
			_checkedRange(data, position_offset, position_size, "meshlet-position-buffer")
			cluster_positions = _decodeWildsMplyPositions(
				bytes(data[position_offset:position_offset + position_size]),
				vertex_count, flags, part_center, bbox_center)
			cursor = (position_offset + position_size + 3) & ~3
			normal_stride = 4 if flags & 0x40 else 8
			normal_size = normal_stride if flags & 0x1 else vertex_count * normal_stride
			_checkedRange(data, cursor, normal_size, "meshlet-normal-buffer")
			raw_normals = bytes(data[cursor:cursor + normal_size])
			if flags & 0x1:
				raw_normals *= vertex_count
			if normal_stride == 4:
				normal_parts.append(b"".join(
					raw_normals[index:index + 4] + b"\0\0\0\x7f"
					for index in range(0, len(raw_normals), 4)))
			else:
				normal_parts.append(raw_normals)
				tangent_count += vertex_count
			cursor += normal_size
			# PRAGMATA's packed profile stores UVs directly after normals even
			# when this flag is set; Wilds has the separate tangent bitset.
			if flags & 0x8000 and not header.get("packed_mply_layout"):
				tangent_bits_size = ((vertex_count + 31) // 32) * 4
				_checkedRange(data, cursor, tangent_bits_size, "meshlet-tangent-bits")
				cursor += tangent_bits_size
			uv_size = vertex_count * 4
			stored_uv_size = 4 if flags & 0x2 else uv_size
			_checkedRange(data, cursor, stored_uv_size, "meshlet-uv-buffer")
			raw_uv = bytes(data[cursor:cursor + stored_uv_size])
			uv_parts.append(raw_uv * vertex_count if flags & 0x2 else raw_uv)
			cursor += stored_uv_size
			for use_flag, compressed_flag, label in (
					(0x200, 0x4, "meshlet-uv2-buffer"),
					(0x400, 0x8, "meshlet-uv3-buffer")):
				if flags & use_flag:
					stored_size = 4 if flags & compressed_flag else uv_size
					_checkedRange(data, cursor, stored_size, label)
					cursor += stored_size
			if flags & 0x100:
				stored_color_size = 4 if flags & 0x10 else uv_size
				_checkedRange(data, cursor, stored_color_size, "meshlet-color-buffer")
				raw_color = bytes(data[cursor:cursor + stored_color_size])
				color_parts.append(
					raw_color * vertex_count if flags & 0x10 else raw_color)
				has_color = True
			else:
				color_parts.append(bytes((255, 255, 255, 255)) * vertex_count)

			vertex_start = len(positions)
			positions.extend(cluster_positions)
			indices.extend(index + vertex_start for index in embedded_indices)
			submeshes.append({
				"lod_index": lod_index, "group_id": 0,
				"submesh_index": cluster_index,
				"material_index": material_index,
				"vertex_start": vertex_start, "vertex_count": vertex_count,
				"index_count": index_count, "indices": embedded_indices,
				"index_buffer": struct.pack(
					"<" + "H" * index_count, *embedded_indices),
			})
			cluster_global_index += 1
		groups.append({
			"lod_index": lod_index, "group_id": 0,
			"submesh_count": cluster_count,
			"vertex_count": len(positions) - lod_vertex_start,
			"index_count": len(indices) - lod_index_start,
		})

	if cluster_global_index != sum(header["cluster_counts"]) or not positions:
		raise MeshProfileError("structural-profile-mismatch:cluster-count")
	position_buffer = b"".join(struct.pack("<3f", *position) for position in positions)
	normal_buffer = b"".join(normal_parts)
	uv_buffer = b"".join(uv_parts)
	color_buffer = b"".join(color_parts)
	vertex_buffer = position_buffer + normal_buffer + uv_buffer
	vertex_elements = {
		0: {"type": 0, "stride": 12, "offset": 0},
		1: {"type": 1, "stride": 8, "offset": len(position_buffer)},
		2: {"type": 2, "stride": 4,
			"offset": len(position_buffer) + len(normal_buffer)},
	}
	if has_color:
		vertex_elements[5] = {"type": 5, "stride": 4, "offset": len(vertex_buffer)}
		vertex_buffer += color_buffer
	mins = [min(position[axis] for position in positions) for axis in range(3)]
	maxs = [max(position[axis] for position in positions) for axis in range(3)]
	stats = _newPragmataImportStats(header["capability"])
	stats.update({
		"lod_count": header["lod_count"], "group_count": header["lod_count"],
		"submesh_count": len(submeshes), "vertex_count": len(positions),
		"index_count": len(indices), "triangle_count": len(indices) // 3,
		"normal_count": len(positions), "tangent_count": tangent_count,
		"uv_count": len(positions), "color_count": len(positions) if has_color else 0,
		"material_binding_count": len(submeshes),
		"aabb": {"min": mins, "max": maxs},
		"topology_hash": _meshTopologyHash(positions, indices),
	})
	return {
		"stats": stats, "positions": positions, "indices": indices,
		"groups": groups, "submeshes": submeshes,
		"vertex_buffer": vertex_buffer, "vertex_elements": vertex_elements,
		"bone_indices": [], "bone_weights": [], "bone_map": [], "bones": [],
		"material_names": material_names, "blend_shape_names": [],
		"blend_shapes": [],
	}

def _pragmataMplyNoesisBatches(submeshes):
	"""Collapse meshlets to one Noesis surface per LOD/material pair."""
	batch_map = {}
	batch_order = []
	for submesh in submeshes:
		key = (submesh["lod_index"], submesh["material_index"])
		if key not in batch_map:
			batch_map[key] = {
				"lod_index": submesh["lod_index"],
				"group_id": submesh["group_id"],
				"submesh_index": len(batch_order),
				"material_index": submesh["material_index"],
				"vertex_start": 0,
				"vertex_count": 0,
				"indices": [],
			}
			batch_order.append(key)
		batch = batch_map[key]
		batch["vertex_count"] += submesh["vertex_count"]
		batch["indices"].extend(
			index + submesh["vertex_start"] for index in submesh["indices"])
	result = []
	for key in batch_order:
		batch = batch_map[key]
		batch["index_count"] = len(batch["indices"])
		batch["index_buffer"] = struct.pack(
			"<" + "I" * batch["index_count"], *batch["indices"])
		result.append(batch)
	return result

def _pragmataNoesisIndexSubmission(submesh, capability):
	if capability in (PRAGMATA_MPLY_250707828, WILDS_MPLY_240704828):
		return submesh["index_buffer"], 4
	indices = submesh.get("indices", [])
	if len(indices) != submesh.get("index_count"):
		raise MeshProfileError(
			"structural-profile-mismatch:noesis-index-count")
	if any(index < 0 or index > 0xFFFF for index in indices):
		raise MeshProfileError(
			"structural-profile-mismatch:noesis-index-width")
	if 0xFFFF in indices:
		return struct.pack("<%dI" % len(indices), *indices), 4
	return submesh["index_buffer"], 2

def _readProfileSkeleton(data, skeleton_offset, bone_name_remap_offset, names):
	name_count = len(names)
	_checkedRange(data, skeleton_offset, 48, "skeleton-header")
	bone_count, bone_map_count = struct.unpack_from("<II", data, skeleton_offset)
	if bone_count <= 0:
		raise MeshProfileError("structural-profile-mismatch:bone-count")
	_validatePragmataBoneMapCount(bone_map_count)
	hierarchy_offset, local_offset, global_offset, inverse_global_offset = struct.unpack_from(
		"<QQQQ", data, skeleton_offset + 16)
	for label, offset, size in (
		("bone-hierarchy", hierarchy_offset, bone_count * 16),
		("bone-local-matrices", local_offset, bone_count * 64),
		("bone-global-matrices", global_offset, bone_count * 64),
		("bone-inverse-global-matrices", inverse_global_offset, bone_count * 64),
	):
		if offset <= 0:
			raise MeshProfileError("offset-out-of-bounds:" + label)
		_checkedRange(data, offset, size, label)

	bone_map_offset = skeleton_offset + 48
	_checkedRange(data, bone_map_offset, bone_map_count * 2, "bone-map")
	bone_map = []
	for map_index in range(bone_map_count):
		bone_index = struct.unpack_from("<h", data, bone_map_offset + map_index * 2)[0]
		if bone_index < 0 or bone_index >= bone_count:
			raise MeshProfileError("bone-map-index-out-of-range")
		bone_map.append(bone_index)

	_checkedRange(data, bone_name_remap_offset, bone_count * 2, "bone-name-remap")
	bone_name_indices = []
	for bone_index in range(bone_count):
		name_index = struct.unpack_from("<H", data, bone_name_remap_offset + bone_index * 2)[0]
		if name_index >= name_count:
			raise MeshProfileError("name-index-out-of-range:bone")
		bone_name_indices.append(name_index)

	bones = []
	seen_bone_indices = set()
	for bone_index in range(bone_count):
		hierarchy = struct.unpack_from("<8h", data, hierarchy_offset + bone_index * 16)
		declared_index = hierarchy[0]
		parent_index = hierarchy[1]
		if declared_index < 0 or declared_index >= bone_count or declared_index in seen_bone_indices:
			raise MeshProfileError("bone-index-out-of-range")
		if parent_index < -1 or parent_index >= bone_count:
			raise MeshProfileError("bone-parent-index-out-of-range")
		seen_bone_indices.add(declared_index)
		matrix_offset = local_offset + bone_index * 64
		matrix_values = struct.unpack_from("<16f", data, matrix_offset)
		if any(not math.isfinite(value) for value in matrix_values):
			raise MeshProfileError("structural-profile-mismatch:non-finite-bone-matrix")
		bones.append({
			"index": declared_index,
			"parent_index": parent_index,
			"name": names[bone_name_indices[bone_index]],
			"local_matrix": bytes(data[matrix_offset:matrix_offset + 64]),
		})

	return bone_count, bone_map_count, bone_map, bones

def _parsePragmataMeshData(data, header, streaming_data=None):
	capability = header.get("capability")
	if capability != PRAGMATA_250707828:
		raise MeshProfileError("unsupported-mesh-profile")
	stats = _newPragmataImportStats(capability)

	lod_offset = header["lod_offset"]
	_checkedRange(data, lod_offset, 16, "lod-header")
	count_array = struct.unpack_from("16B", data, lod_offset)
	lod_count = count_array[0]
	material_count = count_array[1]
	streaming_entry_count = header.get("streaming_entry_count", 0)
	if lod_count <= 0 or lod_count > 64:
		raise MeshProfileError("structural-profile-mismatch:lod-count")
	if material_count <= 0:
		raise MeshProfileError("structural-profile-mismatch:material-count")
	if count_array[6] != 0:
		raise MeshProfileError("structural-profile-mismatch:index-width")
	if streaming_entry_count not in (0, 1, 2):
		raise MeshProfileError("unsupported-streaming-entry-count")
	multi_stream = streaming_entry_count == 2
	if multi_stream and header.get("blend_shape") is not None:
		raise MeshProfileError("unsupported-multi-stream-blend-profile")
	if streaming_entry_count and streaming_data is None:
		raise MeshProfileError("missing-streaming-companion")
	lod_table_offset = lod_offset + 64
	_checkedRange(data, lod_table_offset, lod_count * 8, "lod-offset-table")

	groups = []
	submeshes = []
	buffer_vertex_counts = {"main": 0, "streaming": 0}
	buffer_order = ["streaming", "main"]
	if multi_stream:
		buffer_vertex_counts["streaming_1"] = 0
		buffer_order = ["streaming", "streaming_1", "main"]
	for lod_index in range(lod_count):
		buffer_kind = "streaming" if lod_index < streaming_entry_count else "main"
		lod_record_offset = struct.unpack_from("<Q", data, lod_table_offset + lod_index * 8)[0]
		_checkedRange(data, lod_record_offset, 16, "lod-record")
		group_count = data[lod_record_offset]
		if group_count <= 0:
			raise MeshProfileError("structural-profile-mismatch:group-count")
		group_table_offset = struct.unpack_from("<Q", data, lod_record_offset + 8)[0]
		_checkedRange(data, group_table_offset, group_count * 8, "group-offset-table")
		for group_index in range(group_count):
			group_offset = struct.unpack_from("<Q", data, group_table_offset + group_index * 8)[0]
			_checkedRange(data, group_offset, 16, "group-record")
			group_values = struct.unpack_from("<BBHIII", data, group_offset)
			group_id = group_values[0]
			submesh_count = group_values[1]
			group_vertex_count = group_values[4]
			group_index_count = group_values[5]
			if submesh_count <= 0:
				raise MeshProfileError("structural-profile-mismatch:submesh-count")
			if group_vertex_count <= 0:
				raise MeshProfileError("structural-profile-mismatch:vertex-count")
			if group_index_count <= 0:
				raise MeshProfileError("structural-profile-mismatch:index-count")
			_checkedRange(data, group_offset + 16, submesh_count * 32, "submesh-table")
			if multi_stream:
				buffer_id = data[group_offset + 18]
				if buffer_id > streaming_entry_count:
					raise MeshProfileError("structural-profile-mismatch:streaming-buffer-id")
				buffer_kind = ("main", "streaming", "streaming_1")[buffer_id]
			local_group_vertex_start = buffer_vertex_counts[buffer_kind]
			vertex_buffer_adjust = (
				buffer_vertex_counts["streaming"] if buffer_kind == "main" and not multi_stream else 0
			)
			group_vertex_start = local_group_vertex_start + vertex_buffer_adjust
			group_submeshes = []
			for submesh_index in range(submesh_count):
				if multi_stream and data[group_offset + 18 + submesh_index * 32] != buffer_id:
					raise MeshProfileError("structural-profile-mismatch:streaming-buffer-id")
				submesh = parsePragmataSubmesh(data, group_offset + 16 + submesh_index * 32)
				if submesh["streaming_offset"] != 0 or submesh["platform_streaming_offset"] != 0:
					raise MeshProfileError("streaming-profile-out-of-scope")
				if submesh["material_index"] >= material_count:
					raise MeshProfileError("material-index-out-of-range")
				submesh["lod_index"] = lod_index
				submesh["group_index"] = group_index
				submesh["group_id"] = group_id
				submesh["submesh_index"] = submesh_index
				group_submeshes.append(submesh)
			if group_submeshes[0]["vertex_start"] != local_group_vertex_start:
				raise MeshProfileError("structural-profile-mismatch:vertex-start")
			local_group_vertex_end = local_group_vertex_start + group_vertex_count
			for submesh_index, submesh in enumerate(group_submeshes):
				next_vertex_start = (
					group_submeshes[submesh_index + 1]["vertex_start"]
					if submesh_index + 1 < len(group_submeshes) else local_group_vertex_end
				)
				if next_vertex_start <= submesh["vertex_start"] or next_vertex_start > local_group_vertex_end:
					raise MeshProfileError("structural-profile-mismatch:vertex-start")
				submesh["vertex_count"] = next_vertex_start - submesh["vertex_start"]
				submesh["local_vertex_start"] = submesh["vertex_start"]
				submesh["vertex_start"] += vertex_buffer_adjust
				submesh["buffer_kind"] = buffer_kind
				submeshes.append(submesh)
			group_index_start = group_submeshes[0]["index_start"]
			group_index_end = group_index_start + group_index_count
			for submesh in group_submeshes:
				if submesh["index_start"] < group_index_start or submesh["index_start"] + submesh["index_count"] > group_index_end:
					raise MeshProfileError("structural-profile-mismatch:group-index-count")
			if sum(item["index_count"] for item in group_submeshes) > group_index_count:
				raise MeshProfileError("structural-profile-mismatch:group-index-count")
			groups.append({
				"lod_index": lod_index,
				"group_index": group_index,
				"group_id": group_id,
				"vertex_start": group_vertex_start,
				"vertex_count": group_vertex_count,
				"index_count": group_index_count,
			})
			if multi_stream:
				groups[-1]["buffer_kind"] = buffer_kind
			buffer_vertex_counts[buffer_kind] += group_vertex_count
	if multi_stream:
		if any(buffer_vertex_counts[kind] <= 0 for kind in buffer_order):
			raise MeshProfileError("structural-profile-mismatch:empty-streaming-buffer")
		base = 0
		for kind in buffer_order:
			for record in groups + submeshes:
				if record["buffer_kind"] == kind:
					record["vertex_start"] += base
			base += buffer_vertex_counts[kind]

	vertex_count = sum(group["vertex_count"] for group in groups)
	index_count = sum(submesh["index_count"] for submesh in submeshes)
	if vertex_count <= 0 or index_count <= 0:
		raise MeshProfileError("structural-profile-mismatch:empty-mesh")

	name_count = header["name_count"]
	name_table_offset = header["names_offset"]
	_checkedRange(data, name_table_offset, name_count * 8, "name-table")
	names = []
	for name_index in range(name_count):
		name_offset = struct.unpack_from("<Q", data, name_table_offset + name_index * 8)[0]
		name = _readPragmataCString(data, name_offset, "name-string")
		if not name:
			raise MeshProfileError("structural-profile-mismatch:empty-name")
		names.append(name)

	material_remap_offset = header["material_remap_offset"]
	_checkedRange(data, material_remap_offset, material_count * 2, "material-remap")
	material_names = []
	for material_index in range(material_count):
		name_index = struct.unpack_from("<H", data, material_remap_offset + material_index * 2)[0]
		if name_index >= name_count:
			raise MeshProfileError("name-index-out-of-range:material")
		material_names.append(names[name_index])

	static_mesh = not header["skeleton_offset"]
	if static_mesh:
		bone_count, bone_map_count, bone_map, bones = 0, 0, [], []
	else:
		bone_count, bone_map_count, bone_map, bones = _readProfileSkeleton(
			data, header["skeleton_offset"], header["bone_remap_offset"], names)

	blend_shape_names = []
	blend_shape = header.get("blend_shape")
	if blend_shape is not None:
		expected_blend_name_count = name_count - material_count - bone_count
		if (expected_blend_name_count <= 0 or
				expected_blend_name_count != blend_shape["name_count"]):
			raise MeshProfileError(
				"structural-profile-mismatch:blend-shape-name-count")
		blend_name_offset = header["blend_name_offset"]
		blend_name_size = expected_blend_name_count * 2
		blend_name_range = _checkedRange(
			data, blend_name_offset, blend_name_size, "blend-shape-name-remap")
		name_table_range = (name_table_offset, name_table_offset + name_count * 8)
		if _rangesOverlap(blend_name_range, name_table_range):
			raise MeshProfileError("range-overlap:blend-shape-name-remap:name-table")
		for blend_name_index in range(expected_blend_name_count):
			name_index = struct.unpack_from(
				"<H", data, blend_name_offset + blend_name_index * 2)[0]
			if name_index >= name_count:
				raise MeshProfileError("name-index-out-of-range:blend-shape")
			blend_shape_names.append(names[name_index])
		for blend_submesh in blend_shape["submeshes"]:
			if (blend_submesh["vertex_start"] >= vertex_count or
					blend_submesh["vertex_count"] >
					vertex_count - blend_submesh["vertex_start"]):
				raise MeshProfileError(
					"structural-profile-mismatch:blend-submesh-vertex-range")

	mesh_buffer = header["mesh_buffer"]
	minimum_elements = 4 if static_mesh else 5
	if (mesh_buffer["main_element_count"] != mesh_buffer["element_count"] or
			mesh_buffer["element_count"] < minimum_elements or mesh_buffer["element_count"] > 7):
		raise MeshProfileError("structural-profile-mismatch:vertex-element-count")
	def readVertexElements(source, offset, count, label):
		_checkedRange(source, offset, count * 8, label)
		result = {}
		order = []
		for element_index in range(count):
			element_type, stride, buffer_offset = struct.unpack_from(
				"<HHI", source, offset + element_index * 8)
			if element_type in result:
				raise MeshProfileError("structural-profile-mismatch:duplicate-vertex-element")
			result[element_type] = {
				"type": element_type, "stride": stride, "offset": buffer_offset,
			}
			order.append(element_type)
		return result, order

	main_vertex_elements, element_types = readVertexElements(
		data, mesh_buffer["vertex_element_offset"], mesh_buffer["element_count"],
		"vertex-elements")
	required_elements = {0, 1, 2, 5} if static_mesh else {0, 1, 2, 4, 5}
	if (not required_elements.issubset(main_vertex_elements) or
			(static_mesh and any(element in main_vertex_elements for element in (4, 7))) or
			any(element_type not in (0, 1, 2, 3, 4, 5, 7) for element_type in element_types) or
			element_types != sorted(element_types)):
		raise MeshProfileError("structural-profile-mismatch:vertex-elements")
	expected_strides = {0: 12, 1: 8, 2: 4, 3: 4, 4: 16, 5: 4, 7: 16}
	for element_type in element_types:
		if main_vertex_elements[element_type]["stride"] != expected_strides[element_type]:
			raise MeshProfileError("structural-profile-mismatch:vertex-stride")

	main_vertex_count = buffer_vertex_counts["main"]
	streaming_layouts = {}
	stream_buffer_ranges = []
	if multi_stream:
		descriptor_start = mesh_buffer["streaming_vertex_element_offset"]
		descriptor_stride = (mesh_buffer["main_element_count"] * 8 + 15) & ~15
		descriptor_range = _checkedRange(data, descriptor_start,
			descriptor_stride + mesh_buffer["main_element_count"] * 8,
			"streaming-descriptors")
		protected_ranges = (
			(header["mesh_offset"], header["streaming_offset"] + 16),
			(mesh_buffer["vertex_element_offset"],
			 mesh_buffer["vertex_element_offset"] + mesh_buffer["element_count"] * 8),
			mesh_buffer["total_buffer_range"],
		)
		if any(_rangesOverlap(descriptor_range, protected) for protected in protected_ranges):
			raise MeshProfileError("range-overlap:streaming-descriptors")
	for stream_index in range(streaming_entry_count):
		stream_kind = "streaming" if stream_index == 0 else "streaming_1"
		stream_header_format = "<QIIHHQQ" + "I" * 11
		stream_header_offset = header["mesh_offset"] + 96 + stream_index * struct.calcsize(stream_header_format)
		_checkedRange(data, stream_header_offset, struct.calcsize(stream_header_format),
			"streaming-buffer-header")
		stream_values = struct.unpack_from(stream_header_format, data, stream_header_offset)
		stream_total_size = stream_values[1]
		stream_vertex_size = stream_values[2]
		stream_main_element_count = stream_values[3]
		stream_element_count = stream_values[4]
		stream_unpadded_size = stream_values[7]
		if (stream_main_element_count != mesh_buffer["main_element_count"] or
				stream_element_count != mesh_buffer["element_count"]):
			raise MeshProfileError("structural-profile-mismatch:streaming-vertex-element-count")
		stream_info_count, _stream_info_unknown, stream_info_entry_offset = struct.unpack_from(
			"<IIQ", data, header["streaming_offset"])
		if stream_info_count != streaming_entry_count:
			raise MeshProfileError("unsupported-streaming-entry-count")
		stream_info_entry_offset += stream_index * 8
		_checkedRange(data, stream_info_entry_offset, 8, "streaming-info-entry")
		stream_buffer_start, stream_buffer_length = struct.unpack_from(
			"<II", data, stream_info_entry_offset)
		if stream_buffer_length != stream_total_size:
			raise MeshProfileError("structural-profile-mismatch:streaming-buffer-size")
		stream_range = _checkedRange(streaming_data, stream_buffer_start, stream_total_size,
			"streaming-buffer")
		if any(_rangesOverlap(stream_range, previous) for previous in stream_buffer_ranges):
			raise MeshProfileError("range-overlap:streaming-buffer")
		stream_buffer_ranges.append(stream_range)
		if stream_unpadded_size < stream_vertex_size or stream_unpadded_size > stream_total_size:
			raise MeshProfileError("structural-profile-mismatch:streaming-buffer-size")
		stream_vertex_elements, stream_element_types = readVertexElements(
			data, mesh_buffer["streaming_vertex_element_offset"] +
			stream_index * ((mesh_buffer["main_element_count"] * 8 + 15) & ~15),
			mesh_buffer["main_element_count"], "streaming-vertex-elements")
		if stream_element_types != element_types:
			raise MeshProfileError("structural-profile-mismatch:streaming-vertex-elements")
		streaming_layouts[stream_kind] = {
			"buffer_start": stream_buffer_start,
			"vertex_size": stream_vertex_size,
			"face_start": stream_buffer_start + stream_vertex_size,
			"face_size": stream_unpadded_size - stream_vertex_size,
			"elements": stream_vertex_elements,
		}

	vertex_buffer_parts = []
	vertex_elements = {}
	combined_offset = 0
	main_element_ranges = []
	streaming_element_ranges = {kind: [] for kind in streaming_layouts}
	for element_type in element_types:
		main_element = main_vertex_elements[element_type]
		main_size = main_element["stride"] * main_vertex_count
		main_start = mesh_buffer["vertex_buffer_offset"] + main_element["offset"]
		if main_element["offset"] + main_size > mesh_buffer["vertex_buffer_size"]:
			raise MeshProfileError("offset-out-of-bounds:vertex-element-" + str(element_type))
		_checkedRange(data, main_start, main_size, "vertex-element-" + str(element_type))
		main_range = (main_element["offset"], main_element["offset"] + main_size)
		for previous_type, previous_range in main_element_ranges:
			if main_size and _rangesOverlap(main_range, previous_range):
				raise MeshProfileError(
					"range-overlap:vertex-element-" + str(previous_type) +
					":vertex-element-" + str(element_type))
		main_element_ranges.append((element_type, main_range))
		vertex_elements[element_type] = {
			"type": element_type, "stride": main_element["stride"],
			"offset": combined_offset,
		}
		for stream_kind in buffer_order[:-1]:
			if stream_kind not in streaming_layouts:
				continue
			streaming_layout = streaming_layouts[stream_kind]
			streaming_vertex_count = buffer_vertex_counts[stream_kind]
			stream_element = streaming_layout["elements"][element_type]
			if stream_element["stride"] != main_element["stride"]:
				raise MeshProfileError("structural-profile-mismatch:streaming-vertex-stride")
			stream_size = stream_element["stride"] * streaming_vertex_count
			stream_start = streaming_layout["buffer_start"] + stream_element["offset"]
			if stream_element["offset"] + stream_size > streaming_layout["vertex_size"]:
				raise MeshProfileError("offset-out-of-bounds:streaming-vertex-element-" + str(element_type))
			_checkedRange(streaming_data, stream_start, stream_size,
				"streaming-vertex-element-" + str(element_type))
			stream_range = (
				stream_element["offset"], stream_element["offset"] + stream_size)
			for previous_type, previous_range in streaming_element_ranges[stream_kind]:
				if stream_size and _rangesOverlap(stream_range, previous_range):
					raise MeshProfileError(
						"range-overlap:streaming-vertex-element-" +
						str(previous_type) + ":streaming-vertex-element-" +
						str(element_type))
			streaming_element_ranges[stream_kind].append((element_type, stream_range))
			vertex_buffer_parts.append(bytes(streaming_data[stream_start:stream_start + stream_size]))
			combined_offset += stream_size
		vertex_buffer_parts.append(bytes(data[main_start:main_start + main_size]))
		combined_offset += main_size
	vertex_buffer = b"".join(vertex_buffer_parts)

	positions = []
	position_start = vertex_elements[0]["offset"]
	for vertex_index in range(vertex_count):
		position = struct.unpack_from("<3f", vertex_buffer, position_start + vertex_index * 12)
		if any(not math.isfinite(value) for value in position):
			raise MeshProfileError("structural-profile-mismatch:non-finite-position")
		positions.append(position)

	if static_mesh:
		bone_indices, bone_weights = [], []
		weight_stats = {key: 0 for key in ("weighted_bone_count",
			"weighted_vertex_count", "max_influences", "weight_sum_max_error")}
	else:
		weight_start = vertex_elements[4]["offset"]
		weight_size = vertex_elements[4]["stride"] * vertex_count
		weight_data = vertex_buffer[weight_start:weight_start + weight_size]
		extra_weight_data = None
		if 7 in vertex_elements:
			extra_weight_start = vertex_elements[7]["offset"]
			extra_weight_size = vertex_elements[7]["stride"] * vertex_count
			extra_weight_data = vertex_buffer[
				extra_weight_start:extra_weight_start + extra_weight_size]
		bone_indices, bone_weights, weight_stats = _decodePragmataWeightProfile(
			weight_data, extra_weight_data, bone_map_count)

	face_buffer_size = mesh_buffer["face_buffer_size"]
	if face_buffer_size % 2:
		raise MeshProfileError("structural-profile-mismatch:face-buffer-size")
	face_sources = {
		"main": (data, mesh_buffer["face_buffer_offset"], face_buffer_size),
	}
	for stream_kind, streaming_layout in streaming_layouts.items():
		if streaming_layout["face_size"] % 2:
			raise MeshProfileError("structural-profile-mismatch:streaming-face-buffer-size")
		face_sources[stream_kind] = (
			streaming_data, streaming_layout["face_start"], streaming_layout["face_size"])
	indices = []
	index_ranges = {kind: [] for kind in buffer_order}
	for submesh in submeshes:
		if submesh["index_count"] % 3:
			raise MeshProfileError("structural-profile-mismatch:index-count")
		face_source, face_buffer_offset, source_face_size = face_sources[submesh["buffer_kind"]]
		face_index_capacity = source_face_size // 2
		if submesh["index_start"] + submesh["index_count"] > face_index_capacity:
			raise MeshProfileError("offset-out-of-bounds:index-buffer")
		index_buffer_offset = face_buffer_offset + submesh["index_start"] * 2
		index_buffer_size = submesh["index_count"] * 2
		index_range = _checkedRange(face_source, index_buffer_offset, index_buffer_size, "index-buffer")
		if any(_rangesOverlap(index_range, previous) for previous in index_ranges[submesh["buffer_kind"]]):
			raise MeshProfileError("range-overlap:index-buffer")
		index_ranges[submesh["buffer_kind"]].append(index_range)
		submesh_indices = []
		for index_number in range(submesh["index_count"]):
			index = struct.unpack_from("<H", face_source, index_buffer_offset + index_number * 2)[0]
			if index >= submesh["vertex_count"]:
				raise MeshProfileError("index-out-of-range")
			submesh_indices.append(index)
			indices.append(index + submesh["vertex_start"])
		submesh["indices"] = submesh_indices
		submesh["index_buffer"] = bytes(face_source[index_buffer_offset:index_buffer_offset + index_buffer_size])

	mins = [min(position[axis] for position in positions) for axis in range(3)]
	maxs = [max(position[axis] for position in positions) for axis in range(3)]
	stats.update({
		"lod_count": lod_count,
		"group_count": len(groups),
		"submesh_count": len(submeshes),
		"vertex_count": vertex_count,
		"index_count": index_count,
		"triangle_count": index_count // 3,
		"normal_count": vertex_count,
		"tangent_count": vertex_count,
		"uv_count": vertex_count,
		"color_count": vertex_count,
		"material_binding_count": len(submeshes),
		"bone_count": bone_count,
		"weighted_bone_count": weight_stats["weighted_bone_count"],
		"weighted_vertex_count": weight_stats["weighted_vertex_count"],
		"max_influences": weight_stats["max_influences"],
		"weight_sum_max_error": weight_stats["weight_sum_max_error"],
		"aabb": {"min": mins, "max": maxs},
		"topology_hash": _meshTopologyHash(positions, indices),
	})
	blend_shapes = _decodePragmataBlendShapes(
		data, blend_shape, blend_shape_names)
	return {
		"stats": stats,
		"positions": positions,
		"indices": indices,
		"groups": groups,
		"submeshes": submeshes,
		"vertex_buffer": vertex_buffer,
		"vertex_elements": vertex_elements,
		"bone_indices": bone_indices,
		"bone_weights": bone_weights,
		"bone_map": bone_map,
		"bones": bones,
		"material_names": material_names,
		"blend_shape_names": blend_shape_names,
		"blend_shapes": blend_shapes,
	}

def parseWildsMeshData(data, header, streaming_data=None):
	"""Normalize observed Wilds base-geometry layouts for shared submission.

	Byte contracts and independent oracles: RE-090 phase1 mesh-layout.json.
	Blend names are metadata only; packed blend payload is deliberately not decoded.
	"""
	if header.get("capability") != WILDS_240704828:
		raise MeshProfileError("unsupported-mesh-profile")
	regions = [(0, 176)]
	def metadata(offset, size, label):
		region = _checkedRange(data, offset, size, label)
		if region in regions:
			return region
		if any(_rangesOverlap(region, previous) for previous in regions):
			raise MeshProfileError("range-overlap:" + label)
		regions.append(region)
		return region
	def unpack(offset, fmt, label):
		_checkedRange(data, offset, struct.calcsize(fmt), label)
		return struct.unpack_from(fmt, data, offset)

	lod_offset = header["lod_offset"]
	metadata(lod_offset, 64, "lod-header")
	lod_count, material_count = unpack(lod_offset, "<BB", "lod-counts")
	stream_count = header["streaming_entry_count"]
	if not 1 <= lod_count <= 64 or not material_count or data[lod_offset + 6] != 0:
		raise MeshProfileError("structural-profile-mismatch:lod-header")
	if stream_count and (lod_count != stream_count + 1 or streaming_data is None):
		raise MeshProfileError("missing-streaming-companion-or-unsupported-lods")
	metadata(lod_offset + 64, lod_count * 8, "lod-table")
	metadata(header["names_offset"], header["name_count"] * 8, "names-table")
	names = []
	string_offsets = set()
	for index in range(header["name_count"]):
		offset = unpack(header["names_offset"] + index * 8, "<Q", "name-pointer")[0]
		name = _readPragmataCString(data, offset, "name-string")
		if not name:
			raise MeshProfileError("structural-profile-mismatch:empty-name")
		if offset not in string_offsets:
			metadata(offset, len(name.encode("utf-8")) + 1, "name-string")
			string_offsets.add(offset)
		names.append(name)
	def remap(offset, count, label):
		metadata(offset, count * 2, label)
		result = []
		for index in range(count):
			slot = unpack(offset + index * 2, "<H", label)[0]
			if slot >= len(names):
				raise MeshProfileError("name-index-out-of-range:" + label)
			result.append(names[slot])
		return result
	material_names = remap(header["material_remap_offset"], material_count, "material-remap")
	bones, bone_map = [], []
	if header["skeleton_offset"]:
		offset = header["skeleton_offset"]
		bone_count, map_count = unpack(offset, "<II", "skeleton-counts")
		_validatePragmataBoneMapCount(map_count)
		metadata(offset, 48 + map_count * 2, "skeleton-header-map")
		pointers = unpack(offset + 16, "<4Q", "skeleton-pointers")
		for index, pointer in enumerate(pointers):
			metadata(pointer, bone_count * (16 if index == 0 else 64), "skeleton-table")
		metadata(header["bone_remap_offset"], bone_count * 2, "bone-remap")
		bone_count, map_count, bone_map, bones = _readProfileSkeleton(
			data, offset, header["bone_remap_offset"], names)
		for index, bone in enumerate(bones):
			if bone["index"] != index:
				raise MeshProfileError("structural-profile-mismatch:bone-index-order")
			seen = set()
			parent = index
			while parent != -1:
				if parent in seen:
					raise MeshProfileError("bone-parent-cycle")
				seen.add(parent)
				parent = bones[parent]["parent_index"]
		for pointer in pointers[2:]:
			for value in struct.unpack_from("<" + str(bone_count * 16) + "f", data, pointer):
				if not math.isfinite(value):
					raise MeshProfileError("non-finite-bone-matrix")
	elif header["bone_remap_offset"]:
		raise MeshProfileError("structural-profile-mismatch:bone-remap-without-skeleton")
	blend_shape_names = []
	remaining_names = len(names) - material_count - len(bones)
	if remaining_names:
		if remaining_names < 0 or not header["blend_shape_offset"] or not header["blend_name_offset"]:
			raise MeshProfileError("structural-profile-mismatch:blend-names")
		blend_shape_names = remap(header["blend_name_offset"], remaining_names, "blend-name-remap")

	mesh_offset = header["mesh_offset"]
	metadata(mesh_offset, 64 + stream_count * 64, "mesh-buffer-header")
	values = unpack(mesh_offset, "<QQQIIHH7I", "main-buffer")
	elements, start, total, vertex_size, count = values[0], values[1], values[3], values[4], values[6]
	if start != header["vertices_offset"] or values[5] != count or not 3 <= count <= 7:
		raise MeshProfileError("structural-profile-mismatch:main-buffer")
	if values[7] != values[8]:
		raise MeshProfileError("structural-profile-mismatch:unpadded-size")
	metadata(header["streaming_offset"], 16, "streaming-info")
	buffers = [{"source": data, "start": start, "total": total, "vertex_size": vertex_size,
		"unpadded": values[7], "elements_offset": elements}]
	if stream_count:
		entries = header["streaming_entries_offset"]
		metadata(entries, stream_count * 8, "streaming-entries")
		end = 0
		seen_ranges = set()
		for index in range(stream_count):
			start, length = unpack(entries + index * 8, "<II", "streaming-range")
			stream_elements, range_start = unpack(mesh_offset + 64 + index * 64,
				"<QQ", "streaming-element-pointer")
			values = unpack(mesh_offset + 80 + index * 64, "<QIIHH7I", "streaming-buffer")
			if ((start != end and (start, length) not in seen_ranges) or
					range_start != start or length != values[1] or values[3] != count or
					values[4] != count or values[5] != values[6]):
				raise MeshProfileError("structural-profile-mismatch:streaming-buffer")
			seen_ranges.add((start, length))
			end = max(end, start + length)
			buffers.append({"source": streaming_data, "start": start, "total": length,
				"vertex_size": values[2], "unpadded": values[5],
				"elements_offset": stream_elements})
		if end != len(streaming_data):
			raise MeshProfileError("structural-profile-mismatch:streaming-buffer-size")
	expected_types = None
	strides = {0: 12, 1: 8, 2: 4, 3: 4, 4: 16, 5: 4, 7: 16}
	element_tables = set()
	for buffer in buffers:
		if not 0 < buffer["vertex_size"] < buffer["unpadded"] <= buffer["total"]:
			raise MeshProfileError("structural-profile-mismatch:buffer-size")
		if (buffer["unpadded"] - buffer["vertex_size"]) % 2:
			raise MeshProfileError("structural-profile-mismatch:face-buffer-size")
		_checkedRange(buffer["source"], buffer["start"], buffer["total"], "geometry-buffer")
		if buffer["elements_offset"] not in element_tables:
			metadata(buffer["elements_offset"], count * 8, "vertex-elements")
			element_tables.add(buffer["elements_offset"])
		element_map = {}
		element_types = []
		for index in range(count):
			typ, stride, offset = unpack(buffer["elements_offset"] + index * 8, "<HHI", "vertex-element")
			if typ not in strides or typ in element_map or stride != strides[typ]:
				raise MeshProfileError("structural-profile-mismatch:vertex-elements")
			element_map[typ] = {"type": typ, "stride": stride, "offset": offset}
			element_types.append(typ)
		if (element_types != sorted(element_types) or
				not {0, 1, 2}.issubset(element_map) or
				bool(bones) != (4 in element_map) or
				(7 in element_map and 4 not in element_map)):
			raise MeshProfileError("structural-profile-mismatch:vertex-elements")
		if expected_types is None:
			expected_types = element_types
		elif element_types != expected_types:
			raise MeshProfileError("structural-profile-mismatch:streaming-vertex-elements")
		buffer.update(elements=element_map, vertex_count=0, index_ranges=[])

	groups, submeshes = [], []
	vertex_count = 0
	for li in range(lod_count):
		record = unpack(lod_offset + 64 + li * 8, "<Q", "lod-pointer")[0]
		metadata(record, 16, "lod-record")
		group_count = data[record]
		if not group_count:
			raise MeshProfileError("structural-profile-mismatch:group-count")
		table = unpack(record + 8, "<Q", "group-table-pointer")[0]
		metadata(table, group_count * 8, "group-table")
		lod_slot_counts = {}
		for gi in range(group_count):
			offset = unpack(table + gi * 8, "<Q", "group-pointer")[0]
			gid, sn, unused, unused2, vc, ic = unpack(offset, "<BBHIII", "group")
			if not sn or not vc or not ic:
				raise MeshProfileError("structural-profile-mismatch:empty-group")
			metadata(offset, 16 + sn * 32, "group-submeshes")
			rows = [parsePragmataSubmesh(data, offset + 16 + si * 32) for si in range(sn)]
			slots = {data[offset + 16 + si * 32 + 2] for si in range(sn)}
			if len(slots) != 1:
				raise MeshProfileError("structural-profile-mismatch:submesh-buffer")
			slot = slots.pop()
			if slot > stream_count:
				raise MeshProfileError("structural-profile-mismatch:submesh-buffer")
			buffer = buffers[slot]
			local_start = lod_slot_counts.get(slot, 0)
			if rows[0]["vertex_start"] != local_start:
				raise MeshProfileError("structural-profile-mismatch:vertex-start")
			first_index = rows[0]["index_start"]
			if sum(row["index_count"] for row in rows) > ic:
				raise MeshProfileError("structural-profile-mismatch:group-index-count")
			groups.append({"lod_index": li, "group_index": gi, "group_id": gid,
				"vertex_start": vertex_count, "vertex_count": vc, "index_count": ic})
			for si, row in enumerate(rows):
				end = rows[si + 1]["vertex_start"] if si + 1 < sn else local_start + vc
				if (data[offset + 16 + si * 32 + 2] != slot or row["streaming_offset"] or
						row["platform_streaming_offset"] or row["material_index"] >= material_count):
					raise MeshProfileError("structural-profile-mismatch:submesh")
				if not row["vertex_start"] < end <= local_start + vc:
					raise MeshProfileError("structural-profile-mismatch:vertex-start")
				if (not row["index_count"] or row["index_count"] % 3 or
						row["index_start"] < first_index or row["index_start"] + row["index_count"] > first_index + ic):
					raise MeshProfileError("structural-profile-mismatch:index-count")
				row.update(lod_index=li, group_index=gi, group_id=gid, submesh_index=si,
					buffer_kind=slot, local_vertex_start=row["vertex_start"],
					vertex_count=end-row["vertex_start"])
				row["vertex_start"] = vertex_count + row["local_vertex_start"] - local_start
				submeshes.append(row)
			lod_slot_counts[slot] = local_start + vc
			vertex_count += vc
		for slot, count_for_slot in lod_slot_counts.items():
			buffer = buffers[slot]
			if buffer["vertex_count"] not in (0, count_for_slot):
				raise MeshProfileError("structural-profile-mismatch:buffer-vertex-count")
			buffer["vertex_count"] = count_for_slot

	parts, vertex_elements, combined_offset = [], {}, 0
	for buffer in buffers:
		ranges = []
		for typ in expected_types:
			element = buffer["elements"][typ]
			size = element["stride"] * buffer["vertex_count"]
			region = (element["offset"], element["offset"] + size)
			if region[1] > buffer["vertex_size"]:
				raise MeshProfileError("offset-out-of-bounds:vertex-element")
			if any(_rangesOverlap(region, previous) for previous in ranges):
				raise MeshProfileError("range-overlap:vertex-element")
			ranges.append(region)
	main_region = (buffers[0]["start"], buffers[0]["start"] + buffers[0]["total"])
	if any(_rangesOverlap(main_region, previous) for previous in regions):
		raise MeshProfileError("range-overlap:main-buffer-metadata")
	for typ in expected_types:
		vertex_elements[typ] = {"type": typ, "stride": strides[typ], "offset": combined_offset}
		for row in submeshes:
			buffer = buffers[row["buffer_kind"]]
			start = buffer["start"] + buffer["elements"][typ]["offset"] + row["local_vertex_start"] * strides[typ]
			size = row["vertex_count"] * strides[typ]
			parts.append(bytes(buffer["source"][start:start + size]))
			combined_offset += size
	vertex_buffer = b"".join(parts)
	positions = [struct.unpack_from("<3f", vertex_buffer, i * 12) for i in range(vertex_count)]
	if any(not math.isfinite(c) for position in positions for c in position):
		raise MeshProfileError("structural-profile-mismatch:non-finite-position")
	indices = []
	for row in submeshes:
		buffer = buffers[row["buffer_kind"]]
		start = row["index_start"] * 2
		size = row["index_count"] * 2
		if start + size > buffer["unpadded"] - buffer["vertex_size"]:
			raise MeshProfileError("offset-out-of-bounds:index-buffer")
		region = (start, start + size)
		if (region not in buffer["index_ranges"] and
				any(_rangesOverlap(region, previous) for previous in buffer["index_ranges"])):
			raise MeshProfileError("range-overlap:index-buffer")
		if region not in buffer["index_ranges"]:
			buffer["index_ranges"].append(region)
		start += buffer["start"] + buffer["vertex_size"]
		row["index_buffer"] = bytes(buffer["source"][start:start + size])
		row["indices"] = list(struct.unpack("<" + str(row["index_count"]) + "H", row["index_buffer"]))
		if any(index >= row["vertex_count"] for index in row["indices"]):
			raise MeshProfileError("index-out-of-range")
		indices.extend(index + row["vertex_start"] for index in row["indices"])
	bone_indices, bone_weights = [], []
	stats = _newPragmataImportStats(WILDS_240704828)
	if bones:
		start = vertex_elements[4]["offset"]
		extra_weights = None
		if 7 in vertex_elements:
			extra_start = vertex_elements[7]["offset"]
			extra_weights = vertex_buffer[
				extra_start:extra_start + vertex_count * 16]
		bone_indices, bone_weights, weights = _decodePragmataWeightProfile(
			vertex_buffer[start:start + vertex_count * 16], extra_weights,
			len(bone_map))
		if any(sum(row) != 255 for row in bone_weights):
			raise MeshProfileError("structural-profile-mismatch:weight-sum")
		stats.update(weights)
	stats.update(lod_count=lod_count, group_count=len(groups), submesh_count=len(submeshes),
		vertex_count=vertex_count, index_count=len(indices), triangle_count=len(indices)//3,
		normal_count=vertex_count, tangent_count=vertex_count, uv_count=vertex_count,
		color_count=vertex_count if 5 in vertex_elements else 0, bone_count=len(bones),
		material_binding_count=len(submeshes),
		aabb={"min": [min(p[a] for p in positions) for a in range(3)],
			"max": [max(p[a] for p in positions) for a in range(3)]},
		topology_hash=_meshTopologyHash(positions, indices))
	return {"stats": stats, "positions": positions, "indices": indices,
		"groups": groups, "submeshes": submeshes, "vertex_buffer": vertex_buffer,
		"vertex_elements": vertex_elements, "bone_indices": bone_indices,
		"bone_weights": bone_weights, "bone_map": bone_map, "bones": bones,
		"material_names": material_names, "blend_shape_names": blend_shape_names,
		"blend_shapes": []}
