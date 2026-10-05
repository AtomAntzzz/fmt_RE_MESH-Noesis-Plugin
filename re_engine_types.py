"""Shared value types and exceptions."""

from collections import namedtuple

MeshCapability = namedtuple("MeshCapability", (
	"key", "internal_version", "header_layout",
	"mesh_buffer_layout", "submesh_layout", "bone_index_layout",
))

class MeshProfileError(Exception):
	pass

class MaterialProfileError(Exception):
	pass

DoubleClickTimer = namedtuple("DoubleClickTimer", "name idx timer")

BoneHeader = namedtuple("BoneHeader", "name pos rot index parentIndex hash mat")

BoneClipHeader = namedtuple("BoneClipHeader", "boneIndex trackFlags boneHash trackHeaderOffset")

BoneTrack = namedtuple("BoneTrack", "flags keyCount frameRate maxFrame frameIndOffs frameDataOffs unpackDataOffs")

Unpacks = namedtuple("Unpacks", "max min")

UnpackVec = namedtuple("UnpackVec", "x y z w")
