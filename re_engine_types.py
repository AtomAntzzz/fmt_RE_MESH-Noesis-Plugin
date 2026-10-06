"""Shared value types and exceptions."""

from collections import namedtuple
import struct
from re_engine_binary import checked_range, read_scalar

MeshCapability = namedtuple("MeshCapability", (
	"key", "internal_version", "header_layout",
	"mesh_buffer_layout", "submesh_layout", "bone_index_layout",
))

class MeshProfileError(Exception):
	pass

class MaterialProfileError(Exception):
	pass


# MDF and TEX share this error convention; generic binary reads stay independent.
def _materialCheckedRange(data, start, size, label):
	def materialRangeError(token):
		prefix = "offset-out-of-bounds:"
		if token.startswith(prefix):
			token = token[len(prefix):] + "-out-of-bounds"
		return MaterialProfileError(token)
	return checked_range(data, start, size, label, materialRangeError)

def _materialScalar(data, offset, fmt, label):
	_materialCheckedRange(data, offset, struct.calcsize(fmt), label)
	return read_scalar(data, offset, fmt, label, MaterialProfileError)

DoubleClickTimer = namedtuple("DoubleClickTimer", "name idx timer")

BoneHeader = namedtuple("BoneHeader", "name pos rot index parentIndex hash mat")

BoneClipHeader = namedtuple("BoneClipHeader", "boneIndex trackFlags boneHash trackHeaderOffset")

BoneTrack = namedtuple("BoneTrack", "flags keyCount frameRate maxFrame frameIndOffs frameDataOffs unpackDataOffs")

Unpacks = namedtuple("Unpacks", "max min")

UnpackVec = namedtuple("UnpackVec", "x y z w")
