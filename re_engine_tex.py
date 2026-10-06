"""Tex implementation bound to one plugin runtime."""

import copy
import os
import re
import struct
from re_engine_types import _materialCheckedRange, _materialScalar
from re_engine_config import (
	texFormatLayouts,
	extToFormat,
	fmtNameToBpp,
	formats,
	texFormatNames,
)
from re_engine_types import (
	MaterialProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = ('NoeBitStream', 'NoeTexture', 'convertTexVersion', 'findSourceTexFile', 'noesis', 'rapi', 'readUByteAt', 'readUIntAt', 'texFile')

TEXTURE_IMPORT_RUNTIME_DEPENDENCIES = ('NoeBitStream', 'NoeTexture', 'bImportMips', 'convertTexVersion', 'decodePragmataTexMips', 'loadGDeflateDecoder', 'noesis', 'parsePragmataTexProfile', 'preparePragmataTexSurface', 'rapi', 'readTextureData')


def parsePragmataTexProfile(data, path):
	if not path.lower().endswith((".tex" + formats["PRAGMATA"]["texExt"])):
		raise MaterialProfileError("tex-suffix-mismatch")
	_materialCheckedRange(data, 0, 0x28, "tex-header")
	if data[0:4] != b"TEX\0":
		raise MaterialProfileError("tex-magic-mismatch")
	version = _materialScalar(data, 4, "<I", "tex-version")
	if version != formats["PRAGMATA"]["texVersion"]:
		raise MaterialProfileError("tex-version-mismatch")
	width, height, depth = struct.unpack_from("<HHH", data, 8)
	image_count = data[0x0E]
	mip_table_size = data[0x0F]
	format_code = _materialScalar(data, 0x10, "<I", "tex-format")
	swizzle = _materialScalar(data, 0x14, "<i", "tex-swizzle")
	cubemap = _materialScalar(data, 0x18, "<I", "tex-cubemap")
	if width <= 0 or height <= 0 or depth <= 0 or image_count <= 0:
		raise MaterialProfileError("tex-shape-mismatch")
	if cubemap not in (0, 4) or (cubemap == 4 and image_count != 6):
		raise MaterialProfileError("tex-shape-mismatch")
	if depth > 1 and (image_count != 1 or cubemap != 0):
		raise MaterialProfileError("tex-shape-mismatch")
	format_layout = texFormatLayouts.get(format_code)
	if format_layout is None:
		raise MaterialProfileError("tex-format-mismatch")
	unit_width, unit_height, unit_bytes = format_layout
	if mip_table_size <= 0 or mip_table_size % 16:
		raise MaterialProfileError("mip-table-size-mismatch")
	mip_count = mip_table_size // 16
	entry_count = image_count * mip_count
	mip_table_start = 0x28
	mip_table_byte_size = entry_count * 16
	mip_table_end = mip_table_start + mip_table_byte_size
	_materialCheckedRange(data, mip_table_start, mip_table_byte_size, "mip-table")
	chunk_table_start = mip_table_end
	chunk_table_size = entry_count * 8
	_materialCheckedRange(data, chunk_table_start, chunk_table_size, "physical-chunk-table")
	payload_start = chunk_table_start + chunk_table_size
	expected_logical_offset = mip_table_end
	expected_physical_relative = 0
	mips = []
	for index in range(entry_count):
		image_index = index // mip_count
		mip_index = index % mip_count
		logical_offset, pitch, logical_size = struct.unpack_from("<QII", data, mip_table_start + index * 16)
		if logical_offset != expected_logical_offset:
			raise MaterialProfileError("logical-mip-gap")
		mip_width = max(1, width >> mip_index)
		mip_height = max(1, height >> mip_index)
		mip_depth = max(1, depth >> mip_index)
		tight_pitch = max(1, (mip_width + unit_width - 1) // unit_width) * unit_bytes
		row_count = max(1, (mip_height + unit_height - 1) // unit_height)
		if pitch < tight_pitch or pitch % unit_bytes or logical_size != pitch * row_count:
			raise MaterialProfileError("logical-mip-size-mismatch")
		decoded_size = logical_size * mip_depth
		physical_size, physical_relative = struct.unpack_from("<II", data, chunk_table_start + index * 8)
		if physical_relative != expected_physical_relative:
			raise MaterialProfileError("physical-chunk-gap")
		physical_offset = payload_start + physical_relative
		physical_start, physical_end = _materialCheckedRange(data, physical_offset, physical_size, "physical-chunk")
		if physical_size == decoded_size:
			codec = "raw"
		elif physical_size >= 4 and data[physical_start:physical_start + 2] == b"\x04\xFB":
			codec = "gdeflate"
		else:
			raise MaterialProfileError("gdeflate-signature-mismatch")
		mips.append({
			"index": index,
			"image_index": image_index,
			"mip_index": mip_index,
			"width": mip_width,
			"height": mip_height,
			"depth": mip_depth,
			"logical_offset": logical_offset,
			"pitch": pitch,
			"tight_pitch": tight_pitch,
			"row_count": row_count,
			"logical_size": logical_size,
			"decoded_size": decoded_size,
			"physical_offset": physical_start,
			"physical_size": physical_size,
			"physical_end": physical_end,
			"codec": codec,
		})
		expected_logical_offset += decoded_size
		expected_physical_relative += physical_size
	if payload_start + expected_physical_relative != len(data):
		raise MaterialProfileError("physical-payload-tail")
	return {
		"version": version,
		"width": width,
		"height": height,
		"depth": depth,
		"image_count": image_count,
		"mip_count": mip_count,
		"format": format_code,
		"swizzle": swizzle,
		"cubemap": cubemap == 4,
		"payload_offset": payload_start,
		"mips": mips,
	}

def decodePragmataTexMips(data, profile, decoder):
	decoded = []
	for mip in profile["mips"]:
		start, end = _materialCheckedRange(data, mip["physical_offset"], mip["physical_size"], "physical-chunk")
		chunk = bytes(data[start:end])
		if mip["codec"] == "raw":
			output = chunk
		elif mip["codec"] == "gdeflate":
			output = decoder(chunk, mip["decoded_size"])
		else:
			raise MaterialProfileError("unsupported-mip-codec")
		if not isinstance(output, bytes) or len(output) != mip["decoded_size"]:
			raise MaterialProfileError("decoded-mip-size-mismatch")
		decoded.append(output)
	return decoded

def preparePragmataTexSurface(decodedMip, mip):
	if not isinstance(decodedMip, bytes) or len(decodedMip) != mip["decoded_size"]:
		raise MaterialProfileError("decoded-mip-size-mismatch")
	logical_size = mip["logical_size"]
	pitch = mip["pitch"]
	tight_pitch = mip["tight_pitch"]
	row_count = mip["row_count"]
	if logical_size != pitch * row_count or tight_pitch > pitch:
		raise MaterialProfileError("logical-mip-size-mismatch")
	first_slice = decodedMip[:logical_size]
	if pitch == tight_pitch:
		return first_slice
	return b"".join(
		first_slice[row * pitch:row * pitch + tight_pitch]
		for row in range(row_count)
	)


def appendTextureSurface(texture_type, pixel_type, textures, surface):
	"""Construct one decoded surface; naming/dimensions stay with its format."""
	name, width, height, pixels = surface
	texture = texture_type(name, width, height, pixels, pixel_type)
	textures.append(texture)
	return texture


def loadTextureForImport(runtime, data, textures, texture_name, source_path, texture_profile=None, decoder=None):
	texture_name = texture_name or runtime.rapi.getInputName()
	modern_data = len(data) >= 8 and struct.unpack_from("<I", data, 4)[0] == formats["PRAGMATA"]["texVersion"]
	family = texture_profile["family"] if texture_profile is not None else ("tex-251111100" if modern_data else "legacy")
	if family not in ("legacy", "tex-251111100"):
		raise MaterialProfileError("unsupported-texture-import-family")
	# A known on-disk identity retains its validation even through a legacy caller.
	if modern_data or family == "tex-251111100":
		try:
			profilePath = source_path or runtime.rapi.getInputName()
			profile = runtime.parsePragmataTexProfile(data, profilePath)
			decoder = decoder or runtime.loadGDeflateDecoder()
			decodedMips = runtime.decodePragmataTexMips(data, profile, decoder)
			tex = False
			for index, mipData in enumerate(decodedMips):
				mip = profile["mips"][index]
				if not runtime.bImportMips and mip["mip_index"] != 0:
					continue
				surfaceData = runtime.preparePragmataTexSurface(mipData, mip)
				texData, fmtName = runtime.readTextureData(surfaceData, mip["width"], mip["height"], profile["format"])
				if texData == 0:
					return 0
				imageName = texture_name
				if profile["image_count"] > 1:
					nameRoot, nameExt = os.path.splitext(texture_name)
					imageLabel = "face" if profile["cubemap"] else "image"
					imageName = nameRoot + "_" + imageLabel + "_" + str(mip["image_index"]) + nameExt
				if runtime.bImportMips and profile["mip_count"] > 1:
					nameRoot, nameExt = os.path.splitext(imageName)
					imageName = nameRoot + "_mip_" + str(mip["mip_index"]) + nameExt
				tex = appendTextureSurface(runtime.NoeTexture, runtime.noesis.NOESISTEX_RGBA32,
					textures, (imageName, mip["width"], mip["height"], texData))
			fmtName = texFormatNames.get(profile["format"], str(profile["format"]))
			print("PRAGMATA TEX profile:", profile["width"], "x", profile["height"], "x", profile["depth"], fmtName + ",", profile["image_count"], "images,", profile["mip_count"], "mips")
			return tex
		except MaterialProfileError as error:
			print("PRAGMATA TEX exact profile rejected:", str(error))
			return 0
	bs = runtime.NoeBitStream(data)
	magic = bs.readUInt()
	version = bs.readUInt()
	width = bs.readUShort()
	height = bs.readUShort()
	unk00 = bs.readUShort()
	version = runtime.convertTexVersion(version)

	if version > 27:
		numImages = bs.readUByte()
		oneImgMipHdrSize = bs.readUByte()
		mipCount = int(oneImgMipHdrSize / 16)
	else:
		mipCount = bs.readUByte()
		numImages = bs.readUByte()

	format = bs.readUInt()
	unk02 = bs.readUInt()
	unk03 = bs.readUInt()
	unk04 = bs.readUInt()

	if version > 27:
		bs.seek(8,1)

	mipData = []
	for i in range(numImages):
		mipDataImg = []
		for j in range(mipCount):
			mipDataImg.append([bs.readUInt64(), bs.readUInt(), bs.readUInt()]) #[0]offset, [1]pitch, [2]size
		mipData.append(mipDataImg)
		#bs.seek((mipCount-1)*16, 1) #skip small mipmaps

	formatName = texFormatNames[format]
	bpp = fmtNameToBpp[formatName]
	width = int((mipDataImg[0][1] / bpp) * 2)
	print(formatName, bpp)

	texFormat = runtime.noesis.NOESISTEX_RGBA32
	tex = False

	for i in range(numImages):
		mipWidth = width
		mipHeight = height

		for j in range(mipCount):
			try:
				bs.seek(mipData[i][j][0])
				texData = bs.readBytes(mipData[i][j][2])
			except:
				if i > 0:
					numImages = i - 1
					print ("Multi-image load stopped early")
					break
				else:
					return 0
			try:
				texData, fmtName = runtime.readTextureData(texData, mipWidth, mipHeight, format)
			except:
				print("Failed", mipWidth, mipHeight, format, texData)
				texData, fmtName = runtime.readTextureData(texData, mipWidth, mipHeight, format)
			if texData == 0:
				return 0

			tex = appendTextureSurface(runtime.NoeTexture, texFormat,
				textures, (texture_name, int(mipWidth), int(mipHeight), texData))

			if not runtime.bImportMips:
				break
			if mipWidth > 4:
				mipWidth = int(mipWidth / 2)
			if mipHeight > 4:
				mipHeight = int(mipHeight / 2)

	return tex



def bind(runtime):
	def texCheckType(data):
		bs = runtime.NoeBitStream(data)
		magic = bs.readUInt()
		if magic == 0x00584554:
			return 1
		else: 
			print("Fatal Error: Unknown file magic: " + str(hex(magic) + " expected TEX!"))
			return 0

	def readTextureData(texData, mipWidth, mipHeight, format):
		
		fmtName = texFormatNames[format] if format in texFormatNames else ""
		
		if format == 71 or format == 72: #ATOS
			texData = runtime.rapi.imageDecodeDXT(texData, mipWidth, mipHeight, runtime.noesis.FOURCC_DXT1)
		elif format == 77 or format == 78 or fmtName.find("BC3") != -1: #BC3
			texData = runtime.rapi.imageDecodeDXT(texData, mipWidth, mipHeight, runtime.noesis.FOURCC_BC3)
		elif format == 80 or fmtName.find("BC4") != -1: #BC4 wetmasks
			texData = runtime.rapi.imageDecodeDXT(texData, mipWidth, mipHeight, runtime.noesis.FOURCC_BC4)
		elif format == 83 or fmtName.find("BC5") != -1: #BC5
			texData = runtime.rapi.imageDecodeDXT(texData, mipWidth, mipHeight, runtime.noesis.FOURCC_BC5)
			texData = runtime.rapi.imageEncodeRaw(texData, mipWidth, mipHeight, "r16g16")
			texData = runtime.rapi.imageDecodeRaw(texData, mipWidth, mipHeight, "r16g16")
		elif format == 95 or format == 96 or fmtName.find("BC6") != -1:
			texData = runtime.rapi.imageDecodeDXT(texData, mipWidth, mipHeight, runtime.noesis.FOURCC_BC6H)
		elif format == 98 or format == 99 or fmtName.find("BC7") != -1:
			texData = runtime.rapi.imageDecodeDXT(texData, mipWidth, mipHeight, runtime.noesis.FOURCC_BC7)
		elif re.search("[RB]\d\d?", fmtName):
			fmtName = fmtName.split("_")[0].lower()
			texData = runtime.rapi.imageDecodeRaw(texData, mipWidth, mipHeight, fmtName)
		else:
			print("Fatal Error: Unsupported texture type: " + str(format))
			return 0
		#print("Detected texture format:", fmtName)
		return texData, fmtName

	def isImageBlank(imgData, width=None, height=None, threshold=1):
		first = imgData[0]
		if width and height and width * height > 4096:
			imgData = runtime.rapi.imageResample(imgData, width, height, 64, 64)
		for i, b in enumerate(imgData):
			if (i+1) % 4 != 0 and abs(b - first) > threshold: #skip alpha
				return False
		return True

	def invertRawRGBAChannel(imgData, channelID, bpp=4):
		for i in range(int(len(imgData)/4)):
			imgData[i*4+channelID] = 255 - imgData[i*4+channelID]
		return imgData

	def moveChannelsRGBA(sourceBytes, sourceChannel, sourceWidth, sourceHeight, targetBytes, targetChannels, targetWidth, targetHeight):
		outputTargetBytes = copy.copy(targetBytes)
		if sourceBytes == targetBytes and sourceChannel >= 0:
			for ch in targetChannels:
				outputTargetBytes = runtime.rapi.imageCopyChannelRGBA32(outputTargetBytes, sourceChannel, ch)
		else:
			resizedSourceBytes = runtime.rapi.imageResample(sourceBytes, sourceWidth, sourceHeight, targetWidth, targetHeight)
			nullValue = 1 if sourceChannel == -1 else 255 if sourceChannel == -2 else None
			for i in range(int(len(resizedSourceBytes)/16)):
				for b in range(4):
					for ch in targetChannels:
						outputTargetBytes[i*16 + b*4 + ch] = nullValue or resizedSourceBytes[i*16 + b*4 + sourceChannel]
		return outputTargetBytes

	def generateDummyTexture4px(rgbaColor, name="Dummy"):
		imageByteList = []
		for i in range(16):
			imageByteList.extend(rgbaColor)
		imageData = struct.pack("<" + 'B'*len(imageByteList), *imageByteList)
		imageData = runtime.rapi.imageDecodeRaw(imageData, 4, 4, "r8g8b8a8")
		return runtime.NoeTexture(name, 4, 4, imageData, runtime.noesis.NOESISTEX_RGBA32)

	def texLoadDDS(data, texList, texName="", sourcePath=None, pragmataDecoder=None):
		return loadTextureForImport(runtime, data, texList, texName, sourcePath, decoder=pragmataDecoder)

	def getNoesisDDSType(imgType):
		ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC7
		if imgType == 71 or imgType == 72: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC1
		elif imgType == 80: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC4
		elif imgType == 83: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC5
		elif imgType == 95: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC6H
		elif imgType == 98 or imgType == 99: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC7
		elif imgType == 28 or imgType == 29: ddsFmt = "r8g8b8a8"
		elif imgType == 77: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC3;
		elif imgType == 10 or imgType == 95: ddsFmt = "r16g16b16a16"
		elif imgType == 61: ddsFmt = "r8"
		return ddsFmt

	def findSourceTexFile(version_no, outputName=None):
		newTexName = outputName or runtime.rapi.getOutputName().lower()
		while newTexName.find("out.") != -1: 
			newTexName = newTexName.replace("out.",".")
		newTexName =  newTexName.replace(".dds","").replace(".tex","").replace(".jpg","").replace(".png","").replace(".tga","").replace(".gif","")
		for gameName, tbl in formats.items():
			newTexName = newTexName.replace(tbl["texExt"], "")
		ext = ".tex." + str(version_no)
		if not runtime.rapi.checkFileExists(newTexName + ext):
			for other_ext, subDict in extToFormat.items():
				if runtime.rapi.checkFileExists(newTexName + ".tex." + other_ext):
					ext = ".tex." + other_ext
		return newTexName + ext, ext

	def convertTexVersion(version_no): #because RE3R and RE4R randomly decide to use timestamps for version numbers, which doesnt work well with using the others as versions
		if version_no == 143221013:
			return 36
		if version_no == 190820018:
			return 10
		return version_no

	def texWriteRGBA2(data, width, height, bs, version_no):
		sourceFile = runtime.findSourceTexFile(10)
		#print(str(sourceFile))
		tex = runtime.texFile(data, width, height, sourceFile[0], runtime.rapi.getOutputName())
		if not hasattr(tex, "error"):
			bs = tex.writeTexHeader(bs)
			tex.writeTexImageData(bs, 1)
			return 1
		else:
			sourceFile = (sourceFile and sourceFile[0]) or runtime.rapi.getOutputName()
			print("No format detected for " + sourceFile)
		return 0

	def texWriteRGBA(data, width, height, bs):
		
		print ("\n			----RE Engine TEX Export----\n")
		
		version_no = int(os.path.splitext(runtime.rapi.getOutputName())[1][1:])
		#if noesis.optWasInvoked("-b"): # and version_no >= 28 and version_no < 1000: #batch / no-prompt
		#	return texWriteRGBA2(data, width, height, bs, version_no)
			
		def getExportName(fileName):		
			if fileName == None:
				newTexName = runtime.rapi.getOutputName().lower()
			else: 
				newTexName = fileName
			nonlocal version_no
			guessedName, ext = runtime.findSourceTexFile(version_no)
			
			newTexName = runtime.noesis.userPrompt(runtime.noesis.NOEUSERVAL_FILEPATH, "Inject tex", "Choose a tex file to inject", guessedName, None)
			
			if newTexName == None:
				print("Aborting...!")
				return
			return newTexName
			
		fileName = None
		if runtime.noesis.optWasInvoked("-b"):
			newTexName, ext = runtime.findSourceTexFile(version_no)
		else:
			newTexName = getExportName(fileName)
			if newTexName == None:
				return 0
			while not (runtime.rapi.checkFileExists(newTexName)):
				print ("File not found")
				newTexName = getExportName(fileName)	
				fileName = newTexName
				if newTexName == None:
					return 0
			
		bTexAsSource = False	
		newTEX = runtime.rapi.loadIntoByteArray(newTexName)
		oldDDS = runtime.rapi.loadIntoByteArray(runtime.rapi.getInputName())
		
		f = runtime.NoeBitStream(newTEX)
		og = runtime.NoeBitStream(oldDDS)
		
		magic = f.readUInt()
		version = f.readUInt()
		fWidth = f.readUShort()
		fHeight = f.readUShort()
		reVerseSize = 0
		
		version = runtime.convertTexVersion(version)
		
		f.seek(14)
		if version  > 27:
			reVerseSize = 8
			numImages = f.readUByte()
			oneImgMipHdrSize = f.readUByte()
			maxMips = int(oneImgMipHdrSize / 16)
		else:
			maxMips = f.readUByte()
			numImages = f.readUByte()
		
		ddsMagic = og.readUInt()
		bDoEncode = False
		if magic != 5784916:
			print ("Selected file is not a TEX file!\nAborting...")
			return 0
		
		f.seek(16)
		imgType = f.readUInt()
		print ("TEX type:", imgType)
		
		ddsFmt = 0
		bQuitIfEncode = False
		try:
			if imgType == 71 or imgType == 72: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC1
			elif imgType == 80: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC4
			elif imgType == 83: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC5
			elif imgType == 95: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC6H
			elif imgType == 98 or imgType == 99: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC7
			elif imgType == 28 or imgType == 29: ddsFmt = "r8g8b8a8"
			elif imgType == 77: ddsFmt = runtime.noesis.NOE_ENCODEDXT_BC3;
			elif imgType == 10 or imgType == 95: ddsFmt = "r16g16b16a16"
			elif imgType == 61: ddsFmt = "r8"
			else: 
				print ("Unknown TEX type:", imgType)
				if imgType != 10:
					return 0
		except: 
			bQuitIfEncode = True

		print ("Exporting over \"" + runtime.rapi.getLocalFileName(newTexName)+ "\"")
		
		texFmt = ddsFmt
		#ogHeaderSize = 0
		if og and ddsMagic == 542327876: #DDS
			ogHeaderSize = og.readUInt() + 4
			og.seek(84)
			if og.readUInt() == 808540228: #DX10
				ogHeaderSize += 20
				if ddsFmt == runtime.noesis.NOE_ENCODEDXT_BC1:
					print ("Source DDS encoding (BC7) does not match TEX file (BC1).\nEncoding image...")
					bDoEncode = True
			elif ddsFmt == runtime.noesis.NOE_ENCODEDXT_BC7:
				print ("Source DDS encoding (BC1) does not match TEX file (BC7).\nEncoding image...")
				bDoEncode = True
		elif og and ddsMagic == 5784916: #TEX
			bTexAsSource = True
			og.seek(4)
			ogVersion = runtime.convertTexVersion(og.readUInt())
			
			if ((ogVersion > 27) and int(os.path.splitext(runtime.rapi.getOutputName())[1][1:]) < 27) or ((ogVersion < 27 and int(os.path.splitext(runtime.rapi.getOutputName())[1][1:]) > 27)):
				print("\nWARNING: Source tex version does not match your output tex version\n	Selected Output:      tex" + str(os.path.splitext(runtime.rapi.getOutputName())[1]), "\n	Source Tex version: tex." + str(ogVersion) + "\n")
			og.seek(8)
			ogWidth = og.readUShort()
			ogHeight = og.readUShort()
			if ogWidth != width or ogHeight != height: 
				print ("Input TEX file uses a different resolution from Source TEX file.\nEncoding image...")
				bDoEncode = True
			og.seek(14)
			
			ogHeaderSize = og.readUByte() * 16 + 32
			if ogVersion  > 27: 
				ogHeaderSize = 40 + og.readUByte()
			og.seek(16)
			srcType = og.readUInt()  
			if srcType == 71 or srcType == 72: texFmt = runtime.noesis.NOE_ENCODEDXT_BC1
			elif srcType == 80: texFmt = runtime.noesis.NOE_ENCODEDXT_BC4
			elif srcType == 83: texFmt = runtime.noesis.NOE_ENCODEDXT_BC5
			elif srcType == 95: texFmt = runtime.noesis.NOE_ENCODEDXT_BC6H
			elif srcType == 98 or srcType == 99: texFmt = runtime.noesis.NOE_ENCODEDXT_BC7
			elif srcType == 28 or srcType == 29: texFmt = "r8g8b8a8"
			elif srcType == 77: texFmt = runtime.noesis.NOE_ENCODEDXT_BC3;
			elif srcType == 10 or srcType == 95: texFmt = "r16g16b16a16"
			elif srcType == 61: texFmt = "r8"
			else: 
				print ("Unknown TEX type:", srcType)
				return 0
			if texFmt != ddsFmt or (os.path.splitext(newTexName)[1] == ".30" and os.path.splitext(runtime.rapi.getInputName())[1] != ".30"): 
				print ("Input TEX file uses a different compression or format from Source TEX file.\nEncoding image...")
				bDoEncode = True
		else: 
			print ("Input file is not a DDS or TEX file\nEncoding image...")
			bDoEncode = True
		
		mipSize = width * height
		if texFmt == runtime.noesis.NOE_ENCODEDXT_BC1: mipSize = int(mipSize / 2)
		if not bDoEncode and mipSize < int((os.path.getsize(runtime.rapi.getInputName())) / 4):
			print ("Unexpected source image size\nEncoding image...")
			bDoEncode = True
			
		if not bDoEncode: 
			print ("Copying image data from \"" + runtime.rapi.getLocalFileName(runtime.rapi.getInputName()) + "\"")
			
		elif bQuitIfEncode:
			print ("Fatal Error: BC7 Encoding not supported!\nUpdate to Noesis v4434 (Oct 14, 2020) or later to encode BC7 images\nAborting...\n")
			return 0
			
		#copy header
		f.seek(0)
		bs.writeBytes(f.readBytes(32 + reVerseSize))
		
		numMips = 0
		output_mips = 0
		dataSize = 0
		totalData = 0
		sizeArray = []
		fileData = []
		mipWidth = width
		mipHeight = height
		
		exportCycles = 1
		if numImages > 1:
			imgToReplace = 0
			imgToReplace = runtime.noesis.userPrompt(runtime.noesis.NOEUSERVAL_FILEPATH, "Multi-image texture", "Which image do you want to replace? [0-" + str(numImages-1) + "]", "All", None)
			if imgToReplace == None:
				return 0
			try:
				int(imgToReplace)
			except:
				exportCycles = numImages #if not a number, copy all images
			mipWidth = fWidth
			mipHeight = fHeight
			bs.writeBytes(f.readBytes(os.path.getsize(newTexName) - f.tell())) #copy whole file
		
		print ("Format:", ddsFmt)
		for img in range(exportCycles):
				
			#write mipmap headers & encode image
			if img == 0:
				while mipWidth > 4 or mipHeight > 4:
					if ddsFmt == "r8" and numMips > 1:
						break
					numMips += 1
					output_mips += 1
					if bDoEncode:
						mipData = runtime.rapi.imageResample(data, width, height, mipWidth, mipHeight)
						try:
							dxtData = runtime.rapi.imageEncodeDXT(mipData, 4, mipWidth, mipHeight, ddsFmt)
						except:
							dxtData = runtime.rapi.imageEncodeRaw(mipData, mipWidth, mipHeight, ddsFmt)
						mipSize = len(dxtData)
						fileData.append(dxtData)
						
					else:
						mipSize = mipWidth * mipHeight
						if texFmt == runtime.noesis.NOE_ENCODEDXT_BC1:
							mipSize = int(mipSize / 2)
						
					sizeArray.append(dataSize)
					dataSize += mipSize
					
					pitch = mipWidth
					if ddsFmt == runtime.noesis.NOE_ENCODEDXT_BC1:
						pitch *= 2
					elif ddsFmt != "r8":
						pitch *= 4
						
					bs.writeUInt64(0)
					bs.writeUInt(pitch)
					bs.writeUInt(mipSize)
					
	                
					print ("Mip", numMips, ": ", mipWidth, "x", mipHeight, "\n            ", pitch, "\n            ", mipSize)
					if mipWidth > 4: mipWidth = int(mipWidth / 2)
					if mipHeight > 4: mipHeight = int(mipHeight / 2)
			
			if numImages > 1: #multi image images seek to their image data and encode at the same size 
				if exportCycles > 1:
					mipOffset = runtime.readUIntAt(f, (32 + reVerseSize + 16 * (int(img) * maxMips)) ) #copy same image data over the other images
					print ("Img",  img+1, "of", exportCycles)
				else:
					mipOffset = runtime.readUIntAt(f, (32 + reVerseSize + 16 * (int(imgToReplace) * maxMips)) )
			
			if bDoEncode: 
				if numImages > 1:
					bs.seek(mipOffset)
				for d in range(len(fileData)): #write image data
					bs.writeBytes(fileData[d])
			elif not numImages > 1:
				og.seek(ogHeaderSize) #copy image data
				bs.writeBytes(og.readBytes(os.path.getsize(runtime.rapi.getInputName()) - ogHeaderSize))
			else:
				og.seek(ogHeaderSize)
				bs.seek(mipOffset) #seek to image-to-replace
				bs.writeBytes(og.readBytes(os.path.getsize(runtime.rapi.getInputName()) - ogHeaderSize))
			
			#adjust header
			if numImages == 1:
				bs.seek(28)
				if runtime.readUByteAt(f, 28) > 127:
					bs.writeUByte(128) #ReVerse streaming
				else: 
					bs.writeUByte(0) #streaming texture
					
				bs.seek(8)
				bs.writeUShort(width)
				bs.writeUShort(height)
				if version  > 27:
					bs.seek(15)
					bs.writeUByte(numMips * 16)
				else:
					bs.seek(14)
					bs.writeUByte(numMips)
				
				bsHeaderSize = output_mips * 16 + 32 + reVerseSize
				bs.seek(32 + reVerseSize)
				
				for mip in range(numMips):
					bs.writeUInt64(sizeArray[mip] + bsHeaderSize)
					bs.seek(8, 1)	
			else:
				if numImages > 1:
					bs.seek(mipOffset)
				for d in range(len(fileData)): #write image data
					bs.writeBytes(fileData[d])

		return 1

	return (
		parsePragmataTexProfile,
		decodePragmataTexMips,
		preparePragmataTexSurface,
		texCheckType,
		readTextureData,
		isImageBlank,
		invertRawRGBAChannel,
		moveChannelsRGBA,
		generateDummyTexture4px,
		texLoadDDS,
		getNoesisDDSType,
		findSourceTexFile,
		convertTexVersion,
		texWriteRGBA2,
		texWriteRGBA,
	)
