"""Numeric conversion, packing and topology helpers."""

import hashlib
import json
import math
import struct


def float32(value, error_type=ValueError):
	try:
		value = float(value)
		if not math.isfinite(value):
			raise ValueError
		return struct.unpack("<f", struct.pack("<f", value))[0]
	except (TypeError, ValueError, OverflowError, struct.error):
		raise error_type("structural-profile-mismatch:float32-range")


def round_half_away_from_zero(value, error_type=ValueError):
	try:
		value = float(value)
	except (TypeError, ValueError, OverflowError):
		raise error_type("structural-profile-mismatch:non-finite-attribute")
	if not math.isfinite(value):
		raise error_type("structural-profile-mismatch:non-finite-attribute")
	magnitude = int(math.floor(abs(value) + 0.5))
	return -magnitude if value < 0.0 else magnitude


def round_shift_right_to_even(value, shift):
	if shift <= 0:
		return value << -shift
	quotient = value >> shift
	remainder = value - (quotient << shift)
	halfway = 1 << (shift - 1)
	if remainder > halfway or (remainder == halfway and quotient & 1):
		quotient += 1
	return quotient


def float_to_half_bits(value, error_type=ValueError):
	try:
		value = float(value)
	except (TypeError, ValueError, OverflowError):
		raise error_type("structural-profile-mismatch:uv-range")
	if not math.isfinite(value) or abs(value) > 65504.0:
		raise error_type("structural-profile-mismatch:uv-range")
	bits = struct.unpack("<Q", struct.pack("<d", value))[0]
	sign = (bits >> 48) & 0x8000
	exponent = (bits >> 52) & 0x7FF
	fraction = bits & ((1 << 52) - 1)
	if exponent == 0 and fraction == 0:
		return sign
	if exponent == 0:
		significand = fraction
		power = -1074
	else:
		significand = (1 << 52) | fraction
		power = exponent - 1023 - 52
	if abs(value) < 2.0 ** -14:
		quantized = round_shift_right_to_even(significand, -(power + 24))
		return sign | min(quantized, 0x400)
	half_exponent = exponent - 1023 + 15
	quantized = round_shift_right_to_even(significand, 42)
	if quantized == 0x800:
		half_exponent += 1
		quantized = 0x400
	return sign | (half_exponent << 10) | (quantized & 0x3FF)


def quantize_snorm(value, error_type=ValueError):
	try:
		value = float(value)
	except (TypeError, ValueError, OverflowError):
		raise error_type("structural-profile-mismatch:non-finite-normal-tangent")
	if not math.isfinite(value):
		raise error_type("structural-profile-mismatch:non-finite-normal-tangent")
	return max(-127, min(127, round_half_away_from_zero(
		max(-1.0, min(1.0, value)) * 127.0, error_type)))


def quantize_color(value, error_type=ValueError):
	try:
		value = float(value)
	except (TypeError, ValueError, OverflowError):
		raise error_type("structural-profile-mismatch:non-finite-color")
	if not math.isfinite(value):
		raise error_type("structural-profile-mismatch:non-finite-color")
	return max(0, min(255, round_half_away_from_zero(
		max(0.0, min(1.0, value)) * 255.0, error_type)))


def quantize_weights(values, error_type=ValueError):
	if not values or len(values) > 6:
		raise error_type("structural-profile-mismatch:weight-count")
	if any(not math.isfinite(value) or value <= 0.0 for value in values):
		raise error_type("structural-profile-mismatch:weight-sum")
	total = sum(values)
	if not math.isfinite(total) or total <= 0.0:
		raise error_type("structural-profile-mismatch:weight-sum")
	scaled = [float(value) * 255.0 / total for value in values]
	result = [int(math.floor(value)) for value in scaled]
	remaining = 255 - sum(result)
	order = sorted(range(len(result)), key=lambda index: (
		-(scaled[index] - result[index]), index))
	for index in order[:remaining]:
		result[index] += 1
	return tuple(result + [0] * (8 - len(result)))


def _validate_bone_map_count(bone_map_count, error_type):
	if (isinstance(bone_map_count, bool) or
			not isinstance(bone_map_count, int) or
			bone_map_count <= 0 or bone_map_count > 1024):
		raise error_type("structural-profile-mismatch:bone-map-count")
	return bone_map_count


def pack_six_u10(slots, bone_map_count, expected_separator=3,
		error_type=ValueError):
	_validate_bone_map_count(bone_map_count, error_type)
	if not slots or len(slots) > 6:
		raise error_type("structural-profile-mismatch:weight-count")
	if any(isinstance(slot, bool) or not isinstance(slot, int) for slot in slots):
		raise error_type("structural-profile-mismatch:bone-slot-type")
	if len(set(slots)) != len(slots):
		raise error_type("structural-profile-mismatch:duplicate-bone-slot")
	if any(slot < 0 or slot >= bone_map_count for slot in slots):
		raise error_type("bone-index-out-of-range")
	if (isinstance(expected_separator, bool) or
			not isinstance(expected_separator, int) or
			expected_separator < 0 or expected_separator > 3):
		raise error_type("invalid-six-u10-separator")
	padded = tuple(slots) + (0,) * (6 - len(slots))
	return (padded[0] | padded[1] << 10 | padded[2] << 20 |
		expected_separator << 30 | padded[3] << 32 | padded[4] << 42 |
		padded[5] << 52 | expected_separator << 62)


def decode_six_u10(value, bone_map_count, expected_separator=3,
		error_type=ValueError):
	_validate_bone_map_count(bone_map_count, error_type)
	if (((value >> 30) & 3) != expected_separator or
			((value >> 62) & 3) != expected_separator):
		raise error_type("invalid-six-u10-separator")
	indices = (
		value & 0x3FF,
		(value >> 10) & 0x3FF,
		(value >> 20) & 0x3FF,
		(value >> 32) & 0x3FF,
		(value >> 42) & 0x3FF,
		(value >> 52) & 0x3FF,
	)
	if any(index >= bone_map_count for index in indices):
		raise error_type("bone-index-out-of-range")
	return indices


def validate_vector(value, count, token, error_type=ValueError):
	try:
		if len(value) != count:
			raise error_type("structural-profile-mismatch:" + token)
		result = tuple(float(value[index]) for index in range(count))
	except error_type:
		raise
	except (TypeError, ValueError, IndexError, AttributeError, OverflowError):
		raise error_type("structural-profile-mismatch:" + token)
	if any(not math.isfinite(component) for component in result):
		raise error_type("structural-profile-mismatch:non-finite-" + token)
	return result


def transform_point_row_vector(position, matrix):
	return tuple(
		position[0] * matrix[axis] + position[1] * matrix[4 + axis] +
		position[2] * matrix[8 + axis] + matrix[12 + axis]
		for axis in range(3)
	)


def topology_hash(positions, indices, error_type=ValueError):
	if len(indices) % 3:
		raise error_type("structural-profile-mismatch:index-count")
	triangles = []
	for start in range(0, len(indices), 3):
		triangle = []
		for index in indices[start:start + 3]:
			if index < 0 or index >= len(positions):
				raise error_type("index-out-of-range")
			rounded = [round(float(value), 6) for value in positions[index]]
			if any(not math.isfinite(value) for value in rounded):
				raise error_type(
					"structural-profile-mismatch:non-finite-position")
			triangle.append([0.0 if value == 0.0 else value for value in rounded])
		triangles.append(sorted(triangle))
	payload = json.dumps(sorted(triangles), sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


