"""Motlist implementation bound to one plugin runtime."""

import copy
import math
from re_engine_config import (
	formats,
)
from re_engine_types import (
	BoneClipHeader,
	BoneHeader,
	BoneTrack,
	UnpackVec,
	Unpacks,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'NoeBitStream',
	'NoeBone',
	'NoeKeyFramedAnim',
	'NoeKeyFramedBone',
	'NoeKeyFramedValue',
	'NoeQuat',
	'NoeQuat3',
	'NoeVec3',
	'NoeVec4',
	'convertBits',
	'dialogOptions',
	'fDefaultMeshScale',
	'findGameName',
	'hash_wide',
	'motFile',
	'noesis',
	'readPackedBitsVec3',
	'readUIntAt',
	'readUnicodeStringAt',
	'sGameName',
	'skipToNextLine',
)


def bind(runtime):
	def readPackedBitsVec3(packedInt, numBits):
		limit = 2**numBits-1
		x = ((packedInt >> 0) 		    & limit) / limit
		y = ((packedInt >> (numBits*1)) & limit) / limit
		z = ((packedInt >> (numBits*2)) & limit) / limit
		return runtime.NoeVec3((x, y, z))

	def convertBits(packedInt, numBits):
		return packedInt / (2**numBits-1)

	def skipToNextLine(bs):
		bs.seek(bs.tell() + 16 - (bs.tell() % 16))

	def wRot(quat3):
		RotationW = 1.0 - (quat3[0] * quat3[0] + quat3[1] * quat3[1] + quat3[2] * quat3[2]);
		if RotationW > 0:
			return math.sqrt(RotationW)
		return 0

	class motFile:

		def __init__(self, dataBytesArray, motlist=[], start=0, motionID=""):
			self.bs = runtime.NoeBitStream(dataBytesArray)
			bs = self.bs
			self.start = start
			self.anim = None
			self.frameCount = 0
			self.motlist = motlist
			self.bones = []
			self.version = bs.readUInt()
			bs.seek(12)
			self.motSize = bs.readUInt()
			self.offsToBoneHdrOffs = bs.readUInt64()
			self.boneHdrOffset = 0
			self.boneClipHdrOffset = bs.readUInt64()
			bs.seek(8,1)
			if self.version >= 456:
				bs.seek(8,1)
				clipFileOffset = bs.readUInt64()
				jmapOffset = bs.readUInt64()
				exDataOffset  = bs.readUInt64()
				bs.seek(16,1)
			else:
				self.jmapOffset = bs.readUInt64()
				self.clipFileOffset = bs.readUInt64()
				bs.seek(16,1)
				self.exDataOffset = bs.readUInt64()
			nameOffs = bs.readUInt64()
			self.name = runtime.readUnicodeStringAt(bs, nameOffs)
			self.frameCount = bs.readFloat()
			self.name += " (" + str(int(self.frameCount)) + " frames)" + motionID
			self.blending = bs.readFloat()
			self.uknFloat0 = bs.readFloat()
			self.uknFloat0 = bs.readFloat()
			self.boneCount = bs.readShort()
			self.boneClipCount = bs.readShort()
			self.clipCount = bs.readByte()
			self.uknCount = bs.readByte()
			self.frameRate = bs.readShort()
			self.uknCount2 = bs.readShort()
			self.ukn3 = bs.readShort()
			self.boneHeaders = []
			self.boneClipHeaders = []
			self.kfBones = []
			self.doSkip = False

		def checkIfSyncMot(self, other):
			return (self.frameCount == other.frameCount)
			'''if self.frameCount == other.frameCount:
				boneNames = [self.motlist.bones[kfBone.boneIndex].name.lower() for kfBone in self.kfBones]
				otherBoneNames = [other.motlist.bones[kfBone.boneIndex].name.lower() for kfBone in other.kfBones]
				counter = 0
				for boneName in boneNames:
					if boneName in otherBoneNames:
						counter += 1
				return (counter / len(boneNames) < 0.25)'''


		def readFrame(self, ftype, flags, unpacks):
			bs = self.bs
			compression = flags & 0xFF000
			if ftype=="pos" or ftype=="scl":
				defScaleVec = runtime.NoeVec3((runtime.fDefaultMeshScale, runtime.fDefaultMeshScale, runtime.fDefaultMeshScale))
				if compression == 0x00000:
					output = runtime.NoeVec3((bs.readFloat(), bs.readFloat(), bs.readFloat())) * defScaleVec
				elif compression == 0x20000:
					rawVec = runtime.readPackedBitsVec3(bs.readUShort(), 5)
					if self.version <= 65:
						output = runtime.NoeVec3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.z, unpacks.max.y * rawVec[2] + unpacks.min.z)) * defScaleVec
					else:
						output = runtime.NoeVec3((unpacks.max.x * rawVec[0] + unpacks.max.w, unpacks.max.y * rawVec[1] + unpacks.min.x, unpacks.max.z * rawVec[2] + unpacks.min.y)) * defScaleVec
				elif compression == 0x24000:
					x = y = z = unpacks.max.x * runtime.convertBits(bs.readUShort(), 16) + unpacks.min.x
					output = runtime.NoeVec3((x, y, z)) * defScaleVec
				elif compression == 0x44000:
					x = y = z = unpacks.max.x * bs.readFloat() + unpacks.min.x
					output = runtime.NoeVec3((x, y, z)) * defScaleVec
				elif compression == 0x40000 or (compression == 0x30000 and self.version <= 65):
					rawVec = runtime.readPackedBitsVec3(bs.readUInt(), 10)
					if self.version <= 65:
						output = runtime.NoeVec3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)) * defScaleVec
					else:
						output = runtime.NoeVec3((unpacks.max.x * rawVec[0] + unpacks.max.w, unpacks.max.y * rawVec[1] + unpacks.min.x, unpacks.max.z * rawVec[2] + unpacks.min.y)) * defScaleVec
				elif compression == 0x70000:
					rawVec = runtime.readPackedBitsVec3(bs.readUInt64(), 21)
					output = runtime.NoeVec3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)) * defScaleVec
				elif compression == 0x80000:
					rawVec = runtime.readPackedBitsVec3(bs.readUInt64(), 21)
					output = runtime.NoeVec3((unpacks.max.x * rawVec[0] + unpacks.max.w, unpacks.max.y * rawVec[1] + unpacks.min.x, unpacks.max.z * rawVec[2] + unpacks.min.y)) * defScaleVec
				elif (compression == 0x31000 and self.version <= 65) or (compression == 0x41000 and self.version >= 78): #LoadVector3sXAxis
					output = runtime.NoeVec3((bs.readFloat(), unpacks.max.y, unpacks.max.z)) * defScaleVec
				elif (compression == 0x32000 and self.version <= 65) or (compression == 0x42000 and self.version >= 78): #LoadVector3sYAxis
					output = runtime.NoeVec3((unpacks.max.x, bs.readFloat(), unpacks.max.z)) * defScaleVec
				elif (compression == 0x33000 and self.version <= 65) or (compression == 0x43000 and self.version >= 78): #LoadVector3sZAxis
					output = runtime.NoeVec3((unpacks.max.x, unpacks.max.y, bs.readFloat())) * defScaleVec
				elif compression == 0x21000:
					output = runtime.NoeVec3((unpacks.max.x * runtime.convertBits(bs.readUShort(), 16) + unpacks.max.y, unpacks.max.z, unpacks.max.w)) * defScaleVec
				elif compression == 0x22000:
					output = runtime.NoeVec3((unpacks.max.y, unpacks.max.x * runtime.convertBits(bs.readUShort(), 16) + unpacks.max.z, unpacks.max.w)) * defScaleVec
				elif compression == 0x23000:
					output = runtime.NoeVec3((unpacks.max.y, unpacks.max.z, unpacks.max.x * runtime.convertBits(bs.readUShort(), 16) + unpacks.max.w)) * defScaleVec
				else:
					print("Unknown", "Translation" if ftype=="pos" else "Scale", "type:", "0x"+'{:02X}'.format(compression))
					output = runtime.NoeVec3((0,0,0)) if ftype=="pos" else runtime.NoeVec3((100,100,100))
			elif ftype=="rot":
				if compression == 0x00000: #LoadQuaternionsFull
					output = runtime.NoeQuat((bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat())).transpose()
				elif compression == 0xB0000 or compression == 0xC0000: #LoadQuaternions3Component
					#rawVec = [bs.readFloat(), bs.readFloat(), bs.readFloat()]
					#output = NoeQuat((rawVec[0], rawVec[1], rawVec[2], wRot(rawVec))).transpose()
					output = runtime.NoeQuat3((bs.readFloat(), bs.readFloat(), bs.readFloat())).toQuat().transpose()
				elif compression == 0x20000: #//LoadQuaternions5Bit RE3
					rawVec = runtime.readPackedBitsVec3(bs.readUShort(), 5)
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif compression == 0x21000:
					output = runtime.NoeQuat3((unpacks.max.x * runtime.convertBits(bs.readUShort(), 16) + unpacks.max.y, 0, 0)).toQuat().transpose()
				elif compression == 0x22000:
					output = runtime.NoeQuat3((0, unpacks.max.x * runtime.convertBits(bs.readUShort(), 16) + unpacks.max.y, 0)).toQuat().transpose()
				elif compression == 0x23000:
					output = runtime.NoeQuat3((0, 0, unpacks.max.x * runtime.convertBits(bs.readUShort(), 16) + unpacks.max.y)).toQuat().transpose()
				elif compression == 0x30000 and self.version >= 78: #LoadQuaternions8Bit RE3
					rawVec = [runtime.convertBits(bs.readUByte(), 8), runtime.convertBits(bs.readUByte(), 8), runtime.convertBits(bs.readUByte(), 8)]
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif compression == 0x30000:
					rawVec = runtime.readPackedBitsVec3(bs.readUInt(), 10)
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif compression == 0x31000 or compression == 0x41000:
					output = runtime.NoeQuat3((bs.readFloat(), 0, 0)).toQuat().transpose()
				elif compression == 0x32000 or compression == 0x42000:
					output = runtime.NoeQuat3((0, bs.readFloat(), 0)).toQuat().transpose()
				elif compression == 0x33000 or compression == 0x43000:
					output = runtime.NoeQuat3((0, 0, bs.readFloat())).toQuat().transpose()
				elif compression == 0x40000: #LoadQuaternions10Bit RE3
					rawVec = runtime.readPackedBitsVec3(bs.readUInt(), 10)
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif compression == 0x50000 and self.version <= 65: #LoadQuaternions16Bit RE2
					rawVec = [runtime.convertBits(bs.readUShort(), 16), runtime.convertBits(bs.readUShort(), 16), runtime.convertBits(bs.readUShort(), 16)]
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif compression == 0x50000: #LoadQuaternions13Bit RE3
					rawBytes = [bs.readUByte(), bs.readUByte(), bs.readUByte(), bs.readUByte(), bs.readUByte()]
					retrieved = (rawBytes[0] << 32) | (rawBytes[1] << 24) | (rawBytes[2] << 16) | (rawBytes[3] << 8) | (rawBytes[4] << 0)
					rawVec = runtime.readPackedBitsVec3(retrieved, 13)
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif compression == 0x60000: #LoadQuaternions16Bit RE3
					#output = NoeQuat((0,0,0,1))
					rawVec = [runtime.convertBits(bs.readUShort(), 16), runtime.convertBits(bs.readUShort(), 16), runtime.convertBits(bs.readUShort(), 16)]
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif (compression == 0x70000 and self.version <= 65) or (compression == 0x80000 and self.version >= 78): #LoadQuaternions21Bit RE2 and LoadQuaternions21Bit RE3
					rawVec = runtime.readPackedBitsVec3(bs.readUInt64(), 21)
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				elif compression == 0x70000 and self.version >= 78: #LoadQuaternions18Bit RE3
					rawBytes = [bs.readUByte(), bs.readUByte(), bs.readUByte(), bs.readUByte(), bs.readUByte(), bs.readUByte(), bs.readUByte()]
					retrieved = (rawBytes[0] << 48) | (rawBytes[1] << 40) | (rawBytes[2] << 32) | (rawBytes[3] << 24) | (rawBytes[4] << 16) | (rawBytes[5] << 8) | (rawBytes[6] << 0)
					rawVec = runtime.readPackedBitsVec3(retrieved, 18)
					output = runtime.NoeQuat3((unpacks.max.x * rawVec[0] + unpacks.min.x, unpacks.max.y * rawVec[1] + unpacks.min.y, unpacks.max.z * rawVec[2] + unpacks.min.z)).toQuat().transpose()
				else:
					print("Unknown Rotation type:", "0x"+'{:02X}'.format(compression))
					output = runtime.NoeQuat((0,0,0,1))
			return output

		# Used a lot for merging+moving skeletons of animations and meshes together:
		def readBoneHeaders(self):
			bs = self.bs
			boneHdrOffs = 0
			if self.offsToBoneHdrOffs:
				bs.seek(self.offsToBoneHdrOffs)
				self.boneHdrOffset = bs.readUInt64()
				count = bs.readUInt64()
				if self.boneHdrOffset and count == self.boneCount:
					boneHdrOffs = self.boneHdrOffset
			if boneHdrOffs:
				bs.seek(boneHdrOffs)
				for i in range(count):
					bs.seek(self.boneHdrOffset+80*i)
					boneName = runtime.readUnicodeStringAt(bs, bs.readUInt64())
					#boneName = self.motlist.meshBones[i].name if i < len(self.motlist.meshBones) else boneName #SF6 facial anims test
					parentOffset = bs.readUInt64()
					parentIndex = int((parentOffset-self.boneHdrOffset)/80) if parentOffset else -1
					bs.seek(16,1)
					translation = runtime.NoeVec4((bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat()))
					quat = runtime.NoeQuat((bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat())).transpose()
					index = bs.readUInt()
					boneHash = bs.readUInt()
					mat = quat.toMat43()
					mat[3] = translation.toVec3() * runtime.fDefaultMeshScale
					self.boneHeaders.append(BoneHeader(name=boneName, pos=translation, rot=quat, index=index, parentIndex=parentIndex, hash=boneHash, mat=mat))
				self.motlist.boneHeaders = self.motlist.boneHeaders or self.boneHeaders
			elif self.motlist.boneHeaders:
				self.boneHeaders = self.motlist.boneHeaders
			elif not self.motlist.searchedForBoneHeaders:
				self.motlist.findBoneHeaders()
			else:
				print("Failed to find bone headers:", self.name)
				return 0

			self.bones = []
			if not runtime.dialogOptions.dialog or not runtime.dialogOptions.dialog.args.get("mesh"):

				meshBoneNames = [bone.name.lower() for bone in self.motlist.meshBones]
				motlistBoneNames = [bone.name.lower() for bone in self.motlist.bones]

				for i, boneHeader in enumerate(self.boneHeaders):
					if not meshBoneNames or boneHeader.name.lower() in meshBoneNames: #always use additive animations when loading onto meshes
						bone = runtime.NoeBone(len(self.bones), boneHeader.name, boneHeader.mat, self.boneHeaders[boneHeader.parentIndex].name if boneHeader.parentIndex != -1 else None, boneHeader.parentIndex)
						self.bones.append(bone)

				selfBoneNames = [bone.name.lower() for bone in self.bones]
				addedBones = []
				for i, bone in enumerate(self.bones):
					if bone.parentName and bone.parentName.lower() in motlistBoneNames:
						bone.parentIndex = motlistBoneNames.index(bone.parentName.lower())
					if bone.name.lower() not in motlistBoneNames:
						bone.index = len(self.motlist.bones)
						self.motlist.bones.append(bone)
						motlistBoneNames.append(bone.name.lower())
						addedBones.append(bone)
				for b, bone in enumerate(self.bones):
					if bone.parentIndex != -1 and bone.parentName.lower() in motlistBoneNames:
						mat = self.boneHeaders[b].mat
						bone.setMatrix(mat * self.motlist.bones[motlistBoneNames.index(bone.parentName.lower())].getMatrix())
						'''if bone in addedBones:
							mat = NoeMat43() #remove posed rotation from anim skeleton, and relocate bone to merged parent bone
							mat[3] = self.boneHeaders[b].pos.toVec3()'''
						'''if bone in addedBones:
							childBones = getChildBones(bone, self.motlist.bones, True)
							childMats = []
							for childBone in childBones:
								#print("moving child", childBone.name)
								oldIndex = selfBoneNames.index(childBone.name.lower())
								childMats.append(self.boneHeaders[oldIndex].mat * self.bones[selfBoneNames.index(childBone.parentName.lower())].getMatrix())'''

						'''if bone in addedBones:
							for c, childBone in enumerate(childBones):
								#childBone.setMatrix(childMats[c] * self.motlist.bones[motlistBoneNames.index(childBone.parentName.lower())].getMatrix())
								print("moving child", childBone.name)
								childBone.setMatrix(NoeMat43())'''

		def read(self):
			bs = self.bs

			if not self.boneHeaders:
				self.readBoneHeaders()

			bnClipSz = 24 if self.version==65 else 16 if self.version==43 else 12
			for i in range(self.boneClipCount):
				bs.seek(self.boneClipHdrOffset+bnClipSz*i)
				#print(i, "bnCLipHdr at", bs.tell()+self.start)
				if self.version == 65:
					index = bs.readUShort()
					trackFlags = bs.readUShort()
					boneHash = bs.readUInt()
					bs.seek(8,1)
					trackHeaderOffset = bs.readUInt64()
				else:
					index = bs.readUShort()
					trackFlags = bs.readUShort()
					boneHash = bs.readUInt()
					if  self.version == 43:
						trackHeaderOffset = bs.readUInt64()
					else:
						trackHeaderOffset = bs.readUInt()
				self.boneClipHeaders.append(BoneClipHeader(boneIndex=index, trackFlags=trackFlags, boneHash=boneHash, trackHeaderOffset=trackHeaderOffset))

			runtime.skipToNextLine(bs)
			self.boneClips = []
			for i in range(self.boneClipCount):
				boneClipHdr = self.boneClipHeaders[i]
				#if self.boneHeaders[boneClipHdr.boneIndex].name in
				#if (i == 0 and self.boneHeaders[boneClipHdr.boneIndex].name != self.motlist.bones[0].name):
				#	print(self.name, "Ignoring all keyframes for ", self.boneHeaders[boneClipHdr.boneIndex].name)
				#	continue
				tracks = {"pos": None, "rot": None, "scl": None }
				bs.seek(boneClipHdr.trackHeaderOffset)
				for t in range(3):
					if boneClipHdr.trackFlags & (1 << t):
						flags = bs.readUInt()
						keyCount = bs.readUInt()
						frameRate = maxFrame = 0
						if self.version >= 78:
							frameIndOffs = bs.readUInt()
							frameDataOffs = bs.readUInt()
							unpackDataOffs = bs.readUInt()
						else:
							frameRate = float(bs.readUInt())
							maxFrame = bs.readFloat()
							frameIndOffs = bs.readUInt64()
							frameDataOffs = bs.readUInt64()
							unpackDataOffs = bs.readUInt64()
						newTrack = BoneTrack(flags=flags, keyCount=keyCount, frameRate=frameRate, maxFrame=maxFrame, frameIndOffs=frameIndOffs, frameDataOffs=frameDataOffs, unpackDataOffs=unpackDataOffs)
						if (boneClipHdr.trackFlags & (1)) and not tracks.get("pos"):
							tracks["pos"] = newTrack
						elif (boneClipHdr.trackFlags & (1 << 1)) and not tracks.get("rot"):
							tracks["rot"] = newTrack
						elif (boneClipHdr.trackFlags & (1 << 2)) and not tracks.get("scl"):
							tracks["scl"] = newTrack
				if i == 0 and runtime.dialogOptions.dialog and runtime.dialogOptions.dialog.pak and self.boneHeaders[boneClipHdr.boneIndex].name != runtime.dialogOptions.dialog.pak.bones[0].name:
				#if i == 0 and self.boneHeaders[boneClipHdr.boneIndex].name != "root":
					print(self.name, ": Ignoring all keyframes for ", self.boneHeaders[boneClipHdr.boneIndex].name)
					tracks["pos"] = tracks["rot"] = tracks["scl"] = None #remove local root bone translations/rotations for mounted animations like facials
				elif runtime.dialogOptions.doForceCenter and (self.boneHeaders[boneClipHdr.boneIndex].parentIndex == 0 or i == 0):
					print(self.name, ": Ignoring position keyframes for ", self.boneHeaders[boneClipHdr.boneIndex].name)
					tracks["pos"] = None
				self.boneClips.append(tracks)

			for i, boneClip in enumerate(self.boneClips):
				motlistBoneIndex = self.motlist.boneHashes.get(self.boneClipHeaders[i].boneHash)
				if motlistBoneIndex != None:
					kfBone = runtime.NoeKeyFramedBone(motlistBoneIndex)
					for ftype in ["pos", "rot", "scl"]:
						fHeader = boneClip.get(ftype)
						if fHeader:
							keyCompression = fHeader.flags >> 20
							keyReadFunc = bs.readUInt if keyCompression==5 else bs.readUByte if keyCompression==2 else bs.readUShort
							bs.seek(fHeader.frameIndOffs)
							keyTimes = []
							for k in range(fHeader.keyCount):
								keyTimes.append(keyReadFunc() if fHeader.frameIndOffs else 0)
							if fHeader.unpackDataOffs:
								bs.seek(fHeader.unpackDataOffs)
								unpackMax = UnpackVec(x=bs.readFloat(), y=bs.readFloat(), z=bs.readFloat(), w=bs.readFloat())
								unpackMin = UnpackVec(x=bs.readFloat(), y=bs.readFloat(), z=bs.readFloat(), w=bs.readFloat())
							else:
								unpackMax = unpackMin = UnpackVec(x=0, y=0, z=0, w=0)
							unpackValues = Unpacks(max=unpackMax, min=unpackMin)
							frames = []
							bs.seek(fHeader.frameDataOffs)
							for f in range(fHeader.keyCount):
								frame = self.readFrame(ftype, fHeader.flags, unpackValues)
								if ftype == "scl":
									frame /= 100
								kfValue = runtime.NoeKeyFramedValue(keyTimes[f], frame)
								frames.append(kfValue)
							if ftype == "pos": # and self.motlist.bones[motlistBoneIndex].parentIndex != 0:#kfBoneNames:
								kfBone.setTranslation(frames, runtime.noesis.NOEKF_TRANSLATION_VECTOR_3)
							elif ftype == "rot":
								kfBone.setRotation(frames, runtime.noesis.NOEKF_ROTATION_QUATERNION_4)
							elif ftype == "scl":
								kfBone.setScale(frames, runtime.noesis.NOEKF_SCALE_VECTOR_3)
					self.kfBones.append(kfBone)
			motEnd = bs.tell()

	class motlistFile:

		def __init__(self, data, path=""):
			# Shared state is owned by runtime.
			self.bs = runtime.NoeBitStream(data)
			bs = self.bs
			self.path = path
			self.bones = []
			self.boneHashes = {}
			self.boneHeaders = []
			self.anims = []
			self.mots = []
			self.meshBones = []
			self.searchedForBoneHeaders = False
			self.totalFrames = 0
			self.version = bs.readInt()
			bs.seek(16)
			pointersOffset = bs.readUInt64()
			motionIDsOffset = bs.readUInt64()
			self.name = runtime.readUnicodeStringAt(bs, bs.readUInt64())
			bs.seek(8, 1)
			numOffsets = bs.readUInt()
			bs.seek(pointersOffset)
			self.motionIDs = {}
			self.pointers = []
			runtime.sGameName = runtime.findGameName("."+str(self.version), "mlistExt")

			for i in range(numOffsets):
				if "motionIDsData" in formats[runtime.sGameName]:
					bs.seek(motionIDsOffset + i*formats[runtime.sGameName]["motionIDsData"][0] + formats[runtime.sGameName]["motionIDsData"][1])
					self.motionIDs[i] = bs.readUShort()

				bs.seek(pointersOffset + i*8)
				motAddress = bs.readUInt64()
				if motAddress and motAddress not in self.pointers and runtime.readUIntAt(bs, motAddress+4) == 544501613: # 'mot'
					self.pointers.append(motAddress)
					bs.seek(motAddress)
					mot = runtime.motFile(bs.readBytes(bs.getSize()-bs.tell()), self, motAddress, " ID: " + str(self.motionIDs[i] if i in self.motionIDs else ""))
					self.mots.append(mot)

		def findBoneHeaders(self):
			self.searchedForBoneHeaders = True
			for mot in self.mots:
				mot.readBoneHeaders()
				if self.boneHeaders:
					print("Using bone headers from", mot.name)
					break

		def readBoneHeaders(self, motNamesToLoad=[]):
			self.boneHashes = {}
			for mot in self.mots:
				if not motNamesToLoad or mot.name in motNamesToLoad:
					mot.readBoneHeaders()
			for i, bone in enumerate(self.bones):
				hash = runtime.hash_wide(bone.name, True)
				self.boneHashes[hash] = i #bone.index

		def read(self, motNamesToLoad=[]):
			bs = self.bs
			self.readBoneHeaders(motNamesToLoad)
			for i, mot in enumerate(self.mots):
				if not motNamesToLoad or mot.name in motNamesToLoad and not mot.doSkip:
					mot.read()

		def makeAnims(self, motNamesToLoad=[]):
			bs = self.bs
			motsToLoad = []
			#check for sync mots:
			for i, mot in enumerate(self.mots):
				if not motNamesToLoad or mot.name in motNamesToLoad and not mot.doSkip:
					motsToLoad.append(mot)
			if (runtime.dialogOptions.doSync or runtime.dialogOptions.doForceMergeAnims) and runtime.dialogOptions.motDialog and len(runtime.dialogOptions.motDialog.loadItems) > 0:
				allLoadItems = copy.copy(runtime.dialogOptions.motDialog.loadItems)
				allLoadPaths = copy.copy(runtime.dialogOptions.motDialog.fullLoadItems)
				for j, otherMotName in enumerate(runtime.dialogOptions.motDialog.loadItems):
					if "[ALL]" in otherMotName:
						for mot in runtime.dialogOptions.motDialog.loadedMlists[runtime.dialogOptions.motDialog.fullLoadItems[j]].mots:
							if mot.name not in allLoadItems:
								allLoadItems.append(mot.name)
								allLoadPaths.append(runtime.dialogOptions.motDialog.fullLoadItems[j])
				for i, mot in enumerate(motsToLoad):
					mlistBoneNames = [bone.name.lower() for bone in self.bones]
					for otherPath, otherMlist in runtime.dialogOptions.motDialog.loadedMlists.items():
						if otherMlist == self:
							continue
						otherMotNames = [otherMot.name for otherMot in otherMlist.mots]
						for j, otherMotName in enumerate(allLoadItems):
							if mot.motlist.path != allLoadPaths[j] and "[ALL]" not in otherMotName and otherMotName in otherMotNames and not otherMlist.mots[otherMotNames.index(otherMotName)].doSkip and (runtime.dialogOptions.doForceMergeAnims or mot.checkIfSyncMot(otherMlist.mots[otherMotNames.index(otherMotName)])):
								syncMot = otherMlist.mots[otherMotNames.index(otherMotName)]
								existingKfBoneNames = [self.bones[kfBone.boneIndex].name for kfBone in mot.kfBones]
								for b, kfBone in enumerate(syncMot.kfBones):
									bone = syncMot.motlist.bones[kfBone.boneIndex]
									if bone.name.lower() not in mlistBoneNames:
										bone.index = len(self.bones)
										self.bones.append(bone)
										mlistBoneNames.append(bone.name.lower())
									if (kfBone.hasAnyKeys() and (bone.name not in existingKfBoneNames or not mot.kfBones[existingKfBoneNames.index(bone.name)].hasAnyKeys())):
										kfBone.boneIndex = mlistBoneNames.index(bone.name.lower())
										mot.kfBones.append(kfBone)
								print("Merged animation ", syncMot.name, "into", mot.name)
								syncMot.doSkip = True
			motsByName = []
			for i, mot in enumerate(motsToLoad):
				if not mot.doSkip:
					mot.anim = runtime.NoeKeyFramedAnim(mot.name, self.bones, mot.kfBones, 1)
					self.anims.append(mot.anim)
					motsByName.append(mot.name)
			if len(self.anims) > 0:
				print("\nImported", len(self.anims), "animations from motlist '", self.name, "':")
				for anim in self.anims:
					print(" @ " + str(int(self.totalFrames)), "	'", anim.name, "'")
					self.totalFrames += self.mots[motsByName.index(anim.name)].frameCount

	def motlistCheckType(data):
		bs = runtime.NoeBitStream(data)
		magic = runtime.readUIntAt(bs, 4)
		if magic == 1953721453:
			return 1
		else:
			print("Fatal Error: Unknown file magic: " + str(hex(magic) + " expected 'mlst'!"))
			return 0

	return (
		readPackedBitsVec3,
		convertBits,
		skipToNextLine,
		wRot,
		motFile,
		motlistFile,
		motlistCheckType,
	)
