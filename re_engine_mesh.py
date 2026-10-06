"""Mesh implementation bound to one plugin runtime."""

import json
import math
import os
import struct
from re_engine_config import (
	PRAGMATA_250707828,
	PRAGMATA_MPLY_250707828,
	formats,
)
from re_engine_types import (
	MeshProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'GetRootGameDir',
	'LoadExtractedDir',
	'NoeBitStream',
	'NoeBone',
	'NoeMat43',
	'NoeMat44',
	'NoeQuat',
	'NoeVec3',
	'SaveExtractedDir',
	'_parsePragmataMeshData',
	'_parsePragmataMplyData',
	'_pragmataMplyNoesisBatches',
	'_pragmataNoesisIndexSubmission',
	'_readMeshProfile',
	'bAddBoneNumbers',
	'bColorsEnabled',
	'bDebugMESH',
	'bDebugNormals',
	'bImportAllLODs',
	'bImportMaterialNames',
	'bMaterialsEnabled',
	'bNORMsEnabled',
	'bReadGroupIds',
	'bRenameMeshesToFilenames',
	'bRenderAsPoints',
	'bRotateBonesUpright',
	'bShorterNames',
	'bSkinningEnabled',
	'bTANGsEnabled',
	'bUVsEnabled',
	'bUseOldNamingScheme',
	'cleanBoneName',
	'dialogOptions',
	'extractedNativesPath',
	'fDefaultMeshScale',
	'feedPragmataMorphFrames',
	'hash_wide',
	'isMeshVer3',
	'loadPragmataStreamingCompanion',
	'noesis',
	'rapi',
	'readUIntAt',
	'sGameName',
	'sInputName',
	'setOffsets',
)


def getLegacyMeshLayout(ver, game_name):
	# Per-import layout; writer compatibility publishes a separate copy.
	layout = {}
	layout["BBskipBytes"] = 				8 	if ver == 1 else 0
	layout["numNodesLocation"] = 			18 	if ver < 3 else 20
	layout["LOD1OffsetLocation"] = 		24 	if ver < 3 else 32
	layout["bsHdrOffLocation"] = 			64 	if ver < 3 else 56
	layout["normalsRecalcOffsLocation"] = 56 	if ver < 3 else 64
	layout["vBuffHdrOffsLocation"] = 		80 	if ver < 3 else 72
	layout["floatsHdrOffsLocation"] = 	72 	if ver < 3 else 96
	layout["bonesOffsLocation"] = 		48 	if ver < 3 else 104
	layout["nodesIndicesOffsLocation"] = 	96 	if ver < 3 else 112
	layout["bsIndicesOffLocation"] = 		112 if ver < 3 else 128
	layout["namesOffsLocation"] = 		120 if ver < 3 else 144

	if game_name == "AJ_AAT" or game_name == "DD2" or game_name == "DRDR":
		layout["namesOffsLocation"] = 136 # on unrigged meshes its still 144

	return layout


def bindMeshVertexStreams(rapi, streams):
	"""Consume format-prepared streams in order, without copying their buffers."""
	methods = {
		"position": "rpgBindPositionBufferOfs",
		"normal": "rpgBindNormalBufferOfs",
		"tangent": "rpgBindTangentBufferOfs",
		"uv_scale_bias": "rpgSetUVScaleBias",
		"uv1": "rpgBindUV1BufferOfs",
		"uv2": "rpgBindUV2BufferOfs",
		"bone_map": "rpgSetBoneMap",
		"bone_indices": "rpgBindBoneIndexBufferOfs",
		"bone_weights": "rpgBindBoneWeightBufferOfs",
		"color": "rpgBindColorBufferOfs",
	}
	for semantic, arguments in streams:
		if semantic == "uv_scale_bias_fallback":
			# Legacy catches host failures as well as missing material UV metadata.
			try:
				rapi.rpgSetUVScaleBias(*arguments[0])
			except:
				rapi.rpgSetUVScaleBias(*arguments[1]())
		else:
			getattr(rapi, methods[semantic])(*arguments)


def submitMeshPrimitive(rapi, noesis, primitive):
	"""Submit prepared indices without changing format-specific point/clear policy."""
	rapi.rpgCommitTriangles(
		None if primitive["points"] else primitive["indices"],
		noesis.RPGEODATA_USHORT if primitive["index_width"] == 2 else noesis.RPGEODATA_UINT,
		primitive["count"], noesis.RPGEO_POINTS if primitive["points"] else noesis.RPGEO_TRIANGLE, 0x1)
	if primitive["clear_binds"]:
		rapi.rpgClearBufferBinds()


def bind(runtime):
	def feedPragmataMorphFrames(submesh, positions, blend_shapes):
		matching = [
			shape for shape in blend_shapes
			if (shape["vertex_start"] == submesh["vertex_start"] and
				shape["vertex_count"] == submesh["vertex_count"])
		]
		if not matching:
			return []
		vertex_start = submesh["vertex_start"]
		vertex_count = submesh["vertex_count"]
		if (vertex_start < 0 or vertex_count <= 0 or
				vertex_start + vertex_count > len(positions)):
			raise MeshProfileError(
				"structural-profile-mismatch:blend-submesh-vertex-range")
		names = []
		for shape in matching:
			if len(shape["deltas"]) != vertex_count:
				raise MeshProfileError(
					"structural-profile-mismatch:blend-shape-delta-count")
			absolute_positions = []
			for local_vertex_index in range(vertex_count):
				base = positions[vertex_start + local_vertex_index]
				delta = shape["deltas"][local_vertex_index]
				absolute = tuple(base[axis] + delta[axis] for axis in range(3))
				if any(not math.isfinite(value) for value in absolute):
					raise MeshProfileError(
						"structural-profile-mismatch:non-finite-morph-position")
				absolute_positions.append(absolute)
			position_buffer = b"".join(
				struct.pack("<3f", *position) for position in absolute_positions)
			runtime.rapi.rpgFeedMorphTargetPositions(
				position_buffer, runtime.noesis.RPGEODATA_FLOAT, 12)
			runtime.rapi.rpgCommitMorphFrame(vertex_count)
			names.append(shape["name"])
		runtime.rapi.rpgCommitMorphFrameSet()
		return names

	def setOffsets(ver):
		# Compatibility facade for existing writer/entry callers.
		for name, value in getLegacyMeshLayout(ver, runtime.sGameName).items():
			setattr(runtime, name, value)

	def findGameName(number, formatsKey):
		for gameName, dictionary in formats.items():
			if dictionary[formatsKey] == number:
				return gameName
		return ""

	class meshFile(object):

		def __init__(self, data, path=""):
			self.path = path or runtime.rapi.getInputName()
			self.data = data
			self.inFile = runtime.NoeBitStream(data)
			(self.capability, self.profileHeader, parsed, companion_path) = runtime._readMeshProfile(data, self.path)
			# Retain only an immutable input snapshot, and consume it on first load.
			self._profileSnapshot = (
				(data, self.path, parsed, companion_path) if isinstance(data, bytes) else None)
			self.importStats = None
			self.boneList = []
			self.matNames = []
			self.groupIDs = []
			self.matHashes = []
			self.matList = []
			self.texList = []
			self.texNames = []
			self.missingTexNames = []
			self.texColors = []
			self.fullBoneList = []
			self.fullTexList = []
			self.fullMatList = []
			self.fullRemapTable = []
			self.blendShapeNamesByMesh = {}
			self.setGameName()
			self.gameName = runtime.sGameName
			self.ver = formats[runtime.sGameName]["meshVersion"]
			self.layout = getLegacyMeshLayout(self.ver, self.gameName)
			self.mdfVer = formats[runtime.sGameName]["mdfVersion"]
			self.name = "LOD" if runtime.bShorterNames else "LODGroup"
			self.meshFile = None
			self.mdfFile = None
			self.pos = runtime.NoeVec3((0,0,0))
			self.rot = runtime.NoeQuat((0,0,0,1))
			self.scl = runtime.NoeVec3((1,1,1))
			self.uvBias = {}
			runtime.setOffsets(self.ver)

		def setGameName(self):
			# Shared state is owned by runtime.
			runtime.sGameName = "RE2"
			if self.capability in (PRAGMATA_250707828, PRAGMATA_MPLY_250707828):
				runtime.isMeshVer3 = True
				runtime.sGameName = "PRAGMATA"
				return
			meshVersion = runtime.readUIntAt(self.inFile, 4)
			runtime.isMeshVer3 = False
			if meshVersion == 220822879:
				runtime.isMeshVer3 = True
				runtime.sGameName = "RE4"
			elif (meshVersion == 220705151 and self.path.find(".220907984") != -1):
				runtime.isMeshVer3 = True
				runtime.sGameName = "ExoPrimal"
			elif ((meshVersion == 230403828 or meshVersion == 220705151) and (self.path.find(".230110883") != -1) or self.path.find(".220721329") != -1):
				runtime.isMeshVer3 = True
				runtime.sGameName = "SF6"
			elif meshVersion == 21041600: # or self.path.find(".2109108288") != -1: #RE2RT + RE3RT, and RE7RT
				runtime.sGameName = "RE7RT" if self.path.find(".220128762") != -1 else "RERT"
			elif self.path.find(".1808282334") != -1:
				runtime.sGameName = "DMC5"
			elif self.path.find(".1902042334") != -1:  #386270720
				runtime.sGameName = "RE3"
			elif self.path.find(".2102020001") != -1:
				runtime.sGameName = "ReVerse"
			elif meshVersion == 2020091500 or self.path.find(".2101050001") != -1:
				runtime.sGameName = "RE8"
			elif (meshVersion == 2007158797 or self.path.find(".2008058288") != -1): #Vanilla MHRise
				runtime.sGameName = "MHRise"
			elif (meshVersion == 21061800 or self.path.find(".2109148288") != -1):  #MHRise Sunbreak version
				runtime.sGameName = "MHRSunbreak"
			elif (meshVersion == 230406984 or self.path.find(".230612127") != -1): #Apollo Justice
				runtime.isMeshVer3 = True
				runtime.sGameName = "AJ_AAT"
			elif (meshVersion == 230517984 or self.path.find(".231011879") != -1): #DD2
				runtime.isMeshVer3 = True
				runtime.sGameName = "DD2"
			elif (meshVersion == 240423829 or self.path.find(".240424828") != -1): #DD2
				runtime.isMeshVer3 = True
				runtime.sGameName = "DRDR"

		'''MDF IMPORT ========================================================================================================================================================================'''

		'''MESH IMPORT ========================================================================================================================================================================'''

		def _loadPragmataMeshFile(self):
			snapshot = self._profileSnapshot
			self._profileSnapshot = None
			if snapshot is not None and snapshot[0] is self.data and snapshot[1] == self.path:
				parsed = snapshot[2]
				if snapshot[3] is not None:
					self.streamingCompanionPath = snapshot[3]
			else:
				streaming_data = None
				if (self.capability == PRAGMATA_MPLY_250707828 or
						self.profileHeader.get("streaming_entry_count")):
					self.streamingCompanionPath, streaming_data = runtime.loadPragmataStreamingCompanion(
						self.path)
				parsed = (
					runtime._parsePragmataMplyData(self.data, self.profileHeader, streaming_data)
					if self.capability == PRAGMATA_MPLY_250707828 else
					runtime._parsePragmataMeshData(self.data, self.profileHeader, streaming_data)
				)
			vertex_buffer = parsed["vertex_buffer"]
			vertex_elements = parsed["vertex_elements"]
			full_bones_offset = len(self.fullBoneList)
			full_remap_offset = len(self.fullRemapTable)
			self.materializedPreview = False
			if runtime.bMaterialsEnabled:
				self.materializedPreview = self._loadPragmataMaterialProfile(parsed["material_names"])

			self.boneList = []
			for bone in parsed["bones"]:
				matrix = runtime.NoeMat44.fromBytes(bone["local_matrix"]).toMat43()
				matrix[3] *= runtime.fDefaultMeshScale
				self.boneList.append(runtime.NoeBone(
					bone["index"], bone["name"], matrix, None, bone["parent_index"]
				))
			if self.boneList:
				self.boneList = runtime.rapi.multiplyBones(self.boneList)
			for bone in self.boneList:
				bone.index += full_bones_offset
				if bone.parentIndex != -1:
					bone.parentIndex += full_bones_offset
				elif full_bones_offset > 0:
					bone.parentIndex = 0
			self.fullBoneList.extend(self.boneList)
			self.fullRemapTable.extend([
				bone_index + full_bones_offset for bone_index in parsed["bone_map"]
			])

			decoded_indices = []
			for row in parsed["bone_indices"]:
				decoded_indices.extend([index + full_remap_offset for index in row])
			bone_index_buffer = struct.pack(
				"<" + "H" * len(decoded_indices), *decoded_indices
			)
			bone_weight_count = (
				len(parsed["bone_indices"][0]) if parsed["bone_indices"] else 0
			)
			if (len(parsed["bone_weights"]) != len(parsed["bone_indices"]) or
					any(len(row) != bone_weight_count for row in parsed["bone_indices"]) or
					any(len(row) != bone_weight_count for row in parsed["bone_weights"])):
				raise MeshProfileError("structural-profile-mismatch:decoded-weight-rows")
			bone_weight_buffer = b"".join(bytes(row) for row in parsed["bone_weights"])

			noesis_submeshes = (
				runtime._pragmataMplyNoesisBatches(parsed["submeshes"])
				if self.capability == PRAGMATA_MPLY_250707828 else
				parsed["submeshes"]
			)
			if not runtime.bImportAllLODs:
				noesis_submeshes = [
					submesh for submesh in noesis_submeshes
					if submesh["lod_index"] == 0
				]
			for submesh in noesis_submeshes:
				mesh_name = "LOD_" + str(submesh["lod_index"] + 1) + "_Group_" + str(
					submesh["group_id"]
				) + "_Sub_" + str(submesh["submesh_index"] + 1)
				material_name = parsed["material_names"][submesh["material_index"]]
				if material_name not in self.matNames:
					self.matNames.append(material_name)
				runtime.rapi.rpgSetName(mesh_name + "__" + material_name if runtime.bImportMaterialNames else mesh_name)
				runtime.rapi.rpgSetMaterial(material_name)
				runtime.rapi.rpgSetPosScaleBias(
					(runtime.fDefaultMeshScale, runtime.fDefaultMeshScale, runtime.fDefaultMeshScale), (0, 0, 0)
				)

				def profileVertexStreams():
					vertex_start = submesh["vertex_start"]
					position = vertex_elements[0]
					yield ("position", (vertex_buffer, runtime.noesis.RPGEODATA_FLOAT, position["stride"], position["offset"] + position["stride"] * vertex_start,))
					if runtime.bNORMsEnabled:
						normal = vertex_elements[1]
						normal_offset = normal["offset"] + normal["stride"] * vertex_start
						yield ("normal", (vertex_buffer, runtime.noesis.RPGEODATA_BYTE, normal["stride"], normal_offset,))
						if runtime.bTANGsEnabled:
							yield ("tangent", (vertex_buffer, runtime.noesis.RPGEODATA_BYTE, normal["stride"], normal_offset + 4,))
					if runtime.bUVsEnabled:
						uv = vertex_elements[2]
						yield ("uv_scale_bias", (runtime.NoeVec3((1, 1, 1)), runtime.NoeVec3((0, 0, 0)),))
						yield ("uv1", (vertex_buffer, runtime.noesis.RPGEODATA_HALFFLOAT, uv["stride"], uv["offset"] + uv["stride"] * vertex_start,))
					if runtime.bSkinningEnabled and 4 in vertex_elements:
						yield ("bone_map", (self.fullRemapTable,))
						yield ("bone_indices", (bone_index_buffer, runtime.noesis.RPGEODATA_USHORT, bone_weight_count * 2, vertex_start * bone_weight_count * 2, bone_weight_count,))
						yield ("bone_weights", (bone_weight_buffer, runtime.noesis.RPGEODATA_UBYTE, bone_weight_count, vertex_start * bone_weight_count, bone_weight_count,))
					if runtime.bColorsEnabled and 5 in vertex_elements:
						color = vertex_elements[5]
						yield ("color", (vertex_buffer, runtime.noesis.RPGEODATA_UBYTE, color["stride"], color["offset"] + color["stride"] * vertex_start, 4,))
				bindMeshVertexStreams(runtime.rapi, profileVertexStreams())

				morph_names = runtime.feedPragmataMorphFrames(
					submesh, parsed["positions"], parsed.get("blend_shapes", []))
				if morph_names:
					self.blendShapeNamesByMesh[mesh_name] = morph_names
					print("PRAGMATA_MORPH_FRAME_MAP_JSON:" + json.dumps({
						"mesh": mesh_name,
						"frames": [
							{"index": index, "source_name": name}
							for index, name in enumerate(morph_names)
						],
					}, sort_keys=True, separators=(",", ":")))

				if runtime.bRenderAsPoints:
					primitive = {"indices": None, "index_width": 2,
						"count": submesh["vertex_count"], "points": True, "clear_binds": True}
				else:
					index_buffer, index_width = runtime._pragmataNoesisIndexSubmission(
						submesh, self.capability)
					primitive = {"indices": index_buffer, "index_width": index_width,
						"count": submesh["index_count"], "points": False, "clear_binds": True}
				submitMeshPrimitive(runtime.rapi, runtime.noesis, primitive)

			self.importStats = parsed["stats"]
			return 1

		def loadMeshFile(self): #, mdlList):

			# Shared state is owned by runtime.
			if self.capability in (PRAGMATA_250707828, PRAGMATA_MPLY_250707828):
				return self._loadPragmataMeshFile()

			self.rootDir = runtime.GetRootGameDir(self.path)
			runtime.extractedNativesPath = runtime.LoadExtractedDir(runtime.sGameName)

			#Try to find & save extracted game dir for later if extracted game dir is unknown
			if runtime.extractedNativesPath == "":
				if (self.rootDir.lower().endswith("chunk_000\\natives\\" + formats[runtime.sGameName]["nDir"] + "\\")):
					print ("Saving extracted natives path...")
					if runtime.SaveExtractedDir(self.rootDir, runtime.sGameName):
						runtime.extractedNativesPath = self.rootDir

			bs = self.inFile
			magic = bs.readUInt()
			meshVersion = bs.readUInt()
			fileSize = bs.readUInt()
			deferredWarning = ""
			bDoSkin = True

			bs.seek(self.layout["numNodesLocation"])
			numNodes = bs.readUInt()
			bs.seek(self.layout["LOD1OffsetLocation"])
			LOD1Offs = bs.readUInt64()
			LOD2Offs = bs.readUInt64()
			occluderMeshOffs = bs.readUInt64()
			bs.seek(self.layout["vBuffHdrOffsLocation"])
			vBuffHdrOffs = bs.readUInt64()
			bs.seek(self.layout["bonesOffsLocation"])
			bonesOffs = bs.readUInt64()
			bs.seek(self.layout["nodesIndicesOffsLocation"])
			nodesIndicesOffs = bs.readUInt64()
			boneIndicesOffs = bs.readUInt64()
			#if sGameName == "AJ_AAT" or sGameName == "DD2":
			#	namesOffsLocation = 136 if bonesOffs > 0 else 144
			bs.seek(self.layout["namesOffsLocation"])
			namesOffs = bs.readUInt64()

			if LOD1Offs:
				bs.seek(LOD1Offs)
				countArray = bs.read("16B") #[0] = LODGroupCount, [1] = MaterialCount, [2] = UVChannelCount
				matCount = countArray[1]
				intFaces = countArray[6]
				bLoadedMats = False
				if not (runtime.noesis.optWasInvoked("-noprompt")) and not runtime.bRenameMeshesToFilenames and not runtime.rapi.noesisIsExporting() and not (runtime.dialogOptions.dialog != None and runtime.dialogOptions.doLoadTex == False):
					bLoadedMats = self.createMaterials(matCount)
				if runtime.bDebugMESH:
					print("Count Array")
					print(countArray)

			bs.seek(vBuffHdrOffs)
			vertElemHdrOffs = bs.readUInt64()
			vertBuffOffs = bs.readUInt64()

			if self.ver >= 3:
				uknVB = bs.readUInt64()
				vertBuffSize = bs.readUInt()
				face_buffOffsSF6 = bs.readUInt()
				faceBuffOffs = face_buffOffsSF6 + vertBuffOffs;
			else:
				faceBuffOffs = bs.readUInt64()
				if runtime.sGameName == "RERT" or runtime.sGameName == "RE7RT" or runtime.sGameName == "MHRSunbreak":
					uknInt64 = bs.readUInt64()
				vertBuffSize = bs.readUInt()
				faceBuffSize = bs.readUInt()

			vertElemCountA = bs.readUShort()
			vertElemCountB = bs.readUShort()
			faceBufferSize2nd = bs.readUInt64()
			blendshapesOffset = bs.readUInt()

			bs.seek(vertElemHdrOffs)
			vertElemHeaders = []
			positionIndex = -1
			normalIndex = -1
			colorIndex = -1
			uvIndex = -1
			uv2Index = -1
			weightIndex = -1

			for i in range (vertElemCountB):
				vertElemHeaders.append([bs.readUShort(), bs.readUShort(), bs.readUInt()])
				if vertElemHeaders[i][0] == 0 and positionIndex == -1:
					positionIndex = i
				elif vertElemHeaders[i][0] == 1 and normalIndex == -1:
					normalIndex = i
				elif vertElemHeaders[i][0] == 2 and uvIndex == -1:
					uvIndex = i
				elif vertElemHeaders[i][0] == 3 and uv2Index == -1:
					uv2Index = i
				elif vertElemHeaders[i][0] == 4 and weightIndex == -1:
					weightIndex = i
				elif vertElemHeaders[i][0] == 5 and colorIndex == -1:
					colorIndex = i
			bs.seek(vertBuffOffs)

			vertexStartIndex = bs.tell()
			#print (vertElemHdrOffs, vertBuffOffs, uknVB, vertBuffSize, faceBuffOffs, vertElemCountA, vertElemCountB)
			vertexBuffer = bs.readBytes(vertBuffSize)
			submeshDataArr = []

			if LOD1Offs:

				bs.seek(LOD1Offs + 48 + 16) #unknown floats and bounding box

				if self.ver <= 1:  #sGameName != "RERT" and sGameName != "ReVerse" and sGameName != "RE8" and sGameName != "MHRise":
					bs.seek(bs.readUInt64())

				offsetInfo = []
				for i in range(countArray[0]):
					offsetInfo.append(bs.readUInt64())

				if runtime.bDebugMESH:
					print("Vertex Info Offsets")
					print(offsetInfo)

				nameOffsets = []
				names = []
				nameRemapTable = []

				bs.seek(nodesIndicesOffs)
				for i in range(numNodes):
					nameRemapTable.append(bs.readUShort())

				bs.seek(namesOffs)
				for i in range(numNodes):
					nameOffsets.append(bs.readUInt64())

				for i in range(numNodes):
					bs.seek(nameOffsets[i])
					names.append(bs.readString())

				if runtime.bDebugMESH:
					print("Names:")
					print(names)

				bs.seek(nodesIndicesOffs) #material indices
				matIndices =[]
				for i in range(matCount):
					matIndices.append(bs.readUShort())

				isSCN = (runtime.rapi.getInputName().lower().find(".scn") != -1)
				fullBonesOffs = len(self.fullBoneList)
				fullRemapOffs = len(self.fullRemapTable)
				fullBoneNames = [runtime.cleanBoneName(bone.name).lower() for bone in self.fullBoneList]
				boneRemapTable = []

				#bSkinningEnabled = bDoSkin = bonesOffs = 0

				#Skeleton
				if bonesOffs:
					bs.seek(bonesOffs)
					boneCount = bs.readUInt()
					boneMapCount = bs.readUInt()
					bAddNumbers = False
					if runtime.rapi.getInputName().find(".noesis") == -1 and (not runtime.dialogOptions.dialog or len(runtime.dialogOptions.dialog.loadItems) == 1) and (not runtime.dialogOptions.motDialog or not runtime.dialogOptions.motDialog.loadItems) :
						maxBones = 1024 if runtime.sGameName == "SF6" else 256
						if runtime.bAddBoneNumbers == 1 or runtime.noesis.optWasInvoked("-bonenumbers"):
							bAddNumbers = True
						elif runtime.bAddBoneNumbers == 2 and boneCount > maxBones and runtime.rapi.getInputName().lower().find(".scn") == -1:
							bAddNumbers = True
							print ("Model has more than", maxBones, "bones, auto-enabling bone numbers...")

					bs.seek(bonesOffs + 16)

					if boneCount:
						hierarchyOffs = bs.readUInt64()
						localOffs = bs.readUInt64()
						globalOffs = bs.readUInt64()
						inverseGlobalOffs = bs.readUInt64()

						if boneMapCount:
							for i in range(boneMapCount):
								boneRemapTable.append(bs.readShort() + fullBonesOffs)
						else:
							deferredWarning = "WARNING: Mesh has weights but no bone map"
							print(deferredWarning)
							boneRemapTable.append(0)

						if runtime.bDebugMESH:
							print("boneRemapTable:", boneRemapTable)

						boneParentInfo = []
						bs.seek(hierarchyOffs)
						for i in range(boneCount):
							boneParentInfo.append([bs.readShort(), bs.readShort(), bs.readShort(), bs.readShort(), bs.readShort(), bs.readShort(), bs.readShort(), bs.readShort()])

						bs.seek(localOffs)
						for i in range(boneCount):
							mat = runtime.NoeMat44.fromBytes(bs.readBytes(0x40)).toMat43()
							mat[3] *= runtime.fDefaultMeshScale
							boneName = names[countArray[1] + i]
							lowerBoneName = boneName.lower()
							#if i==0 and "root" in boneName.lower():
							#	mat[3][1] = 0 #neutralize Y offset for root bone

							if bAddNumbers:
								for j in range(len(boneRemapTable)):
									if boneParentInfo[i][0] == boneRemapTable[j]:
										boneName = "b" + "{:03d}".format(j+1) + ":" + boneName
										break
							parentIdx = boneParentInfo[i][1]
							if not isSCN and lowerBoneName in fullBoneNames:
								if i == 0: #relocate this mesh's root bone onto base skeleton version
								#if lowerBoneName == "cog" or lowerBoneName == "hip" or lowerBoneName == "c_hip":
									print("Relocating bone", boneName)
									newMat = self.fullBoneList[fullBoneNames.index(lowerBoneName)].getMatrix()
									self.pos =  (newMat[3] - mat[3]) / runtime.fDefaultMeshScale
									mat = newMat
								ctr = 1
								newBoneName = boneName + "." + runtime.rapi.getLocalFileName(self.path).split(".")[0]
								while newBoneName.lower() in fullBoneNames:
									newBoneName = boneName + "." + runtime.rapi.getLocalFileName(self.path).split(".")[0] + "-" + str(ctr)
									ctr += 1
								boneName = newBoneName

							#if (parentIdx == -1 or parentIdx == i) and (i > 0 or self.fullBoneList):
							#	print("changed parent", boneName)
							#	parentIndex = 0

							self.boneList.append(runtime.NoeBone(boneParentInfo[i][0], boneName, mat, None, parentIdx))

						self.boneList = runtime.rapi.multiplyBones(self.boneList)

						if runtime.bRotateBonesUpright:
							rot_mat = runtime.NoeMat43(((1, 0, 0), (0, 0, 1), (0, -1, 0), (0, 0, 0)))
							for bone in self.boneList:
								bone.setMatrix( (bone.getMatrix().inverse() * rot_mat).inverse()) 	#rotate upright in-place
						for bone in self.boneList:
							bone.index += fullBonesOffs
							if bone.parentIndex != -1:
								bone.parentIndex += fullBonesOffs
							if bone.parentIndex == -1 and fullBonesOffs > 0:
								bone.parentIndex = 0
					else:
						bDoSkin = False


				self.fullBoneList.extend(self.boneList)
				self.fullRemapTable.extend(boneRemapTable)

				#print(offsetInfo)
				for i in range(countArray[0]): # LODGroups

					meshVertexInfo = []
					#ctx = rapi.rpgCreateContext()
					bs.seek(offsetInfo[i])
					numOffsets = bs.readUByte()
					bs.seek(3,1)
					uknFloat = bs.readUInt()
					offsetSubOffsets = bs.readUInt64()
					bs.seek(offsetSubOffsets)

					meshOffsetInfo = []

					for j in range(numOffsets):
						meshOffsetInfo.append(bs.readUInt64())

					numVertsLOD = 0

					for j in range(numOffsets): # MainMeshes
						bs.seek(meshOffsetInfo[j])
						meshVertexInfo.append([bs.readUByte(), bs.readUByte(), bs.readUShort(), bs.readUInt(), bs.readUInt(), bs.readUInt()]) #GroupID, NumMesh, unused, unused, numVerts, numFaces
						self.groupIDs.append(meshVertexInfo[len(meshVertexInfo)-1][0])
						submeshData = []
						for k in range(meshVertexInfo[j][1]):
							if runtime.sGameName == "DRDR":
								submeshData.append([bs.readUShort(), bs.readUShort(), bs.readUInt(), bs.readUInt(), bs.readUInt(), bs.readUInt(), bs.readUInt64(), self.groupIDs[len(self.groupIDs)-1], bs.readUInt()])
								del submeshData[len(submeshData)-1][2] #this is something new, not sure
							elif self.ver >= 2:
								submeshData.append([bs.readUShort(), bs.readUShort(), bs.readUInt(), bs.readUInt(), bs.readUInt(), bs.readUInt64(), self.groupIDs[len(self.groupIDs)-1]])
							else:
								submeshData.append([bs.readUShort(), bs.readUShort(), bs.readUInt(), bs.readUInt(), bs.readUInt(), self.groupIDs[len(self.groupIDs)-1]]) #0 MaterialID, 1 faceCount, 2 indexBufferStartIndex, 3 vertexStartIndex

						submeshDataArr.append(submeshData)

						for k in range(meshVertexInfo[j][1]): # Submeshes


							materialID = submeshData[k][0]
							uknSubmeshID = submeshData[k][1]
							numFaces	 = submeshData[k][2]
							facesBefore  = submeshData[k][3]
							vertsBefore  = submeshData[k][4]
							uknSubmeshInt1 = submeshData[k][5]

							numVerts = submeshData[k+1][4] - vertsBefore if k+1 < len(submeshData) else meshVertexInfo[j][4] - (submeshData[k][4] - numVertsLOD)

							mainMeshNo = self.groupIDs[len(self.groupIDs)-1] if runtime.bReadGroupIds else j+1
							mainMeshStr = "_Group_" if runtime.bReadGroupIds else "_MainMesh_" if not runtime.bShorterNames else "_Main_"

							if runtime.bUseOldNamingScheme:
								meshName = "LODGroup_" + str(i+1) + mainMeshStr + str(mainMeshNo) + "_SubMesh_" + str(materialID+1)
							else:
								if runtime.bRenameMeshesToFilenames:
									meshName = os.path.splitext(runtime.rapi.getLocalFileName(runtime.sInputName))[0].replace(".mesh", "") + "_" + str(mainMeshNo) + "_" + str(k+1)
								elif runtime.bShorterNames:
									meshName = "LOD_" + str(i+1) + mainMeshStr + str(mainMeshNo) + "_Sub_" + str(k+1)
								else:
									meshName = "LODGroup_" + str(i+1) + mainMeshStr + str(mainMeshNo) + "_SubMesh_" + str(k+1)

							if (runtime.dialogOptions.dialog and len(runtime.dialogOptions.dialog.loadItems) > 1) or isSCN:
								meshName = runtime.rapi.getLocalFileName(self.path).split(".")[0].replace("_", "") + "_" + meshName.split("_", 1)[1]

							runtime.rapi.rpgSetName(meshName)
							if runtime.bRenameMeshesToFilenames:
								runtime.rapi.rpgSetMaterial(meshName)
							matName = ""; matHash = 0

							#Search for material
							if bLoadedMats:
								matHash = runtime.hash_wide(names[matIndices[materialID]])
								if i == 0:
									for m in range(len(self.matHashes)):
										if self.matHashes[m] == matHash:
											if self.matNames[m] != names[nameRemapTable[materialID]]:
												print ("WARNING: " + meshName + "\'s material name \"" + self.matNames[m] + "\" in MDF does not match its material hash! \n	True material name: \"" + names[nameRemapTable[materialID]] + "\"")
											matName = self.matNames[m]
											#rapi.rpgSetLightmap(matArray[k].replace(".dds".lower(), ""))
											break
							if matName == "":
								if matHash == 0:
									matHash = runtime.hash_wide(names[matIndices[materialID]])
								if bLoadedMats:
									print ("WARNING: " + meshName + "\'s material \"" + names[nameRemapTable[materialID]] + "\" hash " + str(matHash) + " not found in MDF!")
								self.matNames.append(names[nameRemapTable[materialID]])

								matName = self.matNames[len(self.matNames)-1]

							runtime.rapi.rpgSetMaterial(matName)
							runtime.rapi.rpgSetPosScaleBias((runtime.fDefaultMeshScale, runtime.fDefaultMeshScale, runtime.fDefaultMeshScale), (0, 0, 0))
							if runtime.bImportMaterialNames:
								#rapi.rpgSetName(meshName + "__" + matName + "__" + str(submeshData[k][len(submeshData[k])-1]))
								runtime.rapi.rpgSetName(meshName + '__' + matName)

							def legacyVertexStreams():
								if positionIndex != -1:
									if self.pos: #position offset
										posList = []
										for v in range(vertsBefore, vertsBefore+numVerts):
											idx = 12 * v
											transVec = runtime.NoeVec3(((struct.unpack_from('f', vertexBuffer, idx))[0], (struct.unpack_from('f', vertexBuffer, idx + 4))[0], (struct.unpack_from('f', vertexBuffer, idx + 8))[0])) * self.rot.transpose()
											posList.append(transVec[0] + self.pos[0])
											posList.append(transVec[1] + self.pos[1])
											posList.append(transVec[2] + self.pos[2])
										posBuff = struct.pack("<" + 'f'*len(posList), *posList)
										yield ("position", (posBuff, runtime.noesis.RPGEODATA_FLOAT, 12, 0,))
									else:
										yield ("position", (vertexBuffer, runtime.noesis.RPGEODATA_FLOAT, vertElemHeaders[positionIndex][1], vertElemHeaders[positionIndex][1] * vertsBefore,))

								if normalIndex != -1 and runtime.bNORMsEnabled:
									if runtime.bDebugNormals and not runtime.bColorsEnabled:
										yield ("color", (vertexBuffer, runtime.noesis.RPGEODATA_BYTE, vertElemHeaders[normalIndex][1], vertElemHeaders[normalIndex][2] + (vertElemHeaders[normalIndex][1] * vertsBefore), 4,))
									else:
										yield ("normal", (vertexBuffer, runtime.noesis.RPGEODATA_BYTE, vertElemHeaders[normalIndex][1], vertElemHeaders[normalIndex][2] + (vertElemHeaders[normalIndex][1] * vertsBefore),))
										if runtime.bTANGsEnabled:
											yield ("tangent", (vertexBuffer, runtime.noesis.RPGEODATA_BYTE, vertElemHeaders[normalIndex][1], 4 + vertElemHeaders[normalIndex][2] + (vertElemHeaders[normalIndex][1] * vertsBefore),))
								try:
									uv_stream = ("uv_scale_bias_fallback", ((runtime.NoeVec3((self.uvBias[names[nameRemapTable[materialID]]][0], 1, 1)), runtime.NoeVec3((self.uvBias[names[nameRemapTable[materialID]]][1], 0, 0))), lambda: (runtime.NoeVec3((1,1,1)), runtime.NoeVec3((0,0,0)))))
								except:
									uv_stream = ("uv_scale_bias", (runtime.NoeVec3((1,1,1)), runtime.NoeVec3((0,0,0)),))
								yield uv_stream
								if uvIndex != -1 and runtime.bUVsEnabled:
									yield ("uv1", (vertexBuffer, runtime.noesis.RPGEODATA_HALFFLOAT, vertElemHeaders[uvIndex][1], vertElemHeaders[uvIndex][2] + (vertElemHeaders[uvIndex][1] * vertsBefore),))
								if uv2Index != -1 and runtime.bUVsEnabled:
									yield ("uv2", (vertexBuffer, runtime.noesis.RPGEODATA_HALFFLOAT, vertElemHeaders[uv2Index][1], vertElemHeaders[uv2Index][2] + (vertElemHeaders[uv2Index][1] * vertsBefore),))

								if weightIndex != -1 and runtime.bSkinningEnabled and bDoSkin:
									#rapi.rpgSetBoneMap(boneRemapTable)
									yield ("bone_map", (self.fullRemapTable,))
									idxList = []
									start = vertexStartIndex + vertElemHeaders[weightIndex][2] + (vertElemHeaders[weightIndex][1] * vertsBefore)
									if runtime.sGameName == "SF6":
										for v in range(numVerts):
											bs.seek(start + vertElemHeaders[weightIndex][1] * v)
											for bID in range(3):
												idxList.append(bs.readBits(10)+fullRemapOffs)
											bs.readBits(2)
											for bID in range(3):
												idxList.append(bs.readBits(10)+fullRemapOffs)
											idxList.extend([0,0])
										idxBuff = struct.pack("<" + 'H'*len(idxList), *idxList)
										yield ("bone_indices", (idxBuff, runtime.noesis.RPGEODATA_USHORT, 16, 0, 8,))
									elif fullBonesOffs:
										for v in range(numVerts):
											bs.seek(start + vertElemHeaders[weightIndex][1] * v)
											for w in range(8):
												idxList.append(bs.readUByte()+fullRemapOffs)
										idxBuff = struct.pack("<" + 'H'*len(idxList), *idxList)
										yield ("bone_indices", (idxBuff, runtime.noesis.RPGEODATA_USHORT, 16, 0, 8,))
									else:
										yield ("bone_indices", (vertexBuffer, runtime.noesis.RPGEODATA_UBYTE, vertElemHeaders[weightIndex][1], vertElemHeaders[weightIndex][2] + (vertElemHeaders[weightIndex][1] * vertsBefore), 8,))
									yield ("bone_weights", (vertexBuffer, runtime.noesis.RPGEODATA_UBYTE, vertElemHeaders[weightIndex][1], vertElemHeaders[weightIndex][2] + (vertElemHeaders[weightIndex][1] * vertsBefore) + 8, 8,))

								if colorIndex != -1 and runtime.bColorsEnabled:
									offs = vertElemHeaders[colorIndex][2] + (vertElemHeaders[colorIndex][1] * vertsBefore)
									if offs + numVerts*4 < len(vertexBuffer):
										yield ("color", (vertexBuffer, runtime.noesis.RPGEODATA_UBYTE, vertElemHeaders[colorIndex][1], offs, 4,))
									else:
										print("WARNING:", meshName, "Color buffer would have been read out of bounds by provided indices", "\n	Buffer Size:", len(vertexBuffer), "\n	Required Size:", offs + numVerts*4)
							bindMeshVertexStreams(runtime.rapi, legacyVertexStreams())

							if numFaces > 0:
								faceSize = 4 if intFaces == 1 else 2
								bs.seek(faceBuffOffs + (facesBefore * faceSize))
								indexBuffer = bs.readBytes(numFaces * faceSize)
								primitive = {"indices": indexBuffer, "index_width": faceSize,
									"count": (meshVertexInfo[j][4] - vertsBefore) if runtime.bRenderAsPoints else numFaces,
									"points": runtime.bRenderAsPoints, "clear_binds": not runtime.bRenderAsPoints}
								submitMeshPrimitive(runtime.rapi, runtime.noesis, primitive)

						numVertsLOD += meshVertexInfo[j][4]

					'''try:
						mdl = rapi.rpgConstructModelAndSort()
						if mdl.meshes[0].name.find("_") == 4:
							print ("\nWARNING: Noesis split detected!\n   Export this mesh to FBX with the advanced option '-fbxmeshmerge'\n")
							rapi.rpgOptimize()
					except:
						mdl = NoeModel()
					mdl.setBones(self.boneList)
					mdl.setModelMaterials(NoeModelMaterials(self.texList, self.matList))
					mdlList.append(mdl)'''

					if not runtime.bImportAllLODs:
						break

				print ("\nMESH Material Count:", matCount)
				if bLoadedMats:
					print ("MDF Material Count:", len(self.matList))

			if occluderMeshOffs:
				#ctx = rapi.rpgCreateContext()
				#rapi.rpgSetOption(noesis.RPGOPT_TRIWINDBACKWARD, 1)
				bs.seek(occluderMeshOffs)
				occluderMeshCount = bs.readUInt()
				uknFloat = bs.readFloat()
				occluderMeshesOffset = bs.readUInt64()
				bs.seek(occluderMeshesOffset)
				occluderMeshes = []
				lastVertPos = vertBuffOffs
				lastFacesPos = faceBuffOffs
				for i in range(occluderMeshCount):
					dataOffset = bs.readUInt64()
					bs.seek(dataOffset)
					uknBytes = [bs.readByte(), bs.readByte(), bs.readByte(), bs.readByte(), bs.readByte(), bs.readByte(), bs.readByte(), bs.readByte()]
					vertexCount = bs.readUInt()
					indexCount = bs.readUInt()
					ukn = bs.readUInt()
					indexCount2 = bs.readUInt()
					occluderMeshes.append([uknBytes, vertexCount, indexCount])
					bs.seek(lastVertPos)
					vertexBuffer = bs.readBytes(12 * vertexCount)
					lastVertPos = bs.tell()
					bs.seek(lastFacesPos)
					indexBuffer = bs.readBytes(indexCount * 2)
					lastFacesPos = bs.tell()
					meshName = "OccluderMesh_" + str(i)
					if (runtime.dialogOptions.dialog and len(runtime.dialogOptions.dialog.loadItems) > 1) or isSCN:
						meshName = runtime.rapi.getLocalFileName(self.path).split(".")[0].replace("_", "") + "_" + meshName
					runtime.rapi.rpgSetName(meshName)
					runtime.rapi.rpgBindPositionBuffer(vertexBuffer, runtime.noesis.RPGEODATA_FLOAT, 12)
					runtime.rapi.rpgSetStripEnder(0x10000)
					try:
						runtime.rapi.rpgCommitTriangles(indexBuffer, runtime.noesis.RPGEODATA_USHORT, indexCount, runtime.noesis.RPGEO_TRIANGLE, 0x1)
						runtime.rapi.rpgClearBufferBinds()
						'''try:
							mdl = rapi.rpgConstructModelAndSort()
							if mdl.meshes[0].name.find("_") == 4:
								print ("\nWARNING: Noesis split detected!\n   Export this mesh to FBX with the advanced option '-fbxmeshmerge'\n")
								rapi.rpgOptimize()
						except:
							mdl = NoeModel()
						mdlList.append(mdl)'''
					except:
						print("Failed to read Occluder Mesh")

			print (deferredWarning)

			return 1 #mdlList

	return (
		feedPragmataMorphFrames,
		setOffsets,
		findGameName,
		meshFile,
	)
