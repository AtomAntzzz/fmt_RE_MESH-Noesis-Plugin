"""Materials implementation bound to one plugin runtime."""

import re_engine_common as re_common
import struct
from re_engine_config import (
	MDF2_51_EXACT_TEXTURE_COUNT,
	MDF2_51_EXACT_PROPERTY_COUNT,
	formats,
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


def _materialCheckedRange(data, start, size, label):
	def materialRangeError(token):
		prefix = "offset-out-of-bounds:"
		if token.startswith(prefix):
			token = token[len(prefix):] + "-out-of-bounds"
		return MaterialProfileError(token)
	return re_common.checked_range(data, start, size, label, materialRangeError)

def _materialScalar(data, offset, fmt, label):
	_materialCheckedRange(data, offset, struct.calcsize(fmt), label)
	return re_common.read_scalar(data, offset, fmt, label, MaterialProfileError)

def _materialUtf16z(data, offset, limit, label):
	return re_common.read_utf16z(
		data, offset, limit, label, MaterialProfileError)

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
			"shader_type": _materialScalar(data, entry_offset + 0x20, "<I", "shader-type"),
			"alpha_flags_raw": _materialScalar(data, entry_offset + 0x28, "<I", "alpha-flags"),
			"property_table_offset": _materialScalar(data, entry_offset + 0x3C, "<Q", "property-table"),
			"texture_table_offset": _materialScalar(data, entry_offset + 0x44, "<Q", "texture-table"),
			"first_material_name_offset": _materialScalar(data, entry_offset + 0x4C, "<Q", "first-material-name"),
			"property_data_offset": _materialScalar(data, entry_offset + 0x54, "<Q", "property-data"),
			"master_material_offset": _materialScalar(data, entry_offset + 0x5C, "<Q", "master-material"),
			"trailing_raw": _materialScalar(data, entry_offset + 0x64, "<Q", "material-trailing"),
		})
	if material_count > 1 and entries[0]["texture_table_offset"] == 0x7C:
		raise MaterialProfileError("material-count-mismatch")
	if material_count == 1:
		if entries[0]["texture_count"] != MDF2_51_EXACT_TEXTURE_COUNT:
			raise MaterialProfileError("texture-count-mismatch")
		if entries[0]["property_count"] != MDF2_51_EXACT_PROPERTY_COUNT:
			raise MaterialProfileError("property-count-mismatch")
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
	string_start = expected_offset
	for entry in entries:
		if entry["first_material_name_offset"] != string_start:
			raise MaterialProfileError("first-material-name-mismatch")
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
	materials = []
	seen_names = {}
	for entry in entries:
		_materialCheckedRange(data, entry["property_data_offset"], entry["property_data_size"], "property-data")
		material_name = _materialUtf16z(data, entry["name_offset"], string_limit, "material-name")
		if material_name in seen_names:
			raise MaterialProfileError("duplicate-material-name")
		seen_names[material_name] = True
		textures = []
		for texture_index in range(entry["texture_count"]):
			row_offset = entry["texture_table_offset"] + texture_index * MDF2_51_TEXTURE_ENTRY_SIZE
			slot_offset, texture_hash, texture_path_offset, reserved = struct.unpack_from("<QQQQ", data, row_offset)
			if reserved != 0:
				raise MaterialProfileError("texture-reserved-mismatch")
			slot = _materialUtf16z(data, slot_offset, string_limit, "texture-slot")
			semantic, confidence, preview_use = PRAGMATA_TEXTURE_SEMANTICS.get(slot, ("raw", "unverified", "raw-only"))
			textures.append({
				"index": texture_index,
				"slot": slot,
				"path": _materialUtf16z(data, texture_path_offset, string_limit, "texture-path"),
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
			properties.append({
				"index": property_index,
				"name": _materialUtf16z(data, name_offset, string_limit, "property-name"),
				"hash": name_hash,
				"value_offset": value_offset,
				"values": struct.unpack_from("<" + "f" * value_count, data, entry["property_data_offset"] + value_offset),
			})
		materials.append({
			"index": entry["index"],
			"name": material_name,
			"hash": entry["hash"],
			"shader_type": entry["shader_type"],
			"alpha_flags_raw": entry["alpha_flags_raw"],
			"master_material": _materialUtf16z(data, entry["master_material_offset"], string_limit, "master-material"),
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
		if len(material["textures"]) != MDF2_51_EXACT_TEXTURE_COUNT:
			raise MaterialProfileError("texture-count-mismatch")
		if len(material["properties"]) != MDF2_51_EXACT_PROPERTY_COUNT:
			raise MaterialProfileError("property-count-mismatch")
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
		if target_texture is None:
			raise MaterialProfileError("target-texture-missing")
		result.update({
			"material_name": material["name"],
			"material_hash": material["hash"],
			"shader_type": material["shader_type"],
			"alpha_flags_raw": material["alpha_flags_raw"],
			"master_material": material["master_material"],
			"textures": legacy_textures,
			"target_texture": target_texture,
			"properties": material["properties"],
		})
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
	'buildNoesisMaterial',
	'dialogOptions',
	'extractedNativesPath',
	'generateDummyTexture4px',
	'invertRawRGBAChannel',
	'isImageBlank',
	'moveChannelsRGBA',
	'noesis',
	'parsePragmataMdf2Profile',
	'rapi',
	'resolvePragmataMdfPath',
	'resolvePragmataTexturePath',
	'sGameName',
	'texLoadDDS',
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


def bind_mesh_materials(runtime):
	def createMaterials(self, matCount):
		# Shared state is owned by runtime.

		doColorize = runtime.bColorize
		doPrintMDF = runtime.bPrintMDF
		noMDFFound = 0
		skipPrompt = 0

		modelExt = formats[runtime.sGameName]["modelExt"]
		texExt = formats[runtime.sGameName]["texExt"]
		mmtrExt = formats[runtime.sGameName]["mmtrExt"]
		nDir = formats[runtime.sGameName]["nDir"]
		mdfExt = formats[runtime.sGameName]["mdfExt"]

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

		if runtime.sGameName == "ReVerse" and os.path.isdir(os.path.dirname(inputName) + "\\Material"):
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
		if not runtime.rapi.checkFileExists(pathPrefix + mdfExt):
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
			if self.mdfVer >= 2: #sGameName == "RERT" or sGameName == "RE3" or sGameName == "ReVerse" or sGameName == "RE8" or sGameName == "MHRise":
				pathPrefix = runtime.extractedNativesPath + re.sub(r'.*stm\\', '', inputName)
			else:
				pathPrefix = runtime.extractedNativesPath + re.sub(r'.*x64\\', '', inputName)
			pathPrefix = pathPrefix.replace(modelExt,"").replace(".mesh","")
			materialFileName = (pathPrefix + mdfExt)
			print (materialFileName)
			if not (runtime.rapi.checkFileExists(materialFileName)):
				materialFileName = (pathPrefix + "_mat" + mdfExt)
			if not (runtime.rapi.checkFileExists(materialFileName)):
				materialFileName = (pathPrefix + "_00" + mdfExt)

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
		bs = runtime.NoeBitStream(bs)
		#Magic, Unknown, MaterialCount, Unknown, Unknown
		matHeader = [bs.readUInt(), bs.readUShort(), bs.readUShort(), bs.readUInt(), bs.readUInt()]
		matCountMDF = matHeader[2]

		if matCountMDF != matCount and len(self.fullMatList) == 0:
			print ("MDF Checkerboard Error: MDF does not have the same material count as the MESH file!\n	MESH materials:", matCount, "\n	MDF Materials:", matCountMDF)
			return 0

		usedMats = [mat.name for mat in self.fullMatList]
		usedTexs = [tex.name for tex in self.fullTexList]

		#Parse Materials
		for i in range(matCountMDF):

			record = readLegacyMaterialEntry(bs, self.mdfVer, i, runtime.ReadUnicodeString)
			materialName = record["name"]
			materialHash = record["hash"]
			mmtrName = record["master_material"]
			floatCount = record["property_count"]
			texCount = record["texture_count"]
			#hasTransparency = not not (((alphaFlag & ( 1 << 1 )) >> 1) or ((alphaFlag & ( 1 << 4 )) >> 4))
			hasTransparency = "_dirt" in mmtrName or "_decal" in mmtrName or "_hair" in mmtrName

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

			bFoundBaseColour = False
			bFoundRoughColour = False
			bFoundSpecColour = False
			bFoundAmbiColour = False
			bFoundMetallicColour = False
			bFoundFresnelColour = False

			if doPrintMDF:
				print ("Material Properties:")

			for j in range(floatCount): # floats
				propertyRecord = readLegacyMaterialProperty(bs, self.mdfVer, record, j, runtime.ReadUnicodeString)
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

			alreadyLoadedTexs = [tex.name for tex in self.fullTexList]
			alreadyLoadedMats = [mat.name for mat in self.fullMatList]
			secondaryDiffuse = ""

			for j in range(texCount): # texture headers

				textureRecord = readLegacyMaterialTexture(bs, self.mdfVer, record, j, runtime.ReadUnicodeString)
				textureType = textureRecord["slot"]
				textureName = textureRecord["path"]

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
							if runtime.bPrintFileList and not (textureFilePath.endswith("rtex" + tmpExt)) and (k==1 or runtime.sGameName.find("MHR") == -1):
								self.missingTexNames.append("DOES NOT EXIST: " + ('natives/' + (re.sub(r'.*natives\\', '', textureFilePath)).lower()).replace("\\","/").replace("streaming/",""))
						if "MHR" not in runtime.sGameName:
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
				#if (("BaseMetal" in textureType or "BaseDielectric" in textureType or "BaseAlpha" in textureType or "BaseShift" in textureType)) and not bFoundBM: #
				if "_alb" in lowerTexName and (not bFoundBM or ("_albd" in lowerTexName)): #goddamn RE8 #"_albm" in lowerTexName or
					bFoundBM = True
					material.setTexture(texName)
					material.setSpecularColor([.25, .25, .25, 1])
					if "AlphaMap" in textureType:
						extraParam = "isALBA"
					if "Metal" in textureType:
						extraParam = "isALBM"
					if "Dielectric" in textureType:
						extraParam = "isALBD"
					self.uvBias[material.name] = [0.5, 0.5] if runtime.sGameName == "RE7RT" and "atlas" in lowerTexName else 1.0
				#elif (("Normal" in textureType or "NR" in textureType) or "_nr" in lowerTexName) and not bFoundNM:
				elif "_nr" in lowerTexName and not bFoundNM:
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
				elif re.search("^Base.*Map$", textureType) and not secondaryDiffuse:
				#elif ("_alb" in lowerTexName) and not secondaryDiffuse:
					secondaryDiffuse = texName
				elif not runtime.dialogOptions.loadAllTextures:
					isNotMainTexture = True

				if not bAlreadyLoadedTexture and not isNotMainTexture:
					if (textureName.endswith("rtex")):
						pass
					elif not (runtime.rapi.checkFileExists(textureFilePath)):
						if textureFilePath != "":
							print("Error: Texture at path: " + str(textureFilePath) + " does not exist!")
					else:
						textureData = runtime.rapi.loadIntoByteArray(textureFilePath)
						numTex = len(self.texList)
						noetex = runtime.texLoadDDS(textureData, self.texList, texName)
						if noetex:
							if runtime.dialogOptions.doConvertTex:
								if "isALBM"  == extraParam or "isALBD" == extraParam:
									if "isALBD" == extraParam:
										noetex.pixelData = runtime.invertRawRGBAChannel(noetex.pixelData, 3)
									materialFlags |= runtime.noesis.NMATFLAG_PBR_METAL
									if runtime.dialogOptions.doConvertMatsForBlender:
										metalTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "a8a8a8")
										metalTexData = runtime.rapi.imageDecodeRaw(metalTexData, noetex.width, noetex.height, "r8g8b8")
										noetex.pixelData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8g8b8")
										noetex.pixelData = runtime.rapi.imageDecodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8g8b8")
										if not runtime.isImageBlank(metalTexData, noetex.width, noetex.height, 4):
											metalTexName = texName.replace(runtime.texOutputExt,  "_NoesisMET" + runtime.texOutputExt)
											material.setSpecularTexture(metalTexName)
											self.texList.append(runtime.NoeTexture(metalTexName, noetex.width, noetex.height, metalTexData, runtime.noesis.NOESISTEX_RGBA32))
									else:
										material.setSpecularTexture(texName)
										material.setSpecularSwizzle( runtime.NoeMat44([[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]])) #move alpha channel to green channel
								if runtime.dialogOptions.doConvertMatsForBlender and ("isNRM" == extraParam or "isNRR" in extraParam):
									roughnessTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "a8a8a8" if "isNRM" == extraParam else "r8r8r8")
									roughnessTexData = runtime.rapi.imageDecodeRaw(roughnessTexData, noetex.width, noetex.height, "r8g8b8")
									if not runtime.isImageBlank(roughnessTexData, noetex.width, noetex.height, 4):
										roughnessTexName = texName.replace(runtime.texOutputExt,  "_NoesisRGH" + runtime.texOutputExt)
										self.texList.append(runtime.NoeTexture(roughnessTexName, noetex.width, noetex.height, roughnessTexData, runtime.noesis.NOESISTEX_RGBA32))
										material.setBumpTexture(roughnessTexName)
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
									materialFlags |= runtime.noesis.NMATFLAG_PBR_METAL
									metalTexName = texName.replace(runtime.texOutputExt,  "_NoesisMET" + runtime.texOutputExt)
									metalTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8r8r8")
									metalTexData = runtime.rapi.imageDecodeRaw(metalTexData, noetex.width, noetex.height, "r8g8b8")
									material.setSpecularTexture(metalTexName)
									self.texList.append(runtime.NoeTexture(metalTexName, noetex.width, noetex.height, metalTexData, runtime.noesis.NOESISTEX_RGBA32))
									if runtime.dialogOptions.doConvertMatsForBlender:
										roughnessTexName = texName.replace(runtime.texOutputExt,  "_NoesisRGH" + runtime.texOutputExt)
										roughnessTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "b8b8b8")
										roughnessTexData = runtime.rapi.imageDecodeRaw(roughnessTexData, noetex.width, noetex.height, "r8g8b8")
										self.texList.append(runtime.NoeTexture(roughnessTexName, noetex.width, noetex.height, roughnessTexData, runtime.noesis.NOESISTEX_RGBA32))
										material.setBumpTexture(roughnessTexName)
									noetex.pixelData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "a8a8a8")
									noetex.pixelData = runtime.rapi.imageDecodeRaw(noetex.pixelData, noetex.width, noetex.height, "r8g8b8")
									material.setOcclTexture(noetex.name)

								if "isATOS" in extraParam:
									imgData = copy.copy(noetex.pixelData)
									aoTexData = runtime.rapi.imageEncodeRaw(noetex.pixelData, noetex.width, noetex.height, "b8b8b8")
									aoTexData = runtime.rapi.imageDecodeRaw(aoTexData, noetex.width, noetex.height, "r8g8b8")
									if not runtime.isImageBlank(aoTexData, noetex.width, noetex.height):
										noetex.name = texName.replace(runtime.texOutputExt,  "_NoesisAO" + runtime.texOutputExt)
										self.texList[len(self.texList)-1].pixelData = aoTexData
									else:
										self.texList.remove(noetex)
										material.setOcclTexture("")
									if extraParam == "isATOS_Alpha" and not opacityName:
										opacityTexData = runtime.rapi.imageEncodeRaw(imgData, noetex.width, noetex.height, "r8r8r8")
										opacityTexData = runtime.rapi.imageDecodeRaw(opacityTexData, noetex.width, noetex.height, "r8g8b8")
										if not runtime.isImageBlank(opacityTexData, noetex.width, noetex.height):
											opacityName = texName.replace(runtime.texOutputExt,  "_NoesisAlpha" + runtime.texOutputExt)
											materialFlags |= runtime.noesis.NMATFLAG_TWOSIDED
											self.texList.append(runtime.NoeTexture(opacityName, noetex.width, noetex.height, opacityTexData, runtime.noesis.NOESISTEX_RGBA32))
							alreadyLoadedTexs.append(texName)
						else:
							print ("Failed to load", texName)

				if opacityName and hasTransparency:
					material.setAlphaTest(0.05)
					material.setOpacityTexture(opacityName)
					if runtime.dialogOptions.doConvertMatsForBlender:
						material.setEnvTexture(opacityName)


				if doPrintMDF:
					print(textureType + ":\n    " + textureName)

			if secondaryDiffuse and not bFoundBM:
				material.setTexture(secondaryDiffuse)
				material.setSpecularColor([.25, .25, .25, 1])

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
		mdfPath = runtime.resolvePragmataMdfPath(self.path)
		if not runtime.rapi.checkFileExists(mdfPath):
			print("PRAGMATA MDF2 exact companion not found:", mdfPath)
			return False
		try:
			mdfData = runtime.rapi.loadIntoByteArray(mdfPath)
			profile = runtime.parsePragmataMdf2Profile(mdfData, mdfPath)
			orderedRecords = runtime.bindPragmataMaterialRecords(meshMaterialNames, profile["materials"])
			loadRecords = []
			allPaths = {}
			for record in orderedRecords:
				builderRecord = dict(record)
				builderTextures = []
				selected = []
				for texture in record["textures"]:
					builderTexture = dict(texture)
					if (profile["material_count"] == 1 and "target_texture" in profile
							and texture["slot"] == profile["target_texture"]["slot"]):
						builderTexture["semantic"] = "diagnostic-mask"
						builderTexture["preview_use"] = "diagnostic-diffuse"
					if builderTexture.get("preview_use") in ("preview-mapping", "diagnostic-diffuse"):
						texPath = runtime.resolvePragmataTexturePath(self.path, builderTexture["path"])
						if not runtime.rapi.checkFileExists(texPath):
							if builderTexture.get("preview_use") == "diagnostic-diffuse":
								raise MaterialProfileError("tex-companion-missing")
							print("PRAGMATA optional preview texture missing:", builderTexture["slot"], "->", texPath)
						else:
							selected.append((builderTexture, texPath))
							allPaths[os.path.normcase(os.path.normpath(texPath))] = texPath
					builderTextures.append(builderTexture)
				builderRecord["textures"] = builderTextures
				loadRecords.append((builderRecord, selected))
			stagedTextures = []
			decodedByPath = {}
			for normalizedPath, texPath in allPaths.items():
				texData = runtime.rapi.loadIntoByteArray(texPath)
				resourcePath = None
				for builderRecord, selected in loadRecords:
					for texture, selectedPath in selected:
						if os.path.normcase(os.path.normpath(selectedPath)) == normalizedPath:
							resourcePath = texture["path"]
							break
					if resourcePath is not None:
						break
				texBaseName = os.path.basename(resourcePath.replace("/", "\\"))
				texName = texBaseName[:-4] + runtime.texOutputExt
				loadedTexture = runtime.texLoadDDS(
					texData, stagedTextures, texName, texPath, pragmataDecoder
				)
				if not loadedTexture:
					raise MaterialProfileError("tex-decode-failed")
				decodedByPath[normalizedPath] = loadedTexture

			stagedMaterials = []
			for builderRecord, selected in loadRecords:
				textureNamesBySlot = {}
				for texture, texPath in selected:
					normalizedPath = os.path.normcase(os.path.normpath(texPath))
					textureNamesBySlot[texture["slot"]] = decodedByPath[normalizedPath].name
				stagedMaterials.append(runtime.buildNoesisMaterial(builderRecord, textureNamesBySlot))

			self.texList.extend(stagedTextures)
			self.matList.extend(stagedMaterials)
			for loadedTexture in stagedTextures:
				if loadedTexture.name not in [tex.name for tex in self.fullTexList]:
					self.fullTexList.append(loadedTexture)
			for material in stagedMaterials:
				if material.name not in [mat.name for mat in self.fullMatList]:
					self.fullMatList.append(material)
			profile["bound_material_names"] = [record["name"] for record in orderedRecords]
			self.materialProfile = profile
			print("PRAGMATA MDF2 observed profile:", profile["material_count"], "materials,", profile["texture_count"], "textures,", profile["property_count"], "properties")
			if profile["material_count"] == 1 and "target_texture" in profile:
				print("PRAGMATA diagnostic material texture:", profile["target_texture"]["slot"], "->", stagedMaterials[0].texName)
			return True
		except MaterialProfileError as error:
			print("PRAGMATA material exact profile rejected:", str(error))
			return False

	return (
		createMaterials,
		_loadPragmataMaterialProfile,
	)
