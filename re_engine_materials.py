"""Materials implementation bound to one plugin runtime."""

import re_engine_common as re_common
import struct
import math
from re_engine_types import _materialCheckedRange, _materialScalar
import re_engine_tex as texture_import
from re_engine_paths import (
	resolveMaterialCompanionPath, resolveTextureResourcePath, findMaterialCompanionPath,
	findLinkedMaterialPath,
	_materialNativesRoot,
)
from re_engine_config import (
	MDF2_51_EXACT_TEXTURE_COUNT,
	MDF2_51_EXACT_PROPERTY_COUNT,
	formats,
	composeImportProfile,
	MDF2_51_ENTRY_SIZE,
	MDF2_51_PROPERTY_ENTRY_SIZE,
	MDF2_51_TEXTURE_ENTRY_SIZE,
	PRAGMATA_TEXTURE_SEMANTICS,
)
from re_engine_types import (
	MaterialProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'NoeMaterial',
	'noesis',
)


def _new_material(material_type, name):
	material = material_type(name, "")
	material.setDefaultBlend(0)
	return material


def _materialUtf16z(data, offset, limit, label):
	return re_common.read_utf16z(
		data, offset, limit, label, MaterialProfileError)

def validateWildsMdfProfile(data, path):
	"""Bound the observed MDF45 records before using the legacy material builder."""
	if not path.lower().endswith(".mdf2.45"):
		raise MaterialProfileError("mdf2-suffix-mismatch")
	_materialCheckedRange(data, 0, 16, "mdf2-header")
	if data[:4] != b"MDF\0":
		raise MaterialProfileError("mdf2-magic-mismatch")
	version, count = struct.unpack_from("<HH", data, 4)
	if version != 1 or not count:
		raise MaterialProfileError("mdf2-version-or-count-mismatch")
	entries_end = 16 + count * 100
	_materialCheckedRange(data, 16, count * 100, "material-entries")
	ranges = [(0, entries_end)]
	strings = set()
	def region(offset, size, label):
		value = _materialCheckedRange(data, offset, size, label)
		if size and any(re_common.ranges_overlap(value, old) for old in ranges):
			raise MaterialProfileError("range-overlap:" + label)
		if size:
			ranges.append(value)
	def string(offset, label):
		value = _materialUtf16z(data, offset, len(data), label)
		if not value:
			raise MaterialProfileError("empty-string:" + label)
		if offset not in strings:
			region(offset, len(value.encode("utf-16-le")) + 2, label)
			strings.add(offset)
		return value
	for i in range(count):
		entry = 16 + i * 100
		string(_materialScalar(data, entry, "<Q", "material-name"), "material-name")
		size, props, textures = struct.unpack_from("<III", data, entry + 12)
		prop_table, tex_table, unused, values, master, unused2 = struct.unpack_from("<6Q", data, entry + 52)
		string(master, "master-material")
		region(prop_table, props * 24, "property-table")
		region(tex_table, textures * 32, "texture-table")
		region(values, size, "property-data")
		for index in range(props):
			name, unused_hash, offset, number = struct.unpack_from("<QQII", data, prop_table + index * 24)
			string(name, "property-name")
			if not number or offset % 4 or offset + number * 4 > size:
				raise MaterialProfileError("property-data-out-of-bounds")
			floats = struct.unpack_from("<" + str(number) + "f", data, values + offset)
			if any(not math.isfinite(value) for value in floats):
				raise MaterialProfileError("non-finite-material-property")
		for index in range(textures):
			slot, unused_hash, resource, unused_flags = struct.unpack_from("<4Q", data, tex_table + index * 32)
			string(slot, "texture-slot")
			resource = string(resource, "texture-path").replace("@", "").replace("\\", "/")
			if (":" in resource or not resource.endswith(".tex") or
					any(part in ("", ".", "..") for part in resource.split("/"))):
				raise MaterialProfileError("texture-resource-path-mismatch")

def parsePragmataMdf2Profile(data, path):
	if not path.lower().endswith(formats["PRAGMATA"]["mdfExt"]):
		raise MaterialProfileError("mdf2-suffix-mismatch")
	_materialCheckedRange(data, 0, 0x10, "mdf2-header")
	if data[0:4] != b"MDF\0":
		raise MaterialProfileError("mdf2-magic-mismatch")
	version = _materialScalar(data, 4, "<H", "mdf2-version")
	material_count = _materialScalar(data, 6, "<H", "material-count")
	if version != 1:
		raise MaterialProfileError("mdf2-version-mismatch")
	if material_count < 1:
		raise MaterialProfileError("material-count-mismatch")
	entries_end = 0x10 + material_count * MDF2_51_ENTRY_SIZE
	_materialCheckedRange(data, 0x10, material_count * MDF2_51_ENTRY_SIZE, "material-entries")
	entries = []
	for material_index in range(material_count):
		entry_offset = 0x10 + material_index * MDF2_51_ENTRY_SIZE
		entries.append({
			"index": material_index,
			"name_offset": _materialScalar(data, entry_offset, "<Q", "material-name"),
			"hash": _materialScalar(data, entry_offset + 0x08, "<I", "material-hash"),
			"property_data_size": _materialScalar(data, entry_offset + 0x0C, "<I", "property-data-size"),
			"property_count": _materialScalar(data, entry_offset + 0x10, "<I", "property-count"),
			"texture_count": _materialScalar(data, entry_offset + 0x14, "<I", "texture-count"),
			"gpu_name_count": _materialScalar(data, entry_offset + 0x18, "<I", "gpu-name-count"),
			"gpu_path_count": _materialScalar(data, entry_offset + 0x1C, "<I", "gpu-path-count"),
			"shader_type": _materialScalar(data, entry_offset + 0x20, "<I", "shader-type"),
			"alpha_flags_raw": _materialScalar(data, entry_offset + 0x28, "<I", "alpha-flags"),
			"property_table_offset": _materialScalar(data, entry_offset + 0x3C, "<Q", "property-table"),
			"texture_table_offset": _materialScalar(data, entry_offset + 0x44, "<Q", "texture-table"),
			"gpu_buffer_offset": _materialScalar(data, entry_offset + 0x4C, "<Q", "gpu-buffer-table"),
			"property_data_offset": _materialScalar(data, entry_offset + 0x54, "<Q", "property-data"),
			"master_material_offset": _materialScalar(data, entry_offset + 0x5C, "<Q", "master-material"),
			"trailing_raw": _materialScalar(data, entry_offset + 0x64, "<Q", "material-trailing"),
		})
	if material_count > 1 and entries[0]["texture_table_offset"] == 0x7C:
		raise MaterialProfileError("material-count-mismatch")
	# Cardinalities belong to each material, including single-material files.
	# Check the first table before its chain to retain useful truncation errors.
	_materialCheckedRange(data, entries[0]["texture_table_offset"], entries[0]["texture_count"] * MDF2_51_TEXTURE_ENTRY_SIZE, "texture-table")
	expected_offset = entries_end
	for entry in entries:
		if entry["texture_table_offset"] != expected_offset:
			raise MaterialProfileError("texture-table-chain-mismatch")
		_materialCheckedRange(data, expected_offset, entry["texture_count"] * MDF2_51_TEXTURE_ENTRY_SIZE, "texture-table")
		expected_offset += entry["texture_count"] * MDF2_51_TEXTURE_ENTRY_SIZE
	for entry in entries:
		if entry["property_table_offset"] != expected_offset:
			raise MaterialProfileError("property-table-chain-mismatch")
		_materialCheckedRange(data, expected_offset, entry["property_count"] * MDF2_51_PROPERTY_ENTRY_SIZE, "property-table")
		expected_offset += entry["property_count"] * MDF2_51_PROPERTY_ENTRY_SIZE
	# The optional GPBF block follows the property tables. Each binding has
	# two 16-byte records (UTF-16 pointer + opaque hash), name then resource.
	# Empty materials retain the block start; populated materials own consecutive
	# nonoverlapping slices. This is separate from the following string region.
	gpu_start = expected_offset
	for entry in entries:
		if entry["gpu_name_count"] != entry["gpu_path_count"]:
			raise MaterialProfileError("gpu-buffer-count-mismatch")
		count = entry["gpu_name_count"]
		if entry["gpu_buffer_offset"] != (expected_offset if count else gpu_start):
			raise MaterialProfileError("gpu-buffer-table-chain-mismatch")
		_materialCheckedRange(data, expected_offset, count * 32, "gpu-buffer-table")
		expected_offset += count * 32
	string_start = expected_offset
	for material_index in range(material_count - 1):
		entry = entries[material_index]
		if entry["property_data_offset"] + entry["property_data_size"] != entries[material_index + 1]["property_data_offset"]:
			raise MaterialProfileError("property-data-chain-mismatch")
	last_entry = entries[-1]
	if last_entry["property_data_offset"] + last_entry["property_data_size"] != len(data):
		raise MaterialProfileError("property-data-tail-mismatch")
	string_limit = entries[0]["property_data_offset"]
	if string_limit < string_start:
		raise MaterialProfileError("string-region-overlap")
	def materialString(offset, label):
		if offset < string_start:
			raise MaterialProfileError(label + "-string-region-overlap")
		return _materialUtf16z(data, offset, string_limit, label)
	materials = []
	seen_names = {}
	for entry in entries:
		_materialCheckedRange(data, entry["property_data_offset"], entry["property_data_size"], "property-data")
		material_name = materialString(entry["name_offset"], "material-name")
		if material_name in seen_names:
			raise MaterialProfileError("duplicate-material-name")
		seen_names[material_name] = True
		gpu_buffers = []
		for index in range(entry["gpu_name_count"]):
			name_offset, name_hash, path_offset, path_hash = struct.unpack_from(
				"<QQQQ", data, entry["gpu_buffer_offset"] + index * 32)
			gpu_buffers.append({
				"name": materialString(name_offset, "gpu-buffer-name"),
				"path": materialString(path_offset, "gpu-buffer-path"),
				"name_hash": name_hash, "path_hash": path_hash,
			})
		textures = []
		for texture_index in range(entry["texture_count"]):
			row_offset = entry["texture_table_offset"] + texture_index * MDF2_51_TEXTURE_ENTRY_SIZE
			slot_offset, texture_hash, texture_path_offset, reserved = struct.unpack_from("<QQQQ", data, row_offset)
			if reserved != 0:
				raise MaterialProfileError("texture-reserved-mismatch")
			slot = materialString(slot_offset, "texture-slot")
			semantic, confidence, preview_use = PRAGMATA_TEXTURE_SEMANTICS.get(slot, ("raw", "unverified", "raw-only"))
			textures.append({
				"index": texture_index,
				"slot": slot,
				"path": materialString(texture_path_offset, "texture-path"),
				"hash": texture_hash,
				"semantic": semantic,
				"confidence": confidence,
				"preview_use": preview_use,
			})
		properties = []
		for property_index in range(entry["property_count"]):
			row_offset = entry["property_table_offset"] + property_index * MDF2_51_PROPERTY_ENTRY_SIZE
			name_offset, name_hash, value_offset, value_count = struct.unpack_from("<QQII", data, row_offset)
			value_size = value_count * 4
			if value_count < 1 or value_offset + value_size > entry["property_data_size"]:
				raise MaterialProfileError("property-value-out-of-bounds")
			values = struct.unpack_from("<" + "f" * value_count, data, entry["property_data_offset"] + value_offset)
			if any(not math.isfinite(value) for value in values):
				raise MaterialProfileError("non-finite-material-property")
			properties.append({
				"index": property_index,
				"name": materialString(name_offset, "property-name"),
				"hash": name_hash,
				"value_offset": value_offset,
				"values": values,
			})
		materials.append({
			"index": entry["index"],
			"name": material_name,
			"hash": entry["hash"],
			"shader_type": entry["shader_type"],
			"alpha_flags_raw": entry["alpha_flags_raw"],
			"master_material": materialString(entry["master_material_offset"], "master-material"),
			"gpu_buffers": gpu_buffers,
			"textures": textures,
			"properties": properties,
			"layout": entry,
		})
	result = {
		"version": version,
		"material_count": material_count,
		"materials": materials,
		"texture_count": sum([entry["texture_count"] for entry in entries]),
		"property_count": sum([entry["property_count"] for entry in entries]),
	}
	if material_count == 1:
		material = materials[0]
		legacy_textures = []
		for texture in material["textures"]:
			legacy_textures.append({
				"index": texture["index"],
				"slot": texture["slot"],
				"path": texture["path"],
				"hash": texture["hash"],
			})
		target_texture = None
		for texture in legacy_textures:
			if texture["slot"] == "DeadFilament_MaskMap":
				if target_texture is not None:
					raise MaterialProfileError("target-texture-duplicate")
				target_texture = texture
		result.update({
			"material_name": material["name"],
			"material_hash": material["hash"],
			"shader_type": material["shader_type"],
			"alpha_flags_raw": material["alpha_flags_raw"],
			"master_material": material["master_material"],
			"textures": legacy_textures,
			"properties": material["properties"],
		})
		if target_texture is not None:
			result["target_texture"] = target_texture
	return result

def bindPragmataMaterialRecords(meshNames, materials):
	materialsByName = {}
	for material in materials:
		name = material.get("name")
		if name in materialsByName:
			raise MaterialProfileError("duplicate-material-name")
		materialsByName[name] = material
	ordered = []
	usedNames = {}
	for name in meshNames:
		if name not in materialsByName:
			raise MaterialProfileError("mesh-material-missing:" + str(name))
		ordered.append(materialsByName[name])
		usedNames[name] = True
	for material in materials:
		if material["name"] not in usedNames:
			raise MaterialProfileError("unused-mdf-material:" + material["name"])
	return ordered


def bind(runtime):
	def buildNoesisMaterial(record, textureNamesBySlot):
		material = _new_material(runtime.NoeMaterial, record["name"])
		for prop in record.get("properties", []):
			if prop.get("name") == "BaseColor" and len(prop.get("values", ())) >= 4:
				material.setDiffuseColor(list(prop["values"][:4]))
				break
		flags = 0
		hasDiffuse = False
		hasNormal = False
		hasEmissive = False
		for texture in record.get("textures", []):
			slot = texture.get("slot")
			textureName = textureNamesBySlot.get(slot)
			if not textureName:
				continue
			previewUse = texture.get("preview_use")
			semantic = texture.get("semantic")
			if previewUse == "diagnostic-diffuse" and not hasDiffuse:
				material.setTexture(textureName)
				hasDiffuse = True
			elif previewUse != "preview-mapping":
				continue
			elif semantic == "albedo" and not hasDiffuse:
				material.setTexture(textureName)
				hasDiffuse = True
			elif semantic in ("normal-roughness", "normal-roughness-cavity") and not hasNormal:
				material.setNormalTexture(textureName)
				flags |= getattr(runtime.noesis, "NMATFLAG_PBR_ROUGHNESS_NRMALPHA", 0)
				hasNormal = True
			elif semantic == "emissive" and not hasEmissive:
				emissivePass = runtime.NoeMaterial(record["name"] + "_emissive", textureName)
				emissivePass.setBlendMode("GL_ONE", "GL_ONE")
				emissivePass.setFlags(getattr(runtime.noesis, "NMATFLAG_BASICBLEND", 0))
				material.setNextPass(emissivePass)
				hasEmissive = True
		if flags:
			material.setFlags(flags)
		return material

	return (
		_materialCheckedRange,
		_materialScalar,
		_materialUtf16z,
		parsePragmataMdf2Profile,
		bindPragmataMaterialRecords,
		buildNoesisMaterial,
	)


"""Material loader implementation bound to one plugin runtime."""

import copy
import os
import re
from re_engine_types import (
	MaterialProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
MESH_RUNTIME_DEPENDENCIES = (
	'NoeBitStream',
	'NoeMat44',
	'NoeMaterial',
	'NoeTexture',
	'NoeVec4',
	'ReadUnicodeString',
	'SaveExtractedDir',
	'bColorize',
	'bPopupDebug',
	'bPrintFileList',
	'bPrintMDF',
	'bindPragmataMaterialRecords',
	'LoadExtractedDir',
	'dialogOptions',
	'extractedNativesPath',
	'generateDummyTexture4px',
	'invertRawRGBAChannel',
	'isImageBlank',
	'moveChannelsRGBA',
	'noesis',
	'parsePragmataMdf2Profile',
	'rapi',
	'sGameName',
	'texOutputExt',
)


def readLegacyMaterialEntry(bs, version, i, read_string):
	if version > 3:
		bs.seek(0x10 + (i * 100))
	elif version > 2:
		bs.seek(0x10 + (i * 80))
	else:
		bs.seek(0x10 + (i * 64))

	materialNamesOffset = bs.readUInt64()
	materialHash = bs.readInt()
	sizeOfFloatStr = bs.readUInt()
	floatCount = bs.readUInt()
	texCount = bs.readUInt()

	if version >= 3:
		bs.seek(8,1)

	shaderType = bs.readUInt()
	if version >= 4:
		uknSF6int = bs.readUInt()

	alphaFlag = bs.readUInt()

	if version >= 4:
		uknSF6int2 = bs.readUInt()
		uknSF6int3 = bs.readUInt()

	floatHdrOffs = bs.readUInt64()
	texHdrOffs = bs.readUInt64()
	if version >= 3:
		firstMtrlNameOffs = bs.readUInt64()
	floatStartOffs = bs.readUInt64()
	mmtr_PathOffs = bs.readUInt64()

	if version >= 4:
		uknSF6offset = bs.readUInt64()

	bs.seek(materialNamesOffset)
	materialName = read_string(bs)
	bs.seek(mmtr_PathOffs)
	mmtrName = read_string(bs).lower()
	return {
		"index": i, "name": materialName, "hash": materialHash,
		"shader_type": shaderType, "alpha_flags_raw": alphaFlag,
		"master_material": mmtrName, "property_count": floatCount,
		"texture_count": texCount, "property_table_offset": floatHdrOffs,
		"texture_table_offset": texHdrOffs, "property_data_offset": floatStartOffs,
	}


def readLegacyMaterialProperty(bs, version, entry, index, read_string):
	bs.seek(entry["property_table_offset"] + index * 0x18)
	row = [bs.readUInt64(), bs.readUInt64(), bs.readUInt(), bs.readUInt()]
	bs.seek(row[0])
	name = read_string(bs)
	offset, count = (row[2], row[3]) if version >= 2 else (row[3], row[2])
	bs.seek(entry["property_data_offset"] + offset)
	values = None
	if count == 4:
		values = (bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat())
	elif count == 1:
		values = (bs.readFloat(),)
	return {"name": name, "hash": row[1], "values": values}


def readLegacyMaterialTexture(bs, version, entry, index, read_string):
	if version >= 2:
		bs.seek(entry["texture_table_offset"] + index * 0x20)
		row = [bs.readUInt64(), bs.readUInt64(), bs.readUInt64(), bs.readUInt64()]
		if version >= 4:
			bs.seek(8, 1)
	else:
		bs.seek(entry["texture_table_offset"] + index * 0x18)
		row = [bs.readUInt64(), bs.readUInt64(), bs.readUInt64()]
	bs.seek(row[0])
	slot = read_string(bs)
	bs.seek(row[2])
	path = read_string(bs).replace("@", "")
	return {"slot": slot, "path": path, "hash": row[1]}


def selectMaterialTextureSlots(textures):
	"""Choose primary maps by MDF semantics before using filename hints.

	A missing primary resource stays missing; detail/blend/environment maps
	are not replacements for the surface's base color or tangent normal.
	"""
	primary = (
		("BaseDielectricMap", "BaseMetalMap", "BaseAlphaMap", "BaseShiftMap",
		 "BaseAnisoShiftMap", "BaseMap", "BaseDielectricMapBase",
		 "FaceBaseMap", "Face_BaseDielectricMap", "IrisBaseMap", "ScleraMap"),
		("NormalRoughnessMap", "NormalRoughnessCavityMap",
		 "NormalRoughnessTranslucentMap", "NRMR_NRRTMap", "NormalMap"),
	)
	result = []
	for slots, hint in zip(primary, ("_alb", "_nr")):
		explicit = [i for i, texture in enumerate(textures) if texture["slot"] in slots]
		if explicit:
			result.append(explicit[0])
			continue
		fallback = [i for i, texture in enumerate(textures)
			if hint in texture["path"].lower() and not any(word in texture["slot"].lower()
				for word in ("detail", "damage", "blend", "panorama", "ripple", "skin", "hair", "mask", "wrinkle"))]
		result.append(fallback[0] if fallback else None)
	return tuple(result)


def loadMeshMaterials(mesh, material_names=None, material_count=None):
	"""Select only the material component; its commit/error policy stays local."""
	family = mesh.importProfile["material"]["family"]
	if family == "mdf-45-legacy":
		return mesh.createMaterials(material_count if material_count is not None else len(material_names),
			materialNames=material_names)
	if family == "legacy":
		return mesh.createMaterials(material_count if material_count is not None else len(material_names))
	if family == "mdf-51-observed":
		names = material_names if material_names is not None else mesh.matNames
		return mesh.createMaterials(len(names), materialNames=names)
	raise MaterialProfileError("unsupported-material-import-family")


def bind_mesh_materials(runtime):
	def createMaterials(self, matCount, materialNames=None, decoder=None):
		# MDF51 keeps its validated records and transactional publication, but
		# uses the same lookup, texture conversion and Noesis builder as legacy.
		profile = getattr(self, "importProfile", None)
		if profile is None or profile["material"]["family"] != "mdf-51-observed":
			return _createMaterials(self, matCount, materialNames, decoder)
		staged = copy.copy(self)
		listFields = ("matList", "texList", "fullMatList", "fullTexList", "matNames",
			"matHashes", "texNames", "missingTexNames", "texColors")
		for field in listFields:
			setattr(staged, field, list(getattr(self, field, [])))
		staged.uvBias = dict(getattr(self, "uvBias", {}))
		try:
			staged.rootDir = _materialNativesRoot(self.path, profile["format"])[1]
			if hasattr(self, "gameName"):
				runtime.extractedNativesPath = runtime.LoadExtractedDir(self.gameName)
			result = _createMaterials(staged, matCount, materialNames, decoder)
		except MaterialProfileError as error:
			print("RE_MATERIAL_PROFILE_ERROR:" + str(error))
			return False
		if result:
			for field in listFields:
				if hasattr(self, field):
					getattr(self, field)[:] = getattr(staged, field)
				else:
					setattr(self, field, getattr(staged, field))
			self.uvBias = staged.uvBias
			self.materialProfile = staged.materialProfile
		return result

	def _createMaterials(self, matCount, materialNames=None, decoder=None):
		# Shared state is owned by runtime.

		doColorize = runtime.bColorize
		doPrintMDF = runtime.bPrintMDF
		noMDFFound = 0
		skipPrompt = 0

		import_profile = getattr(self, "importProfile", None)
		if import_profile is None:
			import_profile = composeImportProfile(runtime.sGameName, formats[runtime.sGameName])
		metadata = import_profile["format"]
		material_rules = import_profile["material"]
		modelExt = metadata["modelExt"]
		texExt = metadata["texExt"]
		mmtrExt = metadata["mmtrExt"]
		nDir = metadata["nDir"]
		mdfExt = metadata["mdfExt"]
		strictRecords = material_rules["family"] == "mdf-51-observed"

		if runtime.extractedNativesPath != "":
			print ("Using this extracted natives path:", runtime.extractedNativesPath + "\n")

		#Try to guess MDF filename
		inputName = self.path.lower() #rapi.getInputName()
		isSCN = (runtime.rapi.getInputName().lower().find(".scn") != -1)
		if inputName.find(".noesis") != -1:
			inputName = runtime.rapi.getLastCheckedName()
			skipPrompt = 2
			doPrintMDF = 0
		elif runtime.dialogOptions.doLoadTex or isSCN: # len(self.fullMatList) > 0 or len(self.fullBoneList) > 0:
			skipPrompt = 2
			doPrintMDF = 0

		pathPrefix = inputName
		while pathPrefix.find("out.") != -1:
			pathPrefix = pathPrefix.replace("out.",".")
		pathPrefix = pathPrefix.replace(".mesh", "").replace(modelExt,"").replace(".NEW", "")

		if material_rules["sibling_directory"] and os.path.isdir(os.path.dirname(inputName) + "\\" + material_rules["sibling_directory"]):
			pathPrefix = (os.path.dirname(inputName) + "\\Material\\" + runtime.rapi.getLocalFileName(inputName).replace("SK_", "M_")).replace(".NEW", "")
			while pathPrefix.find("out.") != -1:
				pathPrefix = pathPrefix.replace("out.",".")
			pathPrefix = pathPrefix.replace(".mesh" + modelExt,"")
			if not runtime.rapi.checkFileExists(pathPrefix + mdfExt):
				pathPrefix = pathPrefix.replace("00_", "")
			if not runtime.rapi.checkFileExists(pathPrefix + mdfExt):
				for item in os.listdir(os.path.dirname(pathPrefix + mdfExt)):
					if mdfExt == (".mdf2" + os.path.splitext(os.path.join(os.path.dirname(pathPrefix), item))[1]):
						pathPrefix = os.path.join(os.path.dirname(pathPrefix), item) #.replace(mdfExt, "")
						break

		similarityCounter = 0
		ogFileName = runtime.rapi.getLocalFileName(inputName)
		companion = findMaterialCompanionPath(
			pathPrefix + ".mesh" + modelExt, metadata, runtime.rapi.checkFileExists)
		if companion is not None:
			pathPrefix = companion[:-len(mdfExt)]
		if material_rules["family"] == "legacy" and not runtime.rapi.checkFileExists(pathPrefix + mdfExt):
			for item in os.listdir(os.path.dirname(pathPrefix + mdfExt)):
				if mdfExt == (".mdf2" + os.path.splitext(item)[1]):
					test = runtime.rapi.getLocalFileName(os.path.join(os.path.dirname(pathPrefix), item)).replace(mdfExt, "")
					sameCharCntr = 0
					for c, char in enumerate(test):
						if c < len(ogFileName) and char == ogFileName[c]:
							sameCharCntr += 1
					if sameCharCntr > similarityCounter:
						pathPrefix = os.path.join(os.path.dirname(pathPrefix), item).replace(mdfExt, "")
						similarityCounter = sameCharCntr
		materialFileName = pathPrefix + mdfExt

		if not (runtime.rapi.checkFileExists(materialFileName)):
			print(materialFileName, "does not exist!")
			materialFileName = (pathPrefix + "_mat" + mdfExt)
		if not (runtime.rapi.checkFileExists(materialFileName)):
			materialFileName = (pathPrefix + "_00" + mdfExt)
		if not (runtime.rapi.checkFileExists(materialFileName)):
			companion = findMaterialCompanionPath(
				inputName, metadata, runtime.rapi.checkFileExists,
				[runtime.extractedNativesPath])
			if companion is not None:
				materialFileName = companion
		if not runtime.rapi.checkFileExists(materialFileName):
			try:
				linked = findLinkedMaterialPath(inputName, metadata, [runtime.extractedNativesPath])
			except MaterialProfileError as error:
				print("RE_MATERIAL_PROFILE_ERROR:" + str(error))
				return False
			if linked is not None:
				materialFileName = linked

		if material_rules["family"] in ("mdf-45-legacy", "mdf-51-observed") and (
				runtime.noesis.optWasInvoked("-b") or runtime.noesis.optWasInvoked("-noprompt")):
			if not runtime.rapi.checkFileExists(materialFileName):
				print("No material file.")
				return False
			skipPrompt = 2

		if not (runtime.rapi.checkFileExists(materialFileName)):
			materialFileName = runtime.noesis.userPrompt(runtime.noesis.NOEUSERVAL_FILEPATH, "MDF File Not Found", "Manually enter the name of the MDF file or cancel.", os.path.join(os.path.dirname(inputName), runtime.rapi.getLocalFileName(materialFileName)) , None)
			if (materialFileName is None):
				print("No material file.")
				return
			elif not (runtime.rapi.checkFileExists(materialFileName)):
				noMDFFound = 1
			skipPrompt = 1

		msgName = materialFileName

		#Prompt for MDF load
		if not skipPrompt or (skipPrompt == 2 and not runtime.rapi.checkFileExists(materialFileName)):
			msgName = runtime.noesis.userPrompt(runtime.noesis.NOEUSERVAL_FILEPATH, "MDF File Detected", "Load materials? This may take some time.", materialFileName, None)
			if msgName is None:
				print("No material file.")
				return False

			'''if msgName.endswith(" -c"):
				print (msgName)
				doColorize = 1
				doPrintMDF = 0
				msgName = msgName.replace(" -c", "")'''

			if ((runtime.rapi.checkFileExists(msgName)) and (msgName.endswith(mdfExt))):
				materialFileName = msgName
			else:
				noMDFFound = 1

		if (runtime.bPopupDebug == 1):
			runtime.noesis.logPopup()

		#Save a manually entered natives directory path name for later
		if (msgName.endswith("\\natives\\" + nDir + "\\")) and (os.path.isdir(msgName)):
			print ("Attempting to write: ")
			if runtime.SaveExtractedDir(msgName, runtime.sGameName):
				runtime.extractedNativesPath = msgName

		if (noMDFFound == 1) or not (runtime.rapi.checkFileExists(materialFileName)):
			print("Failed to open material file.")
			return False

		texBaseColour = []
		texRoughColour = []
		texSpecColour = []
		texAmbiColour = []
		texMetallicColour = []
		texFresnelColour = []

		bs = runtime.rapi.loadIntoByteArray(materialFileName)
		profile = None
		if strictRecords:
			profile = runtime.parsePragmataMdf2Profile(bs, materialFileName)
			records = runtime.bindPragmataMaterialRecords(materialNames, profile["materials"])
			# Validate all referenced paths, including textures not selected for
			# basic preview, before publishing or loading external resources.
			for record in records:
				for texture in record["textures"]:
					resolveTextureResourcePath(self.path, texture["path"], metadata)
			profile["bound_material_names"] = [record["name"] for record in records]
			self.materialProfile = profile
		if material_rules["family"] == "mdf-45-legacy":
			validateWildsMdfProfile(bs, materialFileName)
		if strictRecords:
			matCountMDF = len(records)
		else:
			bs = runtime.NoeBitStream(bs)
			#Magic, Unknown, MaterialCount, Unknown, Unknown
			matHeader = [bs.readUInt(), bs.readUShort(), bs.readUShort(), bs.readUInt(), bs.readUInt()]
			matCountMDF = matHeader[2]
			if material_rules["family"] == "mdf-45-legacy" and materialNames is not None:
				mdfNames = [readLegacyMaterialEntry(bs, self.mdfVer, index,
					runtime.ReadUnicodeString)["name"] for index in range(matCountMDF)]
				if len(set(mdfNames)) != len(mdfNames) or set(mdfNames) != set(materialNames):
					raise MaterialProfileError("mesh-material-names-mismatch")

		if matCountMDF != matCount and len(self.fullMatList) == 0:
			print ("MDF Checkerboard Error: MDF does not have the same material count as the MESH file!\n	MESH materials:", matCount, "\n	MDF Materials:", matCountMDF)
			return 0

		usedMats = [mat.name for mat in self.fullMatList]
		usedTexs = [tex.name for tex in self.fullTexList]
		textureBindings = {}

		#Parse Materials
		for i in range(matCountMDF):

			record = records[i] if strictRecords else readLegacyMaterialEntry(bs, self.mdfVer, i, runtime.ReadUnicodeString)
			materialName = record["name"]
			materialHash = record["hash"]
			mmtrName = record["master_material"]
			floatCount = len(record["properties"]) if strictRecords else record["property_count"]
			texCount = len(record["textures"]) if strictRecords else record["texture_count"]
			textures = (record["textures"] if strictRecords else [
				readLegacyMaterialTexture(bs, self.mdfVer, record, index, runtime.ReadUnicodeString)
				for index in range(texCount)])
			#hasTransparency = not not (((alphaFlag & ( 1 << 1 )) >> 1) or ((alphaFlag & ( 1 << 4 )) >> 4))
			hasTransparency = "_dirt" in mmtrName or "_decal" in mmtrName or "_hair" in mmtrName
			isEnvAlphaTest = mmtrName.replace("\\", "/").rsplit("/", 1)[-1].lower() == "env_alphatest.mmtr"
			isMdfAlphaTest = (material_rules["family"] == "mdf-45-legacy" and
				bool(record.get("alpha_flags_raw", 0) & 2) and
				any("AlphaTranslucent" in texture["slot"] for texture in textures))
			hasTransparency = hasTransparency or isEnvAlphaTest or isMdfAlphaTest
			alphaTestRef = 0.05

			if runtime.bPrintFileList:
				self.texNames.append(("natives/" + nDir + "/" + mmtrName + mmtrExt).lower())
				if not runtime.rapi.checkFileExists(runtime.extractedNativesPath + (mmtrName + mmtrExt).lower()) and not runtime.rapi.checkFileExists(self.rootDir + (mmtrName + mmtrExt).lower()) and runtime.rapi.getInputName().find("natives".lower()) != -1:
					self.missingTexNames.append("DOES NOT EXIST " + ("natives/" + nDir + "/" + mmtrName + mmtrExt).lower())

			if doPrintMDF:
				print(materialName + "[" + str(i) + "]\n")

			self.matNames.append(materialName)
			self.matHashes.append(materialHash)
			materialFlags = 0
			materialFlags2 = 0
			material = _new_material(runtime.NoeMaterial, materialName)
			#material.setBlendMode("GL_ONE", "GL_ONE")

			#Parse Textures

			bFoundBM = False
			bFoundNM = False
			bFoundSSSM = False
			bFoundEmissive = False
			emissiveEnabled = True

			bFoundBaseColour = False
			bFoundRoughColour = False
			bFoundSpecColour = False
			bFoundAmbiColour = False
			bFoundMetallicColour = False
			bFoundFresnelColour = False

			if doPrintMDF:
				print ("Material Properties:")

			for j in range(floatCount): # floats
				propertyRecord = record["properties"][j] if strictRecords else readLegacyMaterialProperty(bs, self.mdfVer, record, j, runtime.ReadUnicodeString)
				paramType = propertyRecord["name"]
				values = propertyRecord["values"]
				colours = (runtime.NoeVec4(values) if len(values) == 4 else values[0]) if values is not None else None

				if doPrintMDF:
					print(paramType + ":", colours)

				if paramType == "BaseColor" and not bFoundBaseColour:
					bFoundBaseColour = True
					texBaseColour.append(colours)
				if paramType == "Roughness" and not bFoundRoughColour:
					bFoundRoughColour = True
					texRoughColour.append(colours)
				if paramType == "PrimalySpecularColor" and not bFoundSpecColour:
					bFoundSpecColour = True
					texSpecColour.append(colours)
				if paramType == "AmbientColor" and not bFoundAmbiColour:
					bFoundAmbiColour = True
					texAmbiColour.append(colours)
				if paramType == "Metallic" and not bFoundMetallicColour:
					bFoundMetallicColour = True
					texMetallicColour.append(colours)
				if paramType == "Fresnel_DiffuseIntensity" and not bFoundFresnelColour:
					bFoundFresnelColour = True
					texFresnelColour.append(colours)
				if paramType == "Occlusion_UseSecondaryUV" and colours != 0:
					materialFlags2 |= runtime.noesis.NMATFLAG2_OCCL_UV1
				if paramType == "Emissive_Intensity" and colours == 0:
					# A default white map is also used by explicitly disabled emission.
					emissiveEnabled = False
				if (((isEnvAlphaTest and paramType == "AlphaTestRef") or
						(isMdfAlphaTest and paramType == "AlphaTest_Ref")) and
						values is not None and len(values) == 1 and
						0.0 <= values[0] <= 1.0):
					alphaTestRef = values[0]

			#Append defaults
			if not bFoundBaseColour:
				texBaseColour.append(runtime.NoeVec4((1.0, 1.0, 1.0, 1.0)))
			if not bFoundRoughColour:
				texRoughColour.append(1.0)
			if not bFoundSpecColour:
				texSpecColour.append(runtime.NoeVec4((0.5, 0.5, 0.5, 0.5)))
			if not bFoundAmbiColour:
				texAmbiColour.append(runtime.NoeVec4((1.0, 1.0, 1.0, 1.0)))
			if not bFoundMetallicColour:
				texMetallicColour.append(1.0)
			if not bFoundFresnelColour:
				texFresnelColour.append(0.8)

			if doPrintMDF:
				print ("\nTextures for " + materialName + "[" + str(i) + "]" + ":")

			alreadyLoadedTexs = [tex.name for tex in self.fullTexList + self.texList]
			alreadyLoadedMats = [mat.name for mat in self.fullMatList]
			secondaryDiffuse = ""
			useSlotSelection = material_rules["family"] == "mdf-45-legacy"
			diffuseSlot, normalSlot = selectMaterialTextureSlots(textures) if useSlotSelection else (None, None)
			if profile and profile.get("target_texture"):
				diffuseSlot = next((index for index, texture in enumerate(textures)
					if texture["slot"] == profile["target_texture"]["slot"]), diffuseSlot)

			for j in range(texCount): # texture headers

				textureRecord = textures[j]
				textureType = textureRecord["slot"]
				textureName = textureRecord["path"]
				# Preserve the frozen single-material diagnostic as a fallback;
				# it is not a game shader or a general mask-to-albedo rule.
				if profile and profile.get("target_texture", {}).get("slot") == textureType:
					textureType = "BaseMap"
				if material_rules["family"] == "mdf-45-legacy":
					resolveTextureResourcePath(self.path, textureName, metadata)

				textureFilePath = ""
				texName = ""
				isNotMainTexture = False
				opacityName = ""
				extraParam = ""

				if bFoundBaseColour:
					material.setDiffuseColor(texBaseColour[i])
				if bFoundSpecColour:
					material.setSpecularColor(texSpecColour[i])
				if bFoundAmbiColour:
					material.setAmbientColor(texAmbiColour[i])
				if bFoundMetallicColour:
					material.setMetal(texMetallicColour[i], 0.25)
				if bFoundRoughColour:
					material.setRoughness(texRoughColour[i], 0.25)
				if bFoundFresnelColour:
					material.setEnvColor(runtime.NoeVec4((1.0, 1.0, 1.0, texFresnelColour[i])))

				tmpExt = texExt
				for k in range(2):
					if not runtime.rapi.checkFileExists(textureFilePath):
						if (runtime.rapi.checkFileExists(self.rootDir + "streaming/" + textureName + tmpExt)):
							textureFilePath = self.rootDir + "streaming/" + textureName + tmpExt
							texName = runtime.rapi.getLocalFileName(self.rootDir + "streaming/" + textureName).rsplit('.', 1)[0] + runtime.texOutputExt

						elif (runtime.rapi.checkFileExists(self.rootDir + textureName + tmpExt)):
							textureFilePath = self.rootDir + textureName + tmpExt
							texName = runtime.rapi.getLocalFileName(self.rootDir + textureName).rsplit('.', 1)[0] + runtime.texOutputExt
							if runtime.bPrintFileList and not (runtime.rapi.checkFileExists(self.rootDir + textureName + tmpExt)):
								self.missingTexNames.append("DOES NOT EXIST: " + (('natives/' + (re.sub(r'.*natives\\', '', textureFilePath)).lower()).replace("\\","/")).replace(runtime.extractedNativesPath,''))

						elif (runtime.rapi.checkFileExists(runtime.extractedNativesPath + "streaming/" + textureName + tmpExt)):
							textureFilePath = runtime.extractedNativesPath + "streaming/" + textureName + tmpExt
							texName = runtime.rapi.getLocalFileName(runtime.extractedNativesPath + "streaming/" + textureName).rsplit('.', 1)[0] + runtime.texOutputExt

						elif (runtime.rapi.checkFileExists(runtime.extractedNativesPath + textureName + tmpExt)):
							textureFilePath = runtime.extractedNativesPath + textureName + tmpExt
							texName = runtime.rapi.getLocalFileName(runtime.extractedNativesPath + textureName).rsplit('.', 1)[0] + runtime.texOutputExt
							if runtime.bPrintFileList and not (runtime.rapi.checkFileExists(runtime.extractedNativesPath + textureName + tmpExt)):
								self.missingTexNames.append("DOES NOT EXIST: " + ('natives/' + (re.sub(r'.*natives\\', '', textureFilePath)).lower()).replace("\\","/").replace(runtime.extractedNativesPath,''))

						else:
							textureFilePath = self.rootDir + textureName + tmpExt
							texName = runtime.rapi.getLocalFileName(self.rootDir + textureName).rsplit('.', 1)[0] + runtime.texOutputExt
							if runtime.bPrintFileList and not (textureFilePath.endswith("rtex" + tmpExt)) and (k==1 or not material_rules["stm_retry"]):
								self.missingTexNames.append("DOES NOT EXIST: " + ('natives/' + (re.sub(r'.*natives\\', '', textureFilePath)).lower()).replace("\\","/").replace("streaming/",""))
						if not material_rules["stm_retry"]:
							break
						tmpExt += ".stm"

				bAlreadyLoadedTexture = (texName in alreadyLoadedTexs)
				bAlreadyLoadedMat = (materialName in alreadyLoadedMats)

				if runtime.bPrintFileList: #and rapi.getInputName().find("natives".lower()) != -1:
					if not (textureName.endswith("rtex")):
						newTexPath = ((('natives/' + (re.sub(r'.*natives\\', '', textureFilePath))).replace("\\","/")).replace(runtime.extractedNativesPath,'')).lower()
						self.texNames.append(newTexPath)
						if newTexPath.find('streaming') != -1:
							testPath = newTexPath.replace('natives/' + nDir + '/streaming/', '')
							if runtime.rapi.checkFileExists(self.rootDir + testPath) or runtime.rapi.checkFileExists(runtime.extractedNativesPath + testPath):
								self.texNames.append(newTexPath.replace('streaming/',''))

				lowerTexName = texName.lower()
				if not runtime.rapi.checkFileExists(textureFilePath) and not textureName.endswith("rtex"):
					print("Error: Texture at path: " + str(textureFilePath) + " does not exist!")
					if profile and profile.get("target_texture", {}).get("slot") == textureRecord["slot"]:
						raise MaterialProfileError("tex-companion-missing")
					continue
				#if (("BaseMetal" in textureType or "BaseDielectric" in textureType or "BaseAlpha" in textureType or "BaseShift" in textureType)) and not bFoundBM: #
				if ((useSlotSelection and j == diffuseSlot) or (not useSlotSelection and
						"_alb" in lowerTexName and (not bFoundBM or "_albd" in lowerTexName))):
					bFoundBM = True
					material.setTexture(texName)
					material.setSpecularColor([.25, .25, .25, 1])
					if "AlphaMap" in textureType:
						extraParam = "isALBA"
					if "Metal" in textureType:
						extraParam = "isALBM"
					if "Dielectric" in textureType:
						extraParam = "isALBD"
					self.uvBias[material.name] = [0.5, 0.5] if material_rules["atlas_uv"] and "atlas" in lowerTexName else 1.0
				#elif (("Normal" in textureType or "NR" in textureType) or "_nr" in lowerTexName) and not bFoundNM:
				elif not bFoundNM and ((useSlotSelection and j == normalSlot) or
						(not useSlotSelection and "_nr" in lowerTexName)):
					bFoundNM = True
					material.setNormalTexture(texName)
					extraParam = "isNRM"
					if textureType == "NormalRoughnessMap":
						materialFlags |= runtime.noesis.NMATFLAG_PBR_ROUGHNESS_NRMALPHA
					if "NRR" in textureType or textureType == "NormalRoughnessTranslucentMap" or textureType == "NormalRoughnessCavityMap":
						extraParam = "isNRR"
				elif "AlphaTranslucent" in textureType and not bFoundSSSM:
					bFoundSSSM = True
					material.setOcclTexture(texName.replace(runtime.texOutputExt,  "_NoesisAO" + runtime.texOutputExt))
					extraParam = "isATOS_Alpha" if hasTransparency else "isATOS"
					material.setOcclTexture(texName.replace(runtime.texOutputExt,  "_NoesisAO" + runtime.texOutputExt))
				elif textureType == "AlphaMap":
					opacityName = texName
				#elif "_lymo" in lowerTexName:
				#	extraParam = "isLYMO"
				elif textureType == "EmissiveMap" and emissiveEnabled and not bFoundEmissive:
					emissivePass = runtime.NoeMaterial(materialName + "_emissive", texName)
					emissivePass.setBlendMode("GL_ONE", "GL_ONE")
					emissivePass.setFlags(runtime.noesis.NMATFLAG_BASICBLEND)
					material.setNextPass(emissivePass)
					bFoundEmissive = True
				elif not useSlotSelection and (re.search("^Base.*Map$", textureType) or textureType in ("IrisBaseMap", "ScleraMap")) and not secondaryDiffuse:
				#elif ("_alb" in lowerTexName) and not secondaryDiffuse:
					secondaryDiffuse = texName
				elif not runtime.dialogOptions.loadAllTextures:
					isNotMainTexture = True

				bindingKey = (texName, extraParam)
				if bAlreadyLoadedTexture and bindingKey not in textureBindings:
					# An earlier import/other interpretation has no reusable conversion
					# recipe here. Re-read rather than omit this material's bindings.
					bAlreadyLoadedTexture = False
				if not bAlreadyLoadedTexture and not isNotMainTexture:
					if (textureName.endswith("rtex")):
						pass
					elif not (runtime.rapi.checkFileExists(textureFilePath)):
						if textureFilePath != "":
							print("Error: Texture at path: " + str(textureFilePath) + " does not exist!")
					else:
						textureData = runtime.rapi.loadIntoByteArray(textureFilePath)
						numTex = len(self.texList)
						noetex = texture_import.loadTextureForImport(runtime, textureData, self.texList, texName, textureFilePath, import_profile["texture"], decoder)
						if noetex:
							bindingCalls = []
							conversionFlags = 0
							def bindConverted(method, *args):
								bindingCalls.append((method, args))
								getattr(material, method)(*args)
							if runtime.dialogOptions.doConvertTex:
								if "isALBM"  == extraParam or "isALBD" == extraParam:
									if "isALBD" == extraParam:
										noetex.pixelData = runtime.invertRawRGBAChannel(noetex.pixelData, 3)
									conversionFlags |= runtime.noesis.NMATFLAG_PBR_METAL
									if runtime.dialogOptions.doConvertMatsForBlender:
										metalTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "a8a8a8")
										metalTexData = runtime.rapi.imageDecodeRaw(metalTexData, noetex.width, noetex.height, "r8g8b8")
										noetex.pixelData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8g8b8")
										noetex.pixelData = runtime.rapi.imageDecodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8g8b8")
										if not runtime.isImageBlank(metalTexData, noetex.width, noetex.height, 4):
											metalTexName = texName.replace(runtime.texOutputExt,  "_NoesisMET" + runtime.texOutputExt)
											bindConverted("setSpecularTexture", metalTexName)
											self.texList.append(runtime.NoeTexture(metalTexName, noetex.width, noetex.height, metalTexData, runtime.noesis.NOESISTEX_RGBA32))
									else:
										bindConverted("setSpecularTexture", texName)
										bindConverted("setSpecularSwizzle",  runtime.NoeMat44([[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]])) #move alpha channel to green channel
								if runtime.dialogOptions.doConvertMatsForBlender and ("isNRM" == extraParam or "isNRR" in extraParam):
									roughnessTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "a8a8a8" if "isNRM" == extraParam else "r8r8r8")
									roughnessTexData = runtime.rapi.imageDecodeRaw(roughnessTexData, noetex.width, noetex.height, "r8g8b8")
									if not runtime.isImageBlank(roughnessTexData, noetex.width, noetex.height, 4):
										roughnessTexName = texName.replace(runtime.texOutputExt,  "_NoesisRGH" + runtime.texOutputExt)
										self.texList.append(runtime.NoeTexture(roughnessTexName, noetex.width, noetex.height, roughnessTexData, runtime.noesis.NOESISTEX_RGBA32))
										bindConverted("setBumpTexture", roughnessTexName)
								if "isNRR" in extraParam:
									noetex.pixelData = runtime.rapi.imageSwapChannelRGBA32(noetex.pixelData, 3, 0)
									#noetex.pixelData = rapi.imageNormalSwizzle(noetex.pixelData, noetex.width, noetex.height, 1, 0, 0)
									#noetex.pixelData = moveChannelsRGBA(noetex.pixelData, 3, noetex.width, noetex.height, noetex.pixelData, [0], noetex.width, noetex.height)
									noetex.pixelData = runtime.moveChannelsRGBA(noetex.pixelData, -2, noetex.width, noetex.height, noetex.pixelData, [2,3], noetex.width, noetex.height)
									#noetex.pixelData = invertRawRGBAChannel(noetex.pixelData, 1)
								if "isALBA" == extraParam:
									opacityTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "a8a8a8")
									opacityTexData = runtime.rapi.imageDecodeRaw(opacityTexData, noetex.width, noetex.height, "r8g8b8")
									opacityName = texName.replace(runtime.texOutputExt,  "_NoesisAlpha" + runtime.texOutputExt)
									self.texList.append(runtime.NoeTexture(opacityName, noetex.width, noetex.height, opacityTexData, runtime.noesis.NOESISTEX_RGBA32))
								if "isLYMO" == extraParam:
									#r=metal? g= b=roughness? a=ao?
									conversionFlags |= runtime.noesis.NMATFLAG_PBR_METAL
									metalTexName = texName.replace(runtime.texOutputExt,  "_NoesisMET" + runtime.texOutputExt)
									metalTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8r8r8")
									metalTexData = runtime.rapi.imageDecodeRaw(metalTexData, noetex.width, noetex.height, "r8g8b8")
									bindConverted("setSpecularTexture", metalTexName)
									self.texList.append(runtime.NoeTexture(metalTexName, noetex.width, noetex.height, metalTexData, runtime.noesis.NOESISTEX_RGBA32))
									if runtime.dialogOptions.doConvertMatsForBlender:
										roughnessTexName = texName.replace(runtime.texOutputExt,  "_NoesisRGH" + runtime.texOutputExt)
										roughnessTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "b8b8b8")
										roughnessTexData = runtime.rapi.imageDecodeRaw(roughnessTexData, noetex.width, noetex.height, "r8g8b8")
										self.texList.append(runtime.NoeTexture(roughnessTexName, noetex.width, noetex.height, roughnessTexData, runtime.noesis.NOESISTEX_RGBA32))
										bindConverted("setBumpTexture", roughnessTexName)
									noetex.pixelData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "a8a8a8")
									noetex.pixelData = runtime.rapi.imageDecodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8g8b8")
									bindConverted("setOcclTexture", noetex.name)

								if "isATOS" in extraParam:
									imgData = copy.copy(noetex.pixelData)
									aoTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "b8b8b8")
									aoTexData = runtime.rapi.imageDecodeRaw(aoTexData, noetex.width, noetex.height, "r8g8b8")
									if not runtime.isImageBlank(aoTexData, noetex.width, noetex.height):
										noetex.name = texName.replace(runtime.texOutputExt,  "_NoesisAO" + runtime.texOutputExt)
										self.texList[len(self.texList)-1].pixelData = aoTexData
									else:
										self.texList.remove(noetex)
										bindConverted("setOcclTexture", "")
									if extraParam == "isATOS_Alpha" and not opacityName:
										opacityTexData = runtime.rapi.imageEncodeRaw(imgData, noetex.width, noetex.height, "r8r8r8")
										opacityTexData = runtime.rapi.imageDecodeRaw(opacityTexData, noetex.width, noetex.height, "r8g8b8")
										if not runtime.isImageBlank(opacityTexData, noetex.width, noetex.height):
											opacityName = texName.replace(runtime.texOutputExt,  "_NoesisAlpha" + runtime.texOutputExt)
											self.texList.append(runtime.NoeTexture(opacityName, noetex.width, noetex.height, opacityTexData, runtime.noesis.NOESISTEX_RGBA32))
							materialFlags |= conversionFlags
							textureBindings[bindingKey] = (conversionFlags, bindingCalls, opacityName)
							alreadyLoadedTexs.append(texName)
						else:
							if strictRecords:
								raise MaterialProfileError("tex-decode-failed")
							print ("Failed to load", texName)

				if bAlreadyLoadedTexture and bindingKey in textureBindings:
					flags, bindingCalls, opacityName = textureBindings[bindingKey]
					materialFlags |= flags
					for method, args in bindingCalls:
						getattr(material, method)(*args)

				if opacityName and hasTransparency:
					if extraParam == "isATOS_Alpha" and (
							not isMdfAlphaTest or record["alpha_flags_raw"] & 1):
						materialFlags |= runtime.noesis.NMATFLAG_TWOSIDED
					material.setAlphaTest(alphaTestRef)
					material.setOpacityTexture(opacityName)
					if runtime.dialogOptions.doConvertMatsForBlender:
						material.setEnvTexture(opacityName)


				if doPrintMDF:
					print(textureType + ":\n    " + textureName)

			if secondaryDiffuse and not bFoundBM:
				material.setTexture(secondaryDiffuse)
				material.setSpecularColor([.25, .25, .25, 1])
				bFoundBM = True

			if texCount:
				if not bFoundBM:
					dummyTexName = textureName.replace(runtime.texOutputExt, "_NoesisColor" + runtime.texOutputExt)
					material.setTexture(dummyTexName)
					if dummyTexName not in alreadyLoadedTexs:
						try:
							byteColor = [int((1 if color > 1.0 else 0 if color < 0.0 else color) * 255) for color in texBaseColour[i]]
						except:
							byteColor = [127, 127, 127, 255]
						self.texList.append(runtime.generateDummyTexture4px(byteColor, dummyTexName))
						alreadyLoadedTexs.append(dummyTexName)
				if not bFoundNM:
					material.setNormalTexture("NoesisNRM" + runtime.texOutputExt)
					if "NoesisNRM" + runtime.texOutputExt not in alreadyLoadedTexs:
						self.texList.append(runtime.generateDummyTexture4px((127, 127, 255, 255), "NoesisNRM" + runtime.texOutputExt))
						alreadyLoadedTexs.append("NoesisNRM" + runtime.texOutputExt)

			material.setFlags(materialFlags)
			material.setFlags2(materialFlags2)
			self.matList.append(material)

			lowername = material.name.lower()
			if ("eye" in lowername and not material.texName) or "tearline" in lowername or "lens" in lowername or "destroy" in lowername: #"ao" in lowername or "out" in lowername or
				material.setSkipRender(True)

			if doPrintMDF:
				print("--------------------------------------------------------------------------------------------\n")

		if runtime.bPrintFileList:
			if len(self.texNames) > 0:
				print ("\nReferenced Files:")
				textureList = sorted(list(set(self.texNames)))
				for x in range (len(textureList)):
					print (textureList[x])
				print ("")

			if len(self.missingTexNames) > 0:
				print ("Missing Files:")
				missingTextureList = sorted(list(set(self.missingTexNames)))
				for x in range (len(missingTextureList)):
					print (missingTextureList[x])
				print ("")

		if doColorize:
			colorList = sorted(list(set(self.texColors)))
			print ("Color-coded Materials:")
			for g in range (len(colorList)):
				print (colorList[g])
			print ("")

		for mat in self.matList:
			if mat.name not in usedMats:
				usedMats.append(mat.name)
				self.fullMatList.append(mat)
		for tex in self.texList:
			if tex.name not in usedTexs:
				usedTexs.append(tex.name)
				self.fullTexList.append(tex)

		return True

	def _loadPragmataMaterialProfile(self, meshMaterialNames, pragmataDecoder=None):
		# Compatibility entry point for existing callers; no separate renderer.
		if not hasattr(self, "importProfile"):
			self.importProfile = composeImportProfile("PRAGMATA", formats["PRAGMATA"])
		return createMaterials(self, len(meshMaterialNames), meshMaterialNames, pragmataDecoder)

	return (
		createMaterials,
		_loadPragmataMaterialProfile,
	)
