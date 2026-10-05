"""Mesh writer implementation bound to one plugin runtime."""

import copy
import hashlib
import json
import math
import os
import struct
from re_engine_config import (
	PRAGMATA_CANDIDATE_002_POSITION_SNAP_EPSILON,
	PRAGMATA_CANDIDATE_002_SOURCE_SHA256,
	formats,
)
from re_engine_types import (
	MeshProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'BBskipBytes',
	'BoundingBoxSize',
	'LOD1OffsetLocation',
	'NoeBitStream',
	'NoeMat43',
	'NoeMesh',
	'NoeVec3',
	'NoeVec4',
	'NoeVertWeight',
	'Version',
	'_checkedRange',
	'_parsePragmataMeshData',
	'_meshFloat32',
	'_meshFloatToHalfBits',
	'_pragmataGeometryFromModel',
	'_meshPackSixU10',
	'_meshQuantizeColor',
	'_meshQuantizeSnorm',
	'_meshQuantizeWeights',
	'_meshTopologyHash',
	'_meshTransformPointRowVector',
	'_meshValidateVector',
	'_pragmataWriterPathIdentity',
	'_writePragmataExactTemplate',
	'bAddBoneNumbers',
	'bAlwaysRewrite',
	'bAlwaysWriteBones',
	'bCalculateBoundingBoxes',
	'bDoVFX',
	'bForceRootBoneToBone0',
	'bNewExportMenu',
	'bNormalizeWeights',
	'bReWrite',
	'bReadGroupIds',
	'bRigToCoreBones',
	'bRotateBonesUpright',
	'bSetNumModels',
	'bUseOldNamingScheme',
	'bWriteBones',
	'bonesOffsLocation',
	'bsHdrOffLocation',
	'bsIndicesOffLocation',
	'dialogOptions',
	'fDefaultMeshScale',
	'floatsHdrOffsLocation',
	'generateBoneMap',
	'getExportName',
	'isMeshVer3',
	'namesOffsLocation',
	'nodesIndicesOffsLocation',
	'noesis',
	'normalsRecalcOffsLocation',
	'numNodesLocation',
	'openOptionsDialog',
	'openOptionsDialogExportWindow',
	'parsePragmataHeader',
	'rapi',
	'readUIntAt',
	'recombineNoesisMeshes',
	'sGameName',
	'setOffsets',
	'sort_human',
	'vBuffHdrOffsLocation',
	'w1',
	'w2',
	'writePragmataCandidate002Exact',
)


def bind(runtime):
	def _writePragmataExactTemplate(source_data, source_path, geometry):
		"""Inject one standalone single-submesh geometry into fixed source slices."""
		if not isinstance(source_data, (bytes, bytearray)):
			raise MeshProfileError("structural-profile-mismatch:source-template-type")
		source = bytes(source_data)
		header = runtime.parsePragmataHeader(source, source_path)
		if header.get("streaming_entry_count") != 0:
			raise MeshProfileError("unsupported-streaming-writer-profile")
		parsed = runtime._parsePragmataMeshData(source, header)
		stats = parsed["stats"]
		if (stats["lod_count"] != 1 or stats["group_count"] != 1 or
				stats["submesh_count"] != 1 or len(parsed["material_names"]) != 1):
			raise MeshProfileError("unsupported-writer-cardinality")
		if set(parsed["vertex_elements"]) != set((0, 1, 2, 4, 5)):
			raise MeshProfileError("unsupported-writer-vertex-elements")
		if not isinstance(geometry, dict):
			raise MeshProfileError("structural-profile-mismatch:geometry-type")

		vertex_count = stats["vertex_count"]
		index_count = stats["index_count"]
		count_fields = (
			("positions", "vertex-count"),
			("normal_tangents", "normal-tangent-count"),
			("uvs", "uv-count"),
			("bone_slots", "bone-slot-count"),
			("weights", "weight-count"),
			("colors", "color-count"),
		)
		for field, token in count_fields:
			if not isinstance(geometry.get(field), (list, tuple)) or len(geometry[field]) != vertex_count:
				raise MeshProfileError("structural-profile-mismatch:" + token)
		indices = geometry.get("indices")
		if not isinstance(indices, (list, tuple)) or len(indices) != index_count:
			raise MeshProfileError("structural-profile-mismatch:index-count")
		if geometry.get("bone_names") != [bone["name"] for bone in parsed["bones"]]:
			raise MeshProfileError("structural-profile-mismatch:bone-identity")
		if geometry.get("material_name") != parsed["material_names"][0]:
			raise MeshProfileError("structural-profile-mismatch:material-identity")

		positions = [
			runtime._meshValidateVector(value, 3, "position")
			for value in geometry["positions"]
		]
		normal_tangents = [
			runtime._meshValidateVector(value, 8, "normal-tangent")
			for value in geometry["normal_tangents"]
		]
		uvs = [
			runtime._meshValidateVector(value, 2, "uv")
			for value in geometry["uvs"]
		]
		colors = [
			runtime._meshValidateVector(value, 4, "color")
			for value in geometry["colors"]
		]
		bone_map_count = len(parsed["bone_map"])
		packed_slots = []
		packed_weights = []
		for vertex_index in range(vertex_count):
			slots = geometry["bone_slots"][vertex_index]
			weights = geometry["weights"][vertex_index]
			if not isinstance(slots, (list, tuple)) or not isinstance(weights, (list, tuple)):
				raise MeshProfileError("structural-profile-mismatch:weight-count")
			if len(slots) != len(weights):
				raise MeshProfileError("structural-profile-mismatch:weight-count")
			packed_slots.append(runtime._meshPackSixU10(tuple(slots), bone_map_count))
			packed_weights.append(runtime._meshQuantizeWeights(tuple(weights)))

		validated_indices = []
		for index in indices:
			if isinstance(index, bool) or not isinstance(index, int):
				raise MeshProfileError("structural-profile-mismatch:index-type")
			if index < 0 or index >= vertex_count or index > 0xFFFF:
				raise MeshProfileError("index-out-of-range")
			validated_indices.append(index)

		mesh_buffer = header["mesh_buffer"]
		element_table = mesh_buffer["vertex_element_offset"]
		raw_elements = {}
		for element_index in range(mesh_buffer["element_count"]):
			element_type, stride, offset = struct.unpack_from(
				"<HHI", source, element_table + element_index * 8)
			raw_elements[element_type] = {"stride": stride, "offset": offset}
		output = bytearray(source)
		vertex_base = mesh_buffer["vertex_buffer_offset"]

		for vertex_index, position in enumerate(positions):
			struct.pack_into("<3f", output,
				vertex_base + raw_elements[0]["offset"] + vertex_index * 12,
				*position)
		for vertex_index, values in enumerate(normal_tangents):
			struct.pack_into("<8b", output,
				vertex_base + raw_elements[1]["offset"] + vertex_index * 8,
				*[runtime._meshQuantizeSnorm(value) for value in values])
		for vertex_index, uv in enumerate(uvs):
			struct.pack_into("<2H", output,
				vertex_base + raw_elements[2]["offset"] + vertex_index * 4,
				runtime._meshFloatToHalfBits(uv[0]), runtime._meshFloatToHalfBits(uv[1]))
		for vertex_index in range(vertex_count):
			struct.pack_into("<Q8B", output,
				vertex_base + raw_elements[4]["offset"] + vertex_index * 16,
				packed_slots[vertex_index], *packed_weights[vertex_index])
		for vertex_index, color in enumerate(colors):
			struct.pack_into("<4B", output,
				vertex_base + raw_elements[5]["offset"] + vertex_index * 4,
				*[runtime._meshQuantizeColor(value) for value in color])

		submesh = parsed["submeshes"][0]
		face_start = mesh_buffer["face_buffer_offset"] + submesh["index_start"] * 2
		runtime._checkedRange(output, face_start, index_count * 2, "writer-index-buffer")
		struct.pack_into("<" + "H" * index_count, output, face_start, *validated_indices)

		skeleton_offset = header["skeleton_offset"]
		_inverse_global_offset = struct.unpack_from("<Q", source, skeleton_offset + 40)[0]
		runtime._checkedRange(source, _inverse_global_offset, len(parsed["bones"]) * 64,
			"bone-inverse-global-matrices")
		aabb_count, aabb_entries = struct.unpack_from("<QQ", source, header["aabb_offset"])
		if aabb_count != bone_map_count:
			raise MeshProfileError("structural-profile-mismatch:aabb-count")
		runtime._checkedRange(source, aabb_entries, aabb_count * 32, "aabb-entries")
		local_points = [[] for _index in range(bone_map_count)]
		for vertex_index, position in enumerate(positions):
			for slot, weight in zip(geometry["bone_slots"][vertex_index],
					geometry["weights"][vertex_index]):
				if weight <= 0.0:
					continue
				bone_index = parsed["bone_map"][slot]
				matrix = struct.unpack_from(
					"<16f", source, _inverse_global_offset + bone_index * 64)
				local_points[slot].append(runtime._meshTransformPointRowVector(position, matrix))
		for slot, points in enumerate(local_points):
			if not points:
				raise MeshProfileError("structural-profile-mismatch:unweighted-aabb-slot")
			existing = struct.unpack_from("<8f", source, aabb_entries + slot * 32)
			if any(not math.isfinite(value) for value in existing):
				raise MeshProfileError("structural-profile-mismatch:non-finite-aabb")
			mins = [min(existing[axis], min(point[axis] for point in points))
				for axis in range(3)]
			maxs = [max(existing[4 + axis], max(point[axis] for point in points))
				for axis in range(3)]
			struct.pack_into("<8f", output, aabb_entries + slot * 32,
				mins[0], mins[1], mins[2], 1.0,
				maxs[0], maxs[1], maxs[2], 1.0)

		result = bytes(output)
		reparsed = runtime._parsePragmataMeshData(result, runtime.parsePragmataHeader(result, source_path))
		if reparsed["stats"]["vertex_count"] != vertex_count:
			raise MeshProfileError("writer-postcondition-vertex-count")
		if reparsed["stats"]["index_count"] != index_count:
			raise MeshProfileError("writer-postcondition-index-count")
		written_positions = [tuple(runtime._meshFloat32(value) for value in position)
			for position in positions]
		expected_topology = runtime._meshTopologyHash(written_positions, validated_indices)
		if reparsed["stats"]["topology_hash"] != expected_topology:
			print("RE_MESH_WRITER_POSTCONDITION_JSON:" + json.dumps({
				"expected_topology_hash": expected_topology,
				"reparsed_topology_hash": reparsed["stats"]["topology_hash"],
			}, sort_keys=True, separators=(",", ":")))
			raise MeshProfileError("writer-postcondition-topology")
		return result

	def writePragmataCandidate002Exact(source_data, source_path, geometry):
		if hashlib.sha256(bytes(source_data)).hexdigest() != PRAGMATA_CANDIDATE_002_SOURCE_SHA256:
			raise MeshProfileError("source-template-sha256-mismatch")
		result = runtime._writePragmataExactTemplate(source_data, source_path, geometry)
		parsed = runtime._parsePragmataMeshData(result, runtime.parsePragmataHeader(result, source_path))
		stats = parsed["stats"]
		if (len(result) != 319552 or stats["lod_count"] != 1 or
				stats["group_count"] != 1 or stats["submesh_count"] != 1 or
				stats["vertex_count"] != 4843 or stats["index_count"] != 25926 or
				stats["bone_count"] != 229 or len(parsed["material_names"]) != 1):
			raise MeshProfileError("unsupported-candidate-002-writer-profile")
		return result

	def _pragmataGeometryFromModel(mdl, parsed):
		meshes = getattr(mdl, "meshes", None)
		if not isinstance(meshes, (list, tuple)) or len(meshes) != 1:
			raise MeshProfileError("structural-profile-mismatch:mesh-count")
		mesh = meshes[0]
		expected_bone_names = [bone["name"] for bone in parsed["bones"]]
		model_bones = getattr(mdl, "bones", None)
		if (not isinstance(model_bones, (list, tuple)) or
				[getattr(bone, "name", None) for bone in model_bones] != expected_bone_names):
			raise MeshProfileError("structural-profile-mismatch:bone-identity")
		material_name = getattr(mesh, "matName", None)
		if not material_name:
			mesh_name = getattr(mesh, "name", "")
			material_name = mesh_name.split("__", 1)[1] if "__" in mesh_name else None
		if material_name != parsed["material_names"][0]:
			raise MeshProfileError("structural-profile-mismatch:material-identity")

		positions = getattr(mesh, "positions", None)
		tangents = getattr(mesh, "tangents", None)
		uvs = getattr(mesh, "uvs", None)
		colors = getattr(mesh, "colors", None)
		weights = getattr(mesh, "weights", None)
		indices = getattr(mesh, "indices", None)
		vertex_count = parsed["stats"]["vertex_count"]
		for values, token in (
				(positions, "vertex-count"), (tangents, "normal-tangent-count"),
				(uvs, "uv-count"), (colors, "color-count"),
				(weights, "weight-count")):
			if not isinstance(values, (list, tuple)) or len(values) != vertex_count:
				raise MeshProfileError("structural-profile-mismatch:" + token)
		if not isinstance(indices, (list, tuple)) or len(indices) != parsed["stats"]["index_count"]:
			raise MeshProfileError("structural-profile-mismatch:index-count")

		file_positions = []
		position_snap_count = 0
		position_snap_max_error = 0.0
		for vertex_index, position in enumerate(positions):
			value = runtime._meshValidateVector(position, 3, "position")
			converted = tuple(component / runtime.fDefaultMeshScale for component in value)
			source_position = parsed["positions"][vertex_index]
			error = max(abs(converted[axis] - source_position[axis]) for axis in range(3))
			if error <= PRAGMATA_CANDIDATE_002_POSITION_SNAP_EPSILON:
				converted = tuple(source_position)
				position_snap_count += 1
				position_snap_max_error = max(position_snap_max_error, error)
			file_positions.append(converted)
		normal_tangents = []
		for tangent in tangents:
			try:
				normal = runtime._meshValidateVector(tangent[0], 3, "normal-tangent")
				basis = runtime._meshValidateVector(tangent[1], 3, "normal-tangent")
				bitangent = runtime._meshValidateVector(tangent[2], 3, "normal-tangent")
			except (IndexError, TypeError):
				raise MeshProfileError("structural-profile-mismatch:normal-tangent")
			handedness = -1.0 if sum(
				component * other for component, other in zip((
					normal[1] * basis[2] - normal[2] * basis[1],
					normal[2] * basis[0] - normal[0] * basis[2],
					normal[0] * basis[1] - normal[1] * basis[0],
				), bitangent)) >= 0.0 else 1.0
			normal_tangents.append(normal + (0.0,) + bitangent + (handedness,))

		bone_to_slot = dict((bone_index, slot)
			for slot, bone_index in enumerate(parsed["bone_map"]))
		bone_slots = []
		weight_values = []
		for weight in weights:
			model_indices = getattr(weight, "indices", None)
			model_weights = getattr(weight, "weights", None)
			if (not isinstance(model_indices, (list, tuple)) or
					not isinstance(model_weights, (list, tuple)) or
					len(model_indices) != len(model_weights)):
				raise MeshProfileError("structural-profile-mismatch:weight-count")
			active_slots = []
			active_weights = []
			for bone_index, value in zip(model_indices, model_weights):
				if not math.isfinite(value):
					raise MeshProfileError("structural-profile-mismatch:weight-sum")
				if value <= 0.0:
					continue
				if isinstance(bone_index, bool) or not isinstance(bone_index, int):
					raise MeshProfileError("structural-profile-mismatch:bone-slot-type")
				if bone_index not in bone_to_slot:
					raise MeshProfileError("bone-index-out-of-range")
				active_slots.append(bone_to_slot[bone_index])
				active_weights.append(float(value))
			bone_slots.append(tuple(active_slots))
			weight_values.append(tuple(active_weights))

		return {
			"positions": file_positions,
			"normal_tangents": normal_tangents,
			"uvs": [(value[0], value[1]) for value in uvs],
			"bone_slots": bone_slots,
			"weights": weight_values,
			"colors": [(value[0], value[1], value[2], value[3]) for value in colors],
			"indices": list(indices),
			"bone_names": expected_bone_names,
			"material_name": material_name,
			"position_snap_count": position_snap_count,
			"position_snap_max_error": position_snap_max_error,
		}

	def _pragmataWriterPathIdentity(path):
		if not path:
			raise MeshProfileError("missing-writer-path")
		return os.path.normcase(os.path.abspath(os.path.normpath(path)))

	def pragmataMeshWriteModel(mdl, bs):
		try:
			if runtime.noesis.optWasInvoked("-meshfile"):
				source_path = runtime.noesis.optGetArg("-meshfile")
			elif runtime.noesis.optWasInvoked("-noprompt"):
				raise MeshProfileError("missing-source-template")
			else:
				source_path = runtime.noesis.userPrompt(
					runtime.noesis.NOEUSERVAL_FILEPATH, "PRAGMATA Source Template",
					"Choose the frozen candidate 002 .mesh.251121828 source template",
					runtime.rapi.getInputName(), None)
				if not source_path:
					raise MeshProfileError("missing-source-template")
			output_path = runtime.rapi.getOutputName()
			if runtime._pragmataWriterPathIdentity(source_path) == runtime._pragmataWriterPathIdentity(output_path):
				raise MeshProfileError("source-output-path-collision")
			try:
				source_data = bytes(runtime.rapi.loadIntoByteArray(source_path))
			except Exception:
				raise MeshProfileError("source-template-read-failed")
			header = runtime.parsePragmataHeader(source_data, source_path)
			parsed = runtime._parsePragmataMeshData(source_data, header)
			geometry = runtime._pragmataGeometryFromModel(mdl, parsed)
			print("RE_MESH_WRITER_INPUT_JSON:" + json.dumps({
				"vertex_count": len(geometry["positions"]),
				"index_count": len(geometry["indices"]),
				"position_snap_count": geometry["position_snap_count"],
				"position_snap_max_error": geometry["position_snap_max_error"],
				"uv_min": [min(value[axis] for value in geometry["uvs"])
					for axis in range(2)],
				"uv_max": [max(value[axis] for value in geometry["uvs"])
					for axis in range(2)],
			}, sort_keys=True, separators=(",", ":")))
			result = runtime.writePragmataCandidate002Exact(source_data, source_path, geometry)
			bs.writeBytes(result)
			print("RE_MESH_WRITER_STATS_JSON:" + json.dumps({
				"schema": "pragmata-mesh-writer/v1",
				"source_sha256": hashlib.sha256(source_data).hexdigest(),
				"output_sha256": hashlib.sha256(result).hexdigest(),
				"output_size": len(result),
			}, sort_keys=True, separators=(",", ":")))
			return 1
		except MeshProfileError as error:
			print("RE_MESH_WRITER_ERROR:" + str(error))
			return 0

	def getExportName(fileName, exportType=".mesh"):
		# Shared state is owned by runtime. #, doLOD
		runtime.bReWrite = False; runtime.bWriteBones = False; runtime.w1 = 127; runtime.w2 = -128
		sourceList = []
		if fileName == None:
			meshExt = os.path.splitext(runtime.rapi.getOutputName())[-1]
			newMeshName = runtime.rapi.getExtensionlessName(runtime.rapi.getOutputName().replace("out.", ".")).replace(".mesh", "").replace(meshExt, "") + ".mesh" + meshExt
			ogFileName = runtime.rapi.getLocalFileName(newMeshName)
			similarityCounter = 0
			for item in os.listdir(os.path.dirname(runtime.rapi.getOutputName())):
				if os.path.splitext(item)[1] == meshExt:
					sourceList.append(os.path.join(os.path.dirname(newMeshName), item))
					sameCharCntr = 0
					for c, char in enumerate(runtime.rapi.getExtensionlessName(item)): 
						if c < len(ogFileName) and char == ogFileName[c]:
							sameCharCntr += 1
					if sameCharCntr > similarityCounter:
						similarityCounter = sameCharCntr
						newMeshName = os.path.join(os.path.dirname(newMeshName), item)
		else:
			newMeshName = fileName
		
		if runtime.bNewExportMenu:
			runtime.openOptionsDialog = runtime.openOptionsDialogExportWindow(1000, 195, {"filepath":newMeshName, "exportType":exportType}) #int(len(newMeshName)*7.5)
			runtime.openOptionsDialog.createMeshWindow()
			newMeshName = runtime.openOptionsDialog.filepath or newMeshName
			if runtime.openOptionsDialog.doCancel:
				newMeshName = None
			else: 
				if runtime.openOptionsDialog.doRewrite:
					newMeshName = newMeshName + " -rewrite"
				if runtime.openOptionsDialog.doWriteBones:
					newMeshName = newMeshName + " -bones"
				if runtime.openOptionsDialog.doVFX:
					newMeshName = newMeshName + " -vfx"
		else:
			newMeshName = runtime.noesis.userPrompt(runtime.noesis.NOEUSERVAL_FILEPATH, "Inject " + exportType.upper(), "Choose a " + exportType.upper() + " file to inject", newMeshName, None)

		if newMeshName == None:
			print("Aborting...")
			return
			
		if runtime.noesis.optWasInvoked("-flip") or newMeshName.find(" -flip") != -1:
			newMeshName = newMeshName.replace(" -flip", "")
			print ("Exporting with OpenGL handedness")
			runtime.w1 = -128; runtime.w2 = 127
			
		if runtime.noesis.optWasInvoked("-vfx") or newMeshName.find(" -vfx") != -1:
			newMeshName = newMeshName.replace(" -vfx", "")
			runtime.bDoVFX = True
			print ("Exporting VFX mesh")
		
		if runtime.noesis.optWasInvoked("-bones") or newMeshName.find(" -bones") != -1:
			newMeshName = newMeshName.replace(" -bones", "")
			print ("Exporting with new skeleton...")
			runtime.bWriteBones = True
			
		if newMeshName.find(" -rewrite") != -1:
			newMeshName = newMeshName.replace(" -rewrite", "")
			print ("Exporting with new skeleton, Group and Submesh order...")
			runtime.bReWrite = True
			runtime.bWriteBones = True
			
		if newMeshName.find(" -match") != -1:
			newMeshName = newMeshName.replace(" -match", "")
			print ("Unmatched bones will be rigged to the hips and spine")
			runtime.bRigToCoreBones = True
			
		return newMeshName

	def meshWriteModel(mdl, bs):

		# Shared state is owned by runtime. #doLOD
		
		runtime.bWriteBones = runtime.noesis.optWasInvoked("-bones")
		runtime.bReWrite = runtime.noesis.optWasInvoked("-rewrite")
		runtime.bNewExportMenu = runtime.noesis.optWasInvoked("-adv") or runtime.bNewExportMenu
		
		runtime.w1 = 127; runtime.w2 = -128
		if runtime.noesis.optWasInvoked("-flip"): 
			runtime.w1 = -128; runtime.w2 = 127
			
		if runtime.bAlwaysRewrite or runtime.noesis.optWasInvoked("-b"):
			runtime.bReWrite = True
		if runtime.bAlwaysWriteBones:
			runtime.bWriteBones = True
		
		meshesToExport = mdl.meshes
		bDoUV2 = False
		bDoSkin = False
		bDoColors = False
		bAddNumbers = False
		isDD2Mesh = False
		f = None
		newMeshName = ""
		runtime.bDoVFX = runtime.noesis.optWasInvoked("-vfx") or (runtime.openOptionsDialog and runtime.openOptionsDialog.doVFX)
		numLODs = 1
		diff = 0	
		meshVertexInfo = []
		vertElemCountB = 5	
		newScale = (1 / runtime.fDefaultMeshScale)
		submeshes = []
		
		
		def padToNextLine(bitstream):
			while bitstream.tell() % 16 != 0:
				bitstream.writeByte(0)
				
		def dot(v1, v2):
			return sum(x*y for x,y in zip(v1,v2))	
				
		def cross(a, b):
			c = [a[1]*b[2] - a[2]*b[1],
				 a[2]*b[0] - a[0]*b[2],
				 a[0]*b[1] - a[1]*b[0]]
			return c
			
		def checkReWriteMeshes():
			# Shared state is owned by runtime.
			nonlocal submeshes, meshesToExport, bDoSkin
			for i in objToExport:
				obj = meshesToExport[i]
				sName = obj.name.lower().split('_')
				if len(sName) < 8:
					print("WARNING! Cannot rewrite mesh, an object is missing its material name\nObject Name:", obj.name, "\nMeshes for ReWrite should have 7 underscores in their names.\nExporting with new skeleton...")
					runtime.bReWrite = False
					submeshes = []
					break
				else:
					submeshes.append(copy.copy(obj))
			if runtime.bReWrite and not bDoSkin: #if still true
				submeshBoneCount = 0
				for bone in mdl.bones:
					for mesh in submeshes:
						if bone.name == mesh.name: #fbx is stupid and adds submeshes as bones to boneless meshes
							submeshBoneCount = submeshBoneCount + 1
							break
				if len(mdl.bones) > 0 and len(mdl.bones) - submeshBoneCount > 0:
					bDoSkin = True
						
		#Prompt for source mesh to export over / export options:
		def showOptionsDialog():
			# Shared state is owned by runtime.
			nonlocal bDoSkin, submeshes, f, newMeshName
			fileName = None
			if runtime.noesis.optWasInvoked("-meshfile"):
				newMeshName = runtime.noesis.optGetArg("-meshfile")
				if runtime.noesis.optWasInvoked("-adv"):
					newMeshName = runtime.getExportName(newMeshName)
				if newMeshName:
					newMesh = runtime.rapi.loadIntoByteArray(newMeshName)
					f = runtime.NoeBitStream(newMesh)
					return newMeshName
			else:
				newMeshName = runtime.getExportName(fileName)
			if newMeshName == None:
				return 0
			while not runtime.bReWrite and not runtime.rapi.checkFileExists(newMeshName):
				print ("File not found!")
				newMeshName = runtime.getExportName(fileName)	
				fileName = newMeshName
				if newMeshName == None:
					return 0
			if not runtime.bReWrite:		
				newMesh = runtime.rapi.loadIntoByteArray(newMeshName)
				f = runtime.NoeBitStream(newMesh)
			else:
				checkReWriteMeshes()
				if not runtime.bReWrite:
					showOptionsDialog()
			
		print ("		----" + runtime.Version + " by alphaZomega----\nOpen fmt_RE_MESH.py in your Noesis plugins folder to change global exporter options.\nExport Options:\n Input these options in the `Advanced Options` field to use them, or use in CLI mode\n -flip  =  OpenGL / flipped handedness (fixes seams and inverted lighting on some models)\n -bones = save new skeleton from Noesis to the MESH file\n -bonenumbers = Export with bone numbers, to save a new bone map\n -meshfile [filename]= Input the location of a [filename] to inject that file\n -noprompt = Do not show any prompts\n -rewrite = save new MainMesh and SubMesh order (also saves bones)\n -vfx = Export as a VFX mesh\n -b = Batch conversion mode\n -adv = Show Advanced Options dialog window\n") #\n -lod = export with additional LODGroups") # 
		
		ext = os.path.splitext(runtime.rapi.getOutputName())[1]
		RERTBytes = 0
		
		runtime.sGameName = "RE2" 
		if ext.find(".1808282334") != -1:
			runtime.sGameName = "DMC5"
		elif ext.find(".1902042334") != -1:
			runtime.sGameName = "RE3"
		elif ext.find(".2102020001") != -1:
			runtime.sGameName = "ReVerse"
		elif ext.find(".2101050001") != -1:
			runtime.sGameName = "RE8"
		elif (ext.find(".2109108288") != -1) or (ext.find(".220128762") != -1): #RE2/RE3RT, and RE7RT
			runtime.sGameName = "RERT"
			RERTBytes = 8
		elif ext.find(".2109148288") != -1: #MHRise Sunbreak
			realGameName = "MHRise Sunbreak"
			runtime.sGameName = "RERT"
			RERTBytes = 8
		elif ext.find(".2008058288") != -1: #Vanilla MHRise
			runtime.sGameName = "MHRise"
		elif ext.find(".230110883") != -1 or ext.find(".220721329") != -1: 
			runtime.sGameName = "SF6"
			runtime.isMeshVer3 = True
		elif ext.find(".220907984") != -1:
			runtime.sGameName = "ExoPrimal"
			runtime.isMeshVer3 = True
		elif ext.find(".221108797") != -1:
			runtime.sGameName = "RE4"
			runtime.isMeshVer3 = True
		elif ext.find(".230612127") != -1:
			runtime.sGameName = "AJ_AAT"
			runtime.isMeshVer3 = True
		elif ext.find(".231011879") != -1:
			runtime.sGameName = "DD2"
			runtime.isMeshVer3 = True
		elif ext.find(".240424828") != -1:
			runtime.sGameName = "DRDR"
			runtime.isMeshVer3 = True
			
		runtime.setOffsets(formats[runtime.sGameName]["meshVersion"])
		
		print ("\n				  ", realGameName if 'realGameName' in locals() else runtime.sGameName, "\n")
		
		#merge Noesis-split meshes back together:
		if meshesToExport[0].name.find("_") == 4 and meshesToExport[0].name != meshesToExport[0].sourceName:
			meshesToExport = runtime.recombineNoesisMeshes(mdl)
		
		#Remove Blender numbers from all names
		for mesh in mdl.meshes:
			if mesh.name.find('.') != -1:
				print ("Renaming Mesh " + str(mesh.name) + " to " + str(mesh.name.split('.')[0]))
				mesh.name = mesh.name.split('.')[0]
			if len(mesh.lmUVs) == 0: #make sure UV2 exists
				mesh.lmUVs = mesh.uvs
		
		#sort by name (if FBX reorganized):
		meshesToExport = runtime.sort_human(meshesToExport) 
		
		#Validate meshes are named correctly
		objToExport = []
		for i, mesh in enumerate(meshesToExport):
			ss = mesh.name.lower().split('_')			
			if len(ss) >= 6:
				if ss[1].isnumeric() and ss[3].isnumeric() and ss[5].isnumeric():
					objToExport.append(i)
					
		if runtime.bReWrite:
			if runtime.noesis.optWasInvoked("-adv"): # and noesis.optWasInvoked("-noprompt"):
				newMeshName = runtime.getExportName(runtime.rapi.getOutputName() or None)
			checkReWriteMeshes()
		else:
			showOptionsDialog()

		if f:
			magic = f.readUInt()
			if magic != 1213416781:
				runtime.noesis.messagePrompt("Not a MESH file.\nAborting...")
				return 0		
			bonesOffs = runtime.readUIntAt(f, runtime.bonesOffsLocation)
			if bonesOffs > 0:
				bDoSkin = True
		
		if not runtime.bReWrite:
			if newMeshName != None:
				print("Source Mesh:\n", newMeshName)
			else:
				return 0
				
		if bDoSkin:
			print ("  Rigged mesh detected, exporting with skin weights...")
		else:
			print("  No rigging detected")
			
		extension = os.path.splitext(runtime.rapi.getInputName())[1]
		vertElemCount = 3 
		
		if runtime.sGameName == "AJ_AAT" or runtime.sGameName == "DD2" or runtime.sGameName == "DRDR":
			#namesOffsLocation = 136 if bDoSkin else 144
			isDD2Mesh = True

		#check if exporting bones and create skin bone map if so:
		if bDoSkin:
			vertElemCount += 1
			bonesList = []
			newSkinBoneMap = []
			maxBones = 1024 if runtime.sGameName == "SF6" else 256
			
			if (runtime.bReWrite or runtime.bWriteBones) and runtime.dialogOptions.doCreateBoneMap:
				runtime.generateBoneMap(mdl)
			
			if runtime.bAddBoneNumbers == 1 or runtime.noesis.optWasInvoked("-bonenumbers"):
				bAddNumbers = True
			elif runtime.bAddBoneNumbers == 2:
				if len(mdl.bones) > maxBones:
					print ("Model has more than", maxBones, "bones, auto-enabling bone numbers...")
					bAddNumbers = True
				else:
					for bone in mdl.bones:
						if bone.name.find(':') != -1:
							bAddNumbers = True
							print ("  ", bone.name, "has a \':\' (colon) in its name, auto-enabling bone numbers...")
							break
			
			if (runtime.bReWrite or runtime.bWriteBones) and runtime.bForceRootBoneToBone0 and mdl.bones[0] != None and mdl.bones[0].name.lower() != "root" and mdl.bones[len(mdl.bones)-1].name.lower() == "root":
				print("WARNING: root is not bone[0], reorganizing heirarchy...")
				sortedBones = list(mdl.bones)
				rootIdx = len(sortedBones)-1
				sortedBones.remove(sortedBones[rootIdx])
				sortedBones.insert(0, mdl.bones[rootIdx])
				for i, bone in enumerate(sortedBones):
					bone.index = i
					if bone.parentIndex == rootIdx:
						bone.parentIndex = 0
					elif bone.parentIndex != -1:
						bone.parentIndex = bone.parentIndex + 1
				mdl.bones = tuple(sortedBones)
				for mesh in mdl.meshes:
					for weightsList in mesh.weights:
						indicesList = list(weightsList.indices)
						for i, idx in enumerate(indicesList):
							if idx == rootIdx:
								idx = 0
							else:
								indicesList[i] = idx + 1
						weightsList.indices = tuple(indicesList)
			
			for i, bone in enumerate(mdl.bones):
				if bone.name.find('_') == 8 and bone.name.startswith("bone"):
					print ("Renaming Bone " + str(bone.name) + " to " + bone.name[9:len(bone.name)] )
					bone.name = bone.name[9:len(bone.name)] #remove Noesis duplicate numbers
				if bone.name.find('.') != -1:
					print ("Renaming Bone " + str(bone.name) + " to " + str(bone.name.split('.')[0]))
					bone.name = bone.name.split('.')[0] #remove blender numbers
				
				if bone.name.find(':') != -1:
					bonesList.append(bone.name.split(':')[1]) #remove bone numbers
					if len(newSkinBoneMap) < maxBones:
						newSkinBoneMap.append(i)
				else:
					bonesList.append(bone.name)
					if not bAddNumbers and len(newSkinBoneMap) < maxBones:
						newSkinBoneMap.append(i)
						
			if bAddNumbers and len(newSkinBoneMap) == 0: #in case bone numbers is on but the skeleton has no bone numbers:
				print ("WARNING: No bone numbers detected, only the first", maxBones, "bones will be rigged")
				bAddNumbers = False
				for i, bone in enumerate(mdl.bones):
					if len(newSkinBoneMap) < maxBones:
						newSkinBoneMap.append(i)
		
		newBBOffs = 0

		#OLD WAY (reading source file, no rewrite):
		#====================================================================
		if not runtime.bReWrite:
			
			#header
			f.seek(runtime.numNodesLocation)
			numNodes = f.readUInt()
			f.seek(runtime.LOD1OffsetLocation)
			LOD1Offs = f.readUInt64()
			f.seek(runtime.vBuffHdrOffsLocation)  
			vBuffHdrOffs = f.readUInt64() 
			f.seek(runtime.bonesOffsLocation)   
			bonesOffs = f.readUInt64()  
			f.seek(runtime.nodesIndicesOffsLocation)  
			nodesIndicesOffs = f.readUInt64()  
			boneIndicesOffs = f.readUInt64()  
			f.seek(runtime.namesOffsLocation)
			namesOffs = f.readUInt64() 
			f.seek(runtime.floatsHdrOffsLocation)
			floatsHdrOffs = f.readUInt64() 
			
			if isDD2Mesh:
				f.seek(144)
				DD2HashesOffset = f.readUInt64()
			
			newBBOffs = floatsHdrOffs
			f.seek(LOD1Offs)
			countArray = f.read("16B")
			numMats = countArray[1]
				
			#vertex buffer header
			f.seek(vBuffHdrOffs)
			vertElemHdrOffs = f.readUInt64()
			vertBuffOffs = f.readUInt64()
			
			if runtime.isMeshVer3:
				f.seek(8,1)
				vertBuffSize = f.readUInt()
				face_buffOffsSF6 = f.readUInt()
				faceBuffOffs = face_buffOffsSF6 + vertBuffOffs
				vertElemCountA = f.readUShort()
				vertElemCountB = f.readUShort()
			else:
				faceBuffOffs = f.readUInt64()
				if runtime.sGameName == "RERT":
					uknIntA = f.readUInt()
					uknIntB = f.readUInt()
				vertBuffSize = f.readUInt()
				faceBuffSize = f.readUInt()
				vertElemCountA = f.readUShort()
				vertElemCountB = f.readUShort()
				faceBufferSize2nd = f.readUInt64()
				blendshapesOffset = f.readUInt()
			
			f.seek(vertElemHdrOffs)
			vertElemHeaders = []
			for i in range(vertElemCountB):
				vertElemHeaders.append([f.readUShort(), f.readUShort(), f.readUInt()])
			
			for i in range(len(vertElemHeaders)):
				if vertElemHeaders[i][0] == 3:
					bDoUV2 = 1
				if vertElemHeaders[i][0] == 4:
					bDoSkin = 1
				if vertElemHeaders[i][0] == 5:
					bDoColors = True
			
			nameOffsets = []	
			f.seek(namesOffs)
			for i in range(numNodes):
				nameOffsets.append(f.readUInt64())
			
			names = []
			for i in range(numNodes):
				f.seek(nameOffsets[i])
				names.append(f.readString())
			
			boneNameAddressList = []
			matNameAddressList = []
			
			if bDoSkin:		
				boneRemapTable = []
				boneInds = []
				
				#Skeleton
				f.seek(bonesOffs+4)
				boneMapCount = f.readUInt()
				
				f.seek(bonesOffs)			
				boneCount = f.readUInt()
				f.seek(12,1)
				hierarchyOffs = f.readUInt64()
				localOffs = f.readUInt64()
				globalOffs = f.readUInt64()
				inverseGlobalOffs = f.readUInt64()
					
				for b in range(boneMapCount):
					boneRemapTable.append(f.readUShort())
				
				f.seek(boneIndicesOffs)
				for i in range(boneCount):
					boneInds.append(f.readUShort())
					boneMapIndex = -1
					for b in range(len(boneRemapTable)):
						if boneRemapTable[b] == i:
							boneMapIndex = b
				
				f.seek(namesOffs)
				for i in range(countArray[1]): 
					matNameAddressList.append(f.readUInt64())
					
				for i in range(boneCount):
					boneNameAddressList.append(f.readUInt64())
			
			if runtime.isMeshVer3:
				f.seek(232)
				if runtime.sGameName == "AJ_AAT" or runtime.sGameName == "DD2" or runtime.sGameName == "DRDR":
					f.seek(f.readUInt64())
			elif runtime.sGameName == "RERT" or runtime.sGameName == "ReVerse" or runtime.sGameName == "MHRise" or runtime.sGameName == "RE8":
				f.seek(192)
			else:
				f.seek(200)
				f.seek(f.readUInt64())
				
			offsetInfo = []
			for i in range(numLODs): #LODGroup Offsets
				offsetInfo.append(f.readUInt64())
			
			#prepare array of submeshes for export:
			mainmeshCount = 0
			for ldc in range(numLODs): 
				f.seek(offsetInfo[ldc])
				mainmeshCount = f.readUByte()
				f.seek(3,1)
				uknFloat = f.readFloat()
				offsetSubOffsets = f.readUInt64()
				f.seek(offsetSubOffsets)
				meshOffsets = []
				for i in range(mainmeshCount):
					meshOffsets.append(f.readUInt64())
				for mmc in range(mainmeshCount):
					f.seek(meshOffsets[mmc])
					meshVertexInfo.append([f.readUByte(), f.readUByte(), f.readUShort(), f.readUInt(), f.readUInt(), f.readUInt()])
					for smc in range(meshVertexInfo[mmc][1]):
						matID = f.readUInt() + 1
						bFind = 0
						sourceGroupID = meshVertexInfo[len(meshVertexInfo)-1][0] if runtime.bReadGroupIds else (mmc+1)
						
						for s in range(len(objToExport)):
							#print (meshesToExport[objToExport[s]].name)
							sName = meshesToExport[objToExport[s]].name.split('_')
							thisGroupID = sName[3]
							if int(sName[1]) == (ldc+1) and int(thisGroupID) == (sourceGroupID) and ((not runtime.bUseOldNamingScheme and int(sName[5]) == (smc+1)) or (runtime.bUseOldNamingScheme and int(sName[5]) == (matID))):
								submeshes.append(copy.copy(meshesToExport[objToExport[s]]))
								bFind = 1							
								break
						if not bFind:  #create invisible placeholder submesh
							blankMeshName = "LODGroup_" + str(ldc+1) + "_MainMesh_" + str(sourceGroupID) + "_SubMesh_" + str(smc+1)
							blankTangent = runtime.NoeMat43((runtime.NoeVec3((0,0,0)), runtime.NoeVec3((0,0,0)), runtime.NoeVec3((0,0,0)), runtime.NoeVec3((0,0,0)))) 
							blankWeight = runtime.NoeVertWeight([0,0,0,0,0,0,0,0], [1,0,0,0,0,0,0,0])
							blankMesh = runtime.NoeMesh([0, 1, 2], [runtime.NoeVec3((0.00000000001,0,0)), runtime.NoeVec3((0,0.00000000001,0)), runtime.NoeVec3((0,0,0.00000000001))], blankMeshName, blankMeshName, -1, -1) #positions and faces
							blankMesh.setUVs([runtime.NoeVec3((0,0,0)), runtime.NoeVec3((0,0,0)), runtime.NoeVec3((0,0,0))]) #UV1
							blankMesh.setUVs([runtime.NoeVec3((0,0,0)), runtime.NoeVec3((0,0,0)), runtime.NoeVec3((0,0,0))], 1) #UV2
							blankMesh.setTangents([blankTangent, blankTangent, blankTangent]) #Normals + Tangents
							if bDoColors:
								blankMesh.setColors((runtime.NoeVec4((1,1,1,1)), runtime.NoeVec4((1,1,1,1)), runtime.NoeVec4((1,1,1,1)))) #vertex colors
							if bonesOffs > 0:
								blankMesh.setWeights([blankWeight,blankWeight,blankWeight]) #Weights + Indices
							submeshes.append(blankMesh)
							print (blankMeshName, "not found in FBX")
						f.seek(12, 1)	
			f.seek(0)
			
		if (len(submeshes) == 0):
			print("No submeshes detected")
			return 0
		
		#will be bounding box:
		min = runtime.NoeVec4((10000.0, 10000.0, 10000.0, runtime.fDefaultMeshScale))
		max = runtime.NoeVec4((-10000.1, -10000.1, -10000.1, runtime.fDefaultMeshScale))	
		
		bColorsExist = False
		for mesh in submeshes:
			for col in mesh.colors:
				if not bColorsExist and len(col) > 1:
					bColorsExist = True
					print ("  Vertex colors detected")
					break
			if runtime.bReWrite and bColorsExist:
				bDoColors = True
				break
				
		if runtime.bRotateBonesUpright:
			rot_mat = runtime.NoeMat43(((1, 0, 0), (0, -1, 0), (0, 0, 1), (0, 0, 0)))
			for bone in mdl.bones:
				bone.setMatrix( (bone.getMatrix().inverse() * rot_mat).inverse()) 	#rotate back to normal
				
				
		#NEW WAY (rewrite)
		#====================================================================
		if runtime.bReWrite: #save new mesh order	
			bDoUV2 = True
			#prepare new submesh order:
			newMainMeshes = []; newSubMeshes = []; newMaterialNames = []; 
			indicesBefore = 0; vertsBefore = 0; mmIndCount = 0; mmVertCount = 0
			lastMainMesh = submeshes[0].name.split('_')[3]
			meshOffsets= []
			
			for i, mesh in enumerate(submeshes):
				mat = mesh.name.split('__', 1)[1]
				if mat not in newMaterialNames:
					newMaterialNames.append(mat)
					
			numMats = len(newMaterialNames)
			print ("\nMESH Material Count:", numMats)
			
			for i, mesh in enumerate(submeshes):
				splitName = mesh.name.split('_')
				splitMatNames = mesh.name.split('__', 1)
				key = len(newMainMeshes)
				newGroupID = splitName[3]
				#try:
				if len(splitName) <= 6:
					runtime.bReWrite = False
					break
				else:
					newMaterialID = newMaterialNames.index(splitMatNames[1])
					if newGroupID != lastMainMesh:
						newMainMesh = (newSubMeshes, mmVertCount, mmIndCount, int(lastMainMesh))
						newMainMeshes.append(newMainMesh)
						newSubMeshes = []; mmIndCount = 0; mmVertCount = 0
						lastMainMesh = newGroupID
						
					newSubMeshes.append((newMaterialID, len(mesh.indices) , vertsBefore, indicesBefore))
					vertsBefore += len(mesh.positions)
					mmVertCount += len(mesh.positions)
					indicesBefore += len(mesh.indices)
					mmIndCount += len(mesh.indices)
					if i == len(submeshes)-1:
						newMainMesh = (newSubMeshes, mmVertCount, mmIndCount,  int(lastMainMesh))
						newMainMeshes.append(newMainMesh)
				#except:
				#	print("Failed to parse mesh name", mesh.name)
			
			#print(newMainMeshes)
			
			LOD1Offs = 176 if (runtime.sGameName == "DD2" or runtime.sGameName == "AJ_AAT" or runtime.sGameName == "DRDR") else 168 if runtime.isMeshVer3 else 128 if (runtime.sGameName == "RERT" or runtime.sGameName == "RE8" or runtime.sGameName == "MHRise") else 136
			
			#header:
			bs.writeUInt(1213416781) #MESH
			bs.writeUInt(formats[runtime.sGameName]["meshMagic"])
				
			bs.writeUInt(0) #Filesize
			bs.writeUInt(0) #LODGroupHash
			
			if runtime.isMeshVer3:
				bs.writeUByte(3) #flag
				if runtime.sGameName == "DD2" or runtime.sGameName == "AJ_AAT" or runtime.sGameName == "DRDR":
					bs.writeUByte(130) #solvedOffset
					bs.writeUShort(84) #uknSF6
				else:
					bs.writeUByte(2) #solvedOffset
					bs.writeUShort(0) #uknSF6
				bs.writeUInt(len(mdl.bones) * bDoSkin + numMats) #Node Count
				bs.writeUInt64(0) #ukn
				bs.writeUInt64(LOD1Offs) #LODOffs
				bs.writeUInt64(0) #ShadowLODOffs
				bs.writeUInt64(0) #OccluderMeshOffs
				bs.writeUInt64(0) #bsHeaderOffs
				bs.writeUInt64(0) #ukn2
				bs.writeUInt64(0) #vert_buffOffs
				bs.writeUInt64(0) #normalsRecalcOffs
				bs.writeUInt64(0) #groupPivotOffs      
				bs.writeUInt64(0) #BBHeaderOffs
				bs.writeUInt64(0) #bonesOffs
				bs.writeUInt64(0) #matIndicesOffs
				bs.writeUInt64(0) #boneIndicesOffs
				bs.writeUInt64(0) #bsIndicesOffs
				bs.writeUInt64(0) #ukn3
				bs.writeUInt64(0) #namesOffs
				bs.writeUInt64(0) #verticesOffset
				bs.writeUInt64(0) #ukn4/padding
				if runtime.sGameName == "DD2":
					bs.writeUInt64(0) #ukn5/padding
				
			else:
				bs.writeUShort(3) #flag
				bs.writeUShort(len(mdl.bones) * bDoSkin + numMats) #Node Count
				bs.writeUInt(0) #LODGroupHash
				bs.writeUInt64(LOD1Offs) #LODs address
				bs.writeUInt64(0) #Shadow LODs address
				bs.writeUInt64(0) #occluderMeshOffs
				bs.writeUInt64(0) #Bones Address
				bs.writeUInt64(0) #Normal Recalculation Address
				bs.writeUInt64(0) #Blendshapes Header Address
				bs.writeUInt64(0) #Floats Header Address
				bs.writeUInt64(0) #Vertex Buffer Headers Address
				bs.writeUInt64(0)
				bs.writeUInt64(0) #Material Indices Table Address
				bs.writeUInt64(0) #Bones Indices Table Address
				bs.writeUInt64(0) #Blendshapes Indices Table Address
				bs.writeUInt64(0) #Names Address
				if runtime.sGameName == "RE2" or runtime.sGameName == "RE3" or runtime.sGameName == "DMC5":
					bs.writeUInt64(0)
			
			#LODs:
			bs.writeByte(1) #set to one LODGroup
			bs.writeByte(len(newMaterialNames)) #mat count
			bs.writeByte(2) #set to 2 UV channels
			bs.writeByte(1) #unknown
			bs.writeUInt(len(submeshes)) #total mesh count
			
			if runtime.BBskipBytes==8:
				bs.writeUInt64(0)
			
			for i in range(6):
				bs.writeUInt64(0) #main bounding sphere+box placeholder
			
			bs.writeUInt64(bs.tell()+8) #offset to LODOffsets
			
			if (bs.tell()+8) % 16 != 0:
				bs.writeUInt64(bs.tell()+16) #first (and only) LODOffset
			else:
				bs.writeUInt64(bs.tell()+8)
			padToNextLine(bs)
				
			#Write LODGroup (DRDR fucks up here):
			bs.writeUInt(len(newMainMeshes))
			LODDist = runtime.openOptionsDialog.LODDist if runtime.openOptionsDialog else 0.02667995
			bs.writeFloat(LODDist) #unknown, maybe LOD distance change
			bs.writeUInt64(bs.tell()+8) #Mainmeshes offset
			
			newMainMeshesOffset = bs.tell()
			for i in range(len(newMainMeshes)):
				bs.writeUInt64(0)
			
			while(bs.tell() % 16 != 0):
				bs.writeByte(0)

			#write new MainMeshes:
			for i, mm in enumerate(newMainMeshes):
				
				newMMOffset = bs.tell()
				bs.writeByte(mm[len(mm)-1]) #Group ID
				bs.writeByte(len(mm[0])) #Submesh count
				bs.writeShort(0)
				bs.writeInt(0)
				bs.writeUInt(mm[1]) #MainMesh index count
				bs.writeUInt(mm[2]) #MainMesh vertex count
				meshVertexInfo.append([i, len(mm[0]), 0, 0, mm[1], mm[2]])
				
				for j, submesh in enumerate(mm[0]):
					#print ("New mainmesh GroupID", mm[len(mm)-1], "submesh", j)
					bs.writeUInt(submesh[0])
					if runtime.sGameName == "DRDR":
						bs.writeUInt(0)
					bs.writeUInt(submesh[1])
					bs.writeUInt(submesh[2])
					bs.writeUInt(submesh[3])
					if runtime.sGameName == "DRDR":
						bs.writeUInt(0)
					if runtime.sGameName != "RE7" and runtime.sGameName != "RE2" and runtime.sGameName != "RE3" and runtime.sGameName != "DMC5":
						bs.writeUInt64(0)
				pos = bs.tell()
				bs.seek(newMainMeshesOffset + i * 8)
				bs.writeUInt64(newMMOffset)
				meshOffsets.append(newMMOffset)
				bs.seek(pos)
			
			bonesOffs = bs.tell()
			
			if bDoSkin:
				bs.seek(runtime.bonesOffsLocation)
			else:
				bs.seek(runtime.nodesIndicesOffsLocation) #to material indices offset instead
				
			bs.writeUInt64(bonesOffs)
			bs.seek(bonesOffs)
			mainmeshCount = len(newMainMeshes)
			
		if bDoUV2:
			vertElemCount += 1
		if bDoColors:
			vertElemCount += 1

		if (runtime.bReWrite or runtime.bWriteBones): 
			if bDoSkin:
				boneRemapTable = []
				
				maxBoneMapLength = 256 if runtime.sGameName != "SF6" else 1024
				
				if bAddNumbers and len(newSkinBoneMap) > 0:
					boneMapLength = len(newSkinBoneMap)
				else:
					boneMapLength = maxBoneMapLength if len(mdl.bones) > maxBoneMapLength else len(mdl.bones)

				if not runtime.bReWrite:
					bs.writeBytes(f.readBytes(bonesOffs)) #to bone name start
			
				#write new skeleton header
				bs.writeUInt(len(mdl.bones)) #bone count
				bs.writeUInt(boneMapLength)  #bone map count

				for b in range(5): 
					bs.writeUInt64(0)
				
				#write skin bone map:
				if bAddNumbers and len(newSkinBoneMap) > 0:
					for i in range(len(newSkinBoneMap)):
						bs.writeUShort(newSkinBoneMap[i])
					boneRemapTable = newSkinBoneMap
				else:
					for i in range(boneMapLength): 
						bs.writeUShort(i)
						boneRemapTable.append(i)
				padToNextLine(bs)
				
				if (len(boneRemapTable) > maxBoneMapLength):
					print ("WARNING! Bone map is greater than", maxBoneMapLength, "bones!")
					
				#write hierarchy
				newHierarchyOffs = bs.tell()
				for i, bone in enumerate(mdl.bones):
					bs.writeUShort(i) # bone index
					bs.writeUShort(bone.parentIndex)
					nextSiblingIdx = -1
					for j, bn in enumerate(mdl.bones):
						if i < j and bone != bn and bone.parentIndex == bn.parentIndex:
							nextSiblingIdx = j
							break
					bs.writeUShort(nextSiblingIdx)
					nextChildIdx = -1
					for j, bn in enumerate(mdl.bones):
						if bn.parentIndex == i:
							nextChildIdx = j
							break
					bs.writeUShort(nextChildIdx)
					cousinIdx = -1
					cousinBoneName = ""
					bnName = bonesList[i].lower()
					if bnName.startswith('r_'): 
						cousinBoneName = bnName.replace('r_','l_')
					elif bnName.startswith('l_'):
						cousinBoneName = bnName.replace('l_','r_')
					elif runtime.isMeshVer3 or bnName.startswith("root") or bnName.startswith("cog") or bnName.startswith("hip") \
					or bnName.startswith("waist") or bnName.startswith("spine") or bnName.startswith("chest") \
					or bnName.startswith("stomach") or bnName.startswith("neck") or bnName.startswith("head") \
					or bnName.startswith("null_"):
						cousinIdx = i
					if cousinBoneName != "":
						for j in range(len(mdl.bones)):
							if bonesList[j].lower() == cousinBoneName:
								cousinIdx = j
								break
					bs.writeUShort(cousinIdx)
					padToNextLine(bs)
			
				#prepare transform data:
				localTransforms = []
				globalTransforms = []
				for bone in mdl.bones:
					boneGlobalMat = bone.getMatrix().toMat44()
					boneGlobalMat[3] = boneGlobalMat[3] * 0.01
					boneGlobalMat[3][3] = 1.0
					globalTransforms.append(boneGlobalMat)
					if bone.parentIndex != -1:
						pMat = mdl.bones[bone.parentIndex].getMatrix().toMat44()
						boneLocalMat = (bone.getMatrix().toMat44() * pMat.inverse())
						boneLocalMat[3] = boneLocalMat[3] * 0.01
						boneLocalMat[3][3] = 1.0
						localTransforms.append(boneLocalMat)
					else:
						localTransforms.append(boneGlobalMat)
				
				#write local bone transforms:
				newLocalOffs = bs.tell()
				for i in range(len(localTransforms)):
					bs.writeBytes(localTransforms[i].toBytes())
				
				#write global bone transforms:
				newGlobalOffs = bs.tell()
				for i in range(len(globalTransforms)):
					bs.writeBytes(globalTransforms[i].toBytes())
				
				#write inverse global bone transforms:
				newInvGlobOffs = bs.tell()
				for i in range(len(globalTransforms)):
					bs.writeBytes(globalTransforms[i].inverse().toBytes())
			
			#collect material names:
			materialNames = []
			if runtime.bReWrite:
				materialNames = newMaterialNames
			else:
				for i in range(numMats): 
					f.seek(matNameAddressList[i])
					materialNames.append(f.readString())
			
			#write material indices:
			newMatIndicesOffs = bs.tell()
			for i in range(numMats): 
				if runtime.bReWrite:
					bs.writeUShort(i)
				else:
					f.seek(nodesIndicesOffs + i * 2)
					bs.writeUShort(f.readUShort())
			padToNextLine(bs)
			
			if bDoSkin:
				boneInds = []
				#write bone map indices:
				newBoneMapIndicesOffs = bs.tell()
				for i in range(len(mdl.bones)): 
					bs.writeUShort(numMats + i)
					boneInds.append(numMats + i)
				padToNextLine(bs)
			
			#write names offsets:
			newNamesOffs = bs.tell()
			nameStringsOffs = newNamesOffs + (numMats + len(mdl.bones) * bDoSkin) * 8
			while nameStringsOffs % 16 != 0:
				nameStringsOffs += 1
			
			for i in range(numMats): 
				bs.writeUInt64(nameStringsOffs)
				nameStringsOffs += len(materialNames[i]) + 1
				
			if bDoSkin:
				for i in range(len(mdl.bones)): 
					bs.writeUInt64(nameStringsOffs)
					nameStringsOffs += len(bonesList[i]) + 1
			padToNextLine(bs)
			
			names = []
			#write name strings
			for i in range(len(materialNames)):
				bs.writeString(materialNames[i])
				names.append(materialNames[i])
			if bDoSkin:
				for i in range(len(bonesList)): 
					bs.writeString(bonesList[i])
					names.append(bonesList[i]) 
			padToNextLine(bs)
			
			if bDoSkin:
				#Write unknown DD2 hashes
				if isDD2Mesh:
					DD2HashesOffset = bs.tell()
					bs.writeUInt(2745047434)
					for i in range(mainmeshCount - 1):
						bs.writeUInt(0)
					padToNextLine(bs)
			
				#write bounding boxes
				newBBOffs = bs.tell()
				bs.writeUInt64(len(newSkinBoneMap))
				bs.writeUInt64(bs.tell() + 8)
				for i in range(len(newSkinBoneMap)):
					for j in range(3): bs.writeFloat(-runtime.BoundingBoxSize)
					bs.writeFloat(1)
					for j in range(3): bs.writeFloat(runtime.BoundingBoxSize)
					bs.writeFloat(1)
				newVertBuffHdrOffs = bs.tell()
				
				#fix bones header
				bs.seek(bonesOffs + 16)
				bs.writeUInt64(newHierarchyOffs)
				bs.writeUInt64(newLocalOffs)
				bs.writeUInt64(newGlobalOffs)
				bs.writeUInt64(newInvGlobOffs)
			else:
				newVertBuffHdrOffs = bs.tell()
			
			#fix main header
			bs.seek(runtime.numNodesLocation)
			bs.writeUShort(numMats + len(mdl.bones) * bDoSkin) #numNodes
				
			if bDoSkin:
				bs.seek(runtime.floatsHdrOffsLocation)
				bs.writeUInt64(newBBOffs)
				bs.seek(runtime.vBuffHdrOffsLocation)
				bs.writeUInt64(newVertBuffHdrOffs)
				bs.seek(runtime.nodesIndicesOffsLocation)
				bs.writeUInt64(newMatIndicesOffs)
				bs.writeUInt64(newBoneMapIndicesOffs)
			else:
				bs.seek(runtime.vBuffHdrOffsLocation)
				bs.writeUInt64(newVertBuffHdrOffs)
			bs.seek(runtime.namesOffsLocation)
			print(newNamesOffs)
			bs.writeUInt64(newNamesOffs)
			
			#fix vertexBufferHeader
			bs.seek(newVertBuffHdrOffs)
			
			SF6SkipBytes = 0 if not runtime.isMeshVer3 else 32
			newVertBuffOffs = newVertBuffHdrOffs + 72 + SF6SkipBytes + 8*bDoSkin + 8*bDoUV2 + 8*bDoColors + 2*RERTBytes
			
			bs.writeUInt64(bs.tell() + 48 + SF6SkipBytes + 2*RERTBytes)
			bs.writeUInt64(newVertBuffOffs)
			
			if runtime.sGameName == "RERT":
				bs.writeUInt64(0)
			bs.writeUInt64(0)
			bs.writeUInt64(0)
			bs.writeShort(vertElemCount)
			bs.writeShort(vertElemCount)
			bs.writeUInt64(0)
			bs.writeInt(-newVertBuffOffs)
			
			if runtime.isMeshVer3:
				for i in range(4):
					bs.writeUInt64(0)
			if runtime.sGameName == "RERT": # and (bs.tell() % 8) != 0:
				bs.writeUInt64(0)
			
			bs.writeUInt64(786432) #positions VertElemHeader
			bs.writeUInt64(524289) #normal VertElemHeader
			bs.writeUInt64(262146) #UV0 VertElemHeader
			if bDoUV2:
				bs.writeUInt64(262147) #UV2 VertElemHeader
			if bDoSkin:
				bs.writeUInt64(1048580) #Skin VertElemHeader
			if bDoColors:
				bs.writeUInt64(262149) #Colors VertElemHeader
				
		elif not runtime.bReWrite:
			bs.writeBytes(f.readBytes(vertBuffOffs)) #copy to vertex buffer header
			newVertBuffHdrOffs = bs.tell()
		
		if bDoSkin:
			skinBoneMapNames = []
			for b in range(len(boneRemapTable)):
				bnName = names[boneInds[boneRemapTable[b]]]
				skinBoneMapNames.append(bnName)
		
		vertexStrideStart = 0
		submeshVertexCount = []
		submeshVertexStride = []
		submeshFaceCount = []
		submeshFaceStride = []
		submeshFaceSize = []
		boneWeightBBs = {}

		for mesh in submeshes:
			if len(mesh.morphList) > 0:
				mesh.positions = mesh.morphList[0].positions

		#Write vertex data
		vertexPosStart = bs.tell()
		for mesh in submeshes:
			submeshVertexStride.append(vertexStrideStart)
			for vcmp in mesh.positions:
				bs.writeBytes((vcmp * newScale).toBytes())
				if vcmp[0] > max[0]: max[0] = vcmp[0] 	#calculate main bounding box
				if vcmp[0] < min[0]: min[0] = vcmp[0]
				if vcmp[1] > max[1]: max[1] = vcmp[1]
				if vcmp[1] < min[1]: min[1] = vcmp[1]
				if vcmp[2] > max[2]: max[2] = vcmp[2]
				if vcmp[2] < min[2]: min[2] = vcmp[2]
			submeshVertexCount.append(len(mesh.positions))
			vertexStrideStart += len(mesh.positions)
			
		normalTangentStart = bs.tell()	
		for m, mesh in enumerate(submeshes):
			for v, vcmp in enumerate(mesh.tangents):
				bs.writeByte(int(vcmp[0][0] * 127 + 0.5000000001)) #normal
				bs.writeByte(int(vcmp[0][1] * 127 + 0.5000000001))
				bs.writeByte(int(vcmp[0][2] * 127 + 0.5000000001))
				bs.writeByte(0)
				bs.writeByte(int(vcmp[2][0] * 127 + 0.5000000001)) #bitangent
				bs.writeByte(int(vcmp[2][1] * 127 + 0.5000000001))
				bs.writeByte(int(vcmp[2][2] * 127 + 0.5000000001))
				TNW = dot(cross(vcmp[0], vcmp[1]), vcmp[2])
				if (TNW < 0.0): #default way
					bs.writeByte(runtime.w1)
				else:
					bs.writeByte(runtime.w2)
					
		UV0start = bs.tell()
		for mesh in submeshes:
			for vcmp in mesh.uvs:
				bs.writeHalfFloat(vcmp[0])
				bs.writeHalfFloat(vcmp[1])
					
		UV1start = bs.tell()
		if bDoUV2:
			for mesh in submeshes:
				if len(mesh.lmUVs) != len(mesh.positions):
					mesh.lmUVs = mesh.uvs
				for vcmp in mesh.lmUVs:
					bs.writeHalfFloat(vcmp[0])
					bs.writeHalfFloat(vcmp[1])

		def writeBoneID(bID, i):
			if runtime.sGameName == "SF6":
				if i==3:
					bs.writeBits(0, 2)
				bs.writeBits(bID, 10)
			else:
				bs.writeUByte(bID)
		
		boneIdMax = 6 if runtime.sGameName == "SF6" else 8
		bnWeightStart = bs.tell()
		
		if bDoSkin:
			doDD2Skin = isDD2Mesh and bDoSkin
			
			for m, mesh in enumerate(submeshes):
				pos = bs.tell()
				for vcmp in mesh.weights: #write 0's
					for i in range(4):
						bs.writeFloat(0)
				bs.seek(pos)
				
				for i, vcmp in enumerate(mesh.weights): #write bone indices & weights over 0's
					total = 0
					tupleList = []
					weightList = []
					vertPos = mesh.positions[i]
					for idx in range(len(vcmp.weights)):
						weightList.append(round(vcmp.weights[idx] * 255.0))
						total += weightList[idx]
					if runtime.bNormalizeWeights and total != 255:
						weightList[0] += 255 - total
						print ("Normalizing vertex weight", mesh.name, "vertex", i,",", total)
						
					for idx in range(len(vcmp.weights)):
						if idx > boneIdMax:
							if not runtime.isMeshVer3: 
								print ("Warning: ", mesh.name, "vertex", i,"exceeds the vertex weight limit of ", boneIdMax, "!", )
							break
						elif vcmp.weights[idx] != 0:				
							byteWeight = weightList[idx]
							tupleList.append((byteWeight, vcmp.indices[idx]))
						if runtime.bCalculateBoundingBoxes:
							thisBoneBB = boneWeightBBs[ vcmp.indices[idx] ] if vcmp.indices[idx] in boneWeightBBs else [999999.0, 999999.0, 999999.0, -999999.0, -999999.0, -999999.0]
							if vertPos[0] < thisBoneBB[0]: thisBoneBB[0] = vertPos[0]
							if vertPos[1] < thisBoneBB[1]: thisBoneBB[1] = vertPos[1]
							if vertPos[2] < thisBoneBB[2]: thisBoneBB[2] = vertPos[2]
							if vertPos[0] > thisBoneBB[3]: thisBoneBB[3] = vertPos[0]
							if vertPos[1] > thisBoneBB[4]: thisBoneBB[4] = vertPos[1]
							if vertPos[2] > thisBoneBB[5]: thisBoneBB[5] = vertPos[2]
							boneWeightBBs[ vcmp.indices[idx] ] = thisBoneBB
							
					tupleList = sorted(tupleList, reverse=True) #sort in ascending order
					pos = bs.tell()
					lastBone = 0
					for idx in range(len(tupleList)):
						bFind = False
						for b in range(len(boneRemapTable)):
							bnName = names[boneInds[boneRemapTable[b]]]
							#if doDD2Skin and "_Edit" in bnName:
							#	bnName = ""
							if bnName == bonesList[tupleList[idx][1]]:
								writeBoneID(b, idx)
								lastBone = b
								bFind = True
								break	
						if bFind == False: #assign unmatched bones
							if not runtime.bRigToCoreBones:
								writeBoneID(lastBone, idx)
							else:
								for b in range(lastBone, 0, -1):
									if names[boneInds[boneRemapTable[b]]].find("spine") != -1 or names[boneInds[boneRemapTable[b]]].find("hips") != -1:
										writeBoneID(b, idx)
										break
										
					for x in range(len(tupleList), 8):
						writeBoneID(lastBone, x)
					
					bs.seek(pos+8)
					for wval in range(len(tupleList)):
						bs.writeUByte(tupleList[wval][0])
					bs.seek(pos+16)
								
		colorsStart = bs.tell()
		if bDoColors:
			for m, mesh in enumerate(submeshes):
				if bColorsExist:
					for p, pos in enumerate(mesh.positions):
						RGBA = mesh.colors[p] if p < len(mesh.colors) else runtime.NoeVec4((1.0, 1.0, 1.0, 1.0))
						for c in range(4): 
							color = RGBA[c] if c < len(RGBA) else 1.0
							bs.writeUByte(int(color * 255 + 0.5))
				else:
					for p, pos in enumerate(mesh.positions):
						bs.writeInt(-1)
		
		vertexDataEnd = bs.tell()
		
		for mesh in submeshes:
			faceStart = bs.tell()
			submeshFaceStride.append(faceStart - vertexDataEnd)
			submeshFaceCount.append(len(mesh.indices))
			submeshFaceSize.append(len(mesh.indices))
			for idx in mesh.indices:
				bs.writeUShort(idx)
			if ((bs.tell() - faceStart) / 6) % 2 != 0: #padding
				bs.writeUShort(0)
		faceDataEnd = bs.tell()
		
		#update mainmesh and submesh headers
		loopSubmeshCount = 0
		for ldc in range(numLODs): 
			for mmc in range(mainmeshCount):
				mainmeshVertexCount = 0
				mainmeshFaceCount = 0
				bs.seek(meshOffsets[mmc] + 16)
				
				for smc in range(meshVertexInfo[mmc][1]):
					bs.seek(4, 1)
					bs.writeUInt(submeshFaceCount[loopSubmeshCount])
					bs.writeUInt(int(submeshFaceStride[loopSubmeshCount] / 2))
					bs.writeUInt(submeshVertexStride[loopSubmeshCount])
					if formats[runtime.sGameName]["meshVersion"] >= 3 or runtime.sGameName == "RERT" or runtime.sGameName == "ReVerse" or runtime.sGameName == "MHRise" or runtime.sGameName == "RE8" or runtime.sGameName == "SF6" or runtime.sGameName == "RE4":
						bs.seek(8, 1)
					mainmeshVertexCount += submeshVertexCount[loopSubmeshCount]
					mainmeshFaceCount += submeshFaceSize[loopSubmeshCount]
					loopSubmeshCount += 1
				bs.seek(meshOffsets[mmc]+8)
				bs.writeUInt(mainmeshVertexCount)
				bs.writeUInt(mainmeshFaceCount)
			
		#Fix vertex buffer header:
		skipAmt = 16 if not runtime.isMeshVer3 else 24
		fcBuffSize = faceDataEnd - vertexDataEnd
		if runtime.bReWrite or runtime.bWriteBones:
			bs.seek(newVertBuffHdrOffs+skipAmt) 
		else: 
			bs.seek(vBuffHdrOffs+skipAmt)
		
		if runtime.isMeshVer3:
			facesDiff = (80 + 8*vertElemCountB if runtime.bWriteBones else 0) if not runtime.bReWrite else (80 + 8*vertElemCount)
			bs.writeUInt(faceDataEnd - vertexPosStart) #total buffer size
			#print("faces offset", bs.tell(), vertexDataEnd, newVertBuffHdrOffs, facesDiff, vertexDataEnd - newVertBuffHdrOffs - facesDiff)
			bs.writeUInt(vertexDataEnd - newVertBuffHdrOffs - facesDiff) #face buffer offset
			bs.seek(4,1) #element counts
			bs.writeUInt(faceDataEnd - vertexPosStart) #total buffer size2
			bs.writeUInt(faceDataEnd - vertexPosStart) #total buffer size3
			bs.writeInt(-(vertexPosStart))
			bs.seek(32, 1)
		else:
			bs.writeUInt64(vertexDataEnd) #face buffer offset
			bs.seek(RERTBytes, 1)
			bs.writeUInt(vertexDataEnd - vertexPosStart) #vertex buffer size
			bs.writeUInt(fcBuffSize) #face buffer size
			bs.seek(4,1) #element counts
			bs.writeUInt64(fcBuffSize)
			bs.writeInt(-(vertexPosStart))
		
		if runtime.bReWrite:
			bs.seek(newVertBuffHdrOffs + 48 + SF6SkipBytes + (RERTBytes * 2))
		else:
			bs.seek(RERTBytes, 1)
		
		vertElemHdrStart = bs.tell()
		
		for i in range (vertElemCount):
			elementType = bs.readUShort()
			elementSize = bs.readUShort()
			if elementType == 0:
				bs.writeUInt(vertexPosStart - vertexPosStart)
			elif elementType == 1:
				bs.writeUInt(normalTangentStart - vertexPosStart)
			elif elementType == 2:
				bs.writeUInt(UV0start - vertexPosStart)
			elif elementType == 3:
				bs.writeUInt(UV1start - vertexPosStart)
			elif elementType == 4:
				bs.writeUInt(bnWeightStart - vertexPosStart)
			elif elementType == 5:
				bs.writeUInt(colorsStart - vertexPosStart) 
		
		if runtime.isMeshVer3: 
			DD2amt = 8 if isDD2Mesh else 0
			bs.seek(136 + int(DD2amt * 2))
			bs.writeUInt64(vertElemHdrStart-16) #fix ukn3
			bs.seek(152 + DD2amt)
			bs.writeUInt64(vertexPosStart) #fix Vertices offset
			if isDD2Mesh:
				bs.seek(144)
				bs.writeUInt64(DD2HashesOffset)
		
		#fix main bounding box:
		bs.seek(LOD1Offs+8+runtime.BBskipBytes)
		
		#Calculate Bounding Sphere:
		BBcenter = runtime.NoeVec3((min[0]+(max[0]-min[0])/2, min[1]+(max[1]-min[1])/2, min[2]+(max[2]-min[2])/2))
		sphereRadius = 0
		for mesh in mdl.meshes:
			for position in mesh.positions:
				distToCenter = (position - BBcenter).length()
				if distToCenter > sphereRadius: 
					sphereRadius = distToCenter
					
		bs.writeBytes((BBcenter * newScale).toBytes()) #Bounding Sphere
		bs.writeFloat(sphereRadius * newScale) #Bounding Sphere radius
		bs.writeBytes((min * newScale).toBytes()) #BBox min
		bs.writeBytes((max * newScale).toBytes()) #BBox max
		if runtime.isMeshVer3:
			bs.seek(-20,1); bs.writeUInt(1)
			bs.seek(12,1); bs.writeUInt(1)
		
		#fix skeleton bounding boxes:
		if bDoSkin and runtime.bCalculateBoundingBoxes:
			for idx, box in boneWeightBBs.items():
				try:
					if runtime.bReWrite or runtime.bWriteBones:
						remappedBoneIdx = newSkinBoneMap.index(idx)
					else:
						remappedBoneIdx = boneRemapTable.index(idx)
					pos = mdl.bones[newSkinBoneMap[remappedBoneIdx]].getMatrix()[3]
				except:
					continue
				bs.seek(newBBOffs+16+remappedBoneIdx*32) 
				boneWeightBBs[idx] = [(box[0]-pos[0])*newScale, (box[1]-pos[1])*newScale, (box[2]-pos[2])*newScale, 1.0, (box[3]-pos[0])*newScale, (box[4]-pos[1])*newScale, (box[5]-pos[2])*newScale, 1.0]
				box = boneWeightBBs[idx]
				for coord in box:
					bs.writeFloat(coord)
		
		#set to only one LODGroup
		bs.seek(LOD1Offs)
		bs.writeByte(1)
		
		#disable shadow LODs
		bs.seek(runtime.LOD1OffsetLocation+8)
		bs.writeUInt(0)
		
		#disable normals recalculation data
		bs.seek(runtime.normalsRecalcOffsLocation)
		bs.writeUInt(0)
		
		#disable group pivots data
		bs.seek(88)
		bs.writeUInt(0)
		
		#set numModels flag
		doSetFlag = runtime.bSetNumModels or runtime.bDoVFX or (runtime.openOptionsDialog and runtime.openOptionsDialog.flag != -1)
		if doSetFlag or runtime.bReWrite:
			bs.seek(16)
			if runtime.openOptionsDialog and runtime.openOptionsDialog.flag != -1:
				bitFlag = runtime.openOptionsDialog.flag
			else:
				bitFlag = 0x00
				if runtime.bDoVFX or runtime.rapi.getOutputName().find("2109148288") != -1 or runtime.isMeshVer3: 
					bitFlag = bitFlag + 0x80
				if bDoSkin: 
					bitFlag = bitFlag + 0x03
			print("Flag: ", bitFlag)
			bs.writeUByte(bitFlag)
		
		#remove blendshapes offsets
		bs.seek(runtime.bsHdrOffLocation)
		bs.writeUInt(0)
		bs.seek(runtime.bsIndicesOffLocation)
		bs.writeUInt(0)
		
		fileEnd = faceDataEnd
		
		if runtime.sGameName == "DD2" and bDoSkin:
			bs.seek(12)
			bs.writeUInt(2303293740) #Unknown
			
			#Extra weights buffer:
			bs.seek(bnWeightStart)
			bnWtBuffSz = colorsStart - bnWeightStart
			weightBytes = bs.readBytes(bnWtBuffSz)
			bs.seek(bnWeightStart)
			dd2BoneIdx = skinBoneMapNames.index("Spine_1") if "Spine_1" in skinBoneMapNames else 0
			
			for i in range(int(bnWtBuffSz / 16)):
				bID = bs.readUByte()
				bs.seek(-1, 1)
				bs.writeUInt64(0)
				bs.writeUInt64(255)
			bs.seek(fileEnd)
			padToNextLine(bs)
			exWeightsBuffStart = bs.tell()
			bs.writeBytes(weightBytes)
			fileEnd = bs.tell()
			bs.seek(newVertBuffHdrOffs+16) 
			bs.writeUInt64(exWeightsBuffStart)
			bs.seek(newVertBuffHdrOffs+48) 
			bs.writeUInt64(bnWtBuffSz)
		
		#fileSize
		bs.seek(8)
		bs.writeUInt(fileEnd) 
		
		return 1

	return (
		_writePragmataExactTemplate,
		writePragmataCandidate002Exact,
		_pragmataGeometryFromModel,
		_pragmataWriterPathIdentity,
		pragmataMeshWriteModel,
		getExportName,
		meshWriteModel,
	)


"""Geometry implementation bound to one plugin runtime."""

import re

# Host/state/callback dependencies (resolved on use, never copied).
GEOMETRY_RUNTIME_DEPENDENCIES = (
	'NoeMesh',
)


def bind_geometry(runtime):
	def sort_human(List):
		convert = lambda text: float(text) if text.isdigit() else text
		return sorted(List, key=lambda mesh: [convert(c) for c in re.split('([-+]?[0-9]*\.?[0-9]*)', mesh.name)])

	def recombineNoesisMeshes(mdl):

		meshesBySourceName = {}
		for mesh in mdl.meshes:
			meshesBySourceName[mesh.sourceName] = meshesBySourceName.get(mesh.sourceName) or []
			meshesBySourceName[mesh.sourceName].append(mesh)

		combinedMeshes = []
		for sourceName, meshList in meshesBySourceName.items():
			newPositions = []
			newUV1 = []
			newUV2 = []
			newUV3 = []
			newTangents = []
			newWeights = []
			newIndices = []
			newColors = []
			for mesh in meshList:
				tempIndices = []
				for index in mesh.indices:
					tempIndices.append(index + len(newPositions))
				newPositions.extend(mesh.positions)
				newUV1.extend(mesh.uvs)
				newUV2.extend(mesh.lmUVs)
				newUV3.extend(mesh.uvxList[0] if len(mesh.uvxList) > 0 else [])
				newColors.extend(mesh.colors)
				newTangents.extend(mesh.tangents)
				newWeights.extend(mesh.weights)
				newIndices.extend(tempIndices)

			combinedMesh = runtime.NoeMesh(newIndices, newPositions, meshList[0].sourceName, meshList[0].sourceName, mdl.globalVtx, mdl.globalIdx)
			combinedMesh.setTangents(newTangents)
			combinedMesh.setWeights(newWeights)
			combinedMesh.setUVs(newUV1)
			combinedMesh.setUVs(newUV2, 1)
			combinedMesh.setUVs(newUV3, 2)
			combinedMesh.setColors(newColors)
			if len(combinedMesh.positions) > 65535:
				print("Warning: Mesh exceeds the maximum of 65535 vertices (has", str(len(combinedMesh.positions)) + "):\n	", combinedMesh.name)
			else:
				combinedMeshes.append(combinedMesh)

		return combinedMeshes

	return (
		sort_human,
		recombineNoesisMeshes,
	)
