"""Scene implementation bound to one plugin runtime."""

from collections import namedtuple
from re_engine_config import (
	formats,
)
from re_engine_types import (
	namedtuple,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'LoadExtractedDir',
	'NoeBitStream',
	'NoeMaterial',
	'NoeModel',
	'NoeModelMaterials',
	'NoeQuat',
	'NoeVec3',
	'ReadUnicodeString',
	'collapseBones',
	'forceFindTexture',
	'meshFile',
	'noesis',
	'rapi',
	'readUIntAt',
	'readUnicodeStringAt',
	'sGameName',
	'texLoadDDS',
)


def bind(runtime):
	def UVSCheckType(data):
		bs = runtime.NoeBitStream(data)
		magic = bs.readUInt()
		if magic == 1431720750:
			return 1
		else:
			print("Fatal Error: Unknown file magic: " + str(hex(magic) + " expected ' SVU'!"))
			return 0

	def UVSLoadModel(data, mdlList):
		# Shared state is owned by runtime.
		bs = runtime.NoeBitStream(data)
		magic = bs.readUInt()
		textureNum = bs.readUInt()
		sequenceNum = bs.readUInt()
		patternNum = bs.readUInt()
		attribute = bs.readUInt()
		reserve = bs.readUInt()
		texturePtr = bs.readUInt64()
		sequencePtr = bs.readUInt64()

		patternPtr = bs.readUInt64()
		stringPtr = bs.readUInt64()

		uvsTexList = []
		uvsMatList = []
		textures = []

		bs.seek(texturePtr)
		texFile = ""
		runtime.sGameName = "RE2"
		aspectRatios = []
		for i in range(textureNum):
			aspectRatios.append((1,1))
			mStateHolder = bs.readUInt64()
			mDataPtr = bs.readUInt64()
			mTextureHandleTbl = [bs.readUInt64(), bs.readUInt64(), bs.readUInt64()]
			Name = runtime.readUnicodeStringAt(bs, stringPtr + mDataPtr * 2)
			textures.append([mStateHolder, mDataPtr, mTextureHandleTbl, Name])

			if texFile != 0:
				texFile, ext = runtime.forceFindTexture(Name)
				if texFile != 0:
					textureData = runtime.rapi.loadIntoByteArray(texFile)
					matName = runtime.rapi.getExtensionlessName(runtime.rapi.getExtensionlessName(runtime.rapi.getLocalFileName(texFile)))
					noetex = runtime.texLoadDDS(textureData, uvsTexList, matName)
					if noetex:
						aspectRatios[len(aspectRatios)-1] = (noetex.width / noetex.height, 1)
						noetex.name = matName
						uvsMatList.append(runtime.NoeMaterial(matName, texFile))

		bs.seek(sequencePtr)

		for i in range(sequenceNum):
			ctx = runtime.rapi.rpgCreateContext()
			#print ("sequence", bs.tell())
			patternCount = bs.readUInt()
			patternTbl = bs.readUInt()
			pos = bs.tell()

			UVs = []
			patterns = []
			bs.seek(patternPtr + patternTbl*32)
			for j in range(patternCount):
				#print("sequence at", bs.tell())
				uvTrans = bs.readUInt64()
				top = bs.readFloat()
				left = bs.readFloat()
				bottom = bs.readFloat()
				right = bs.readFloat()
				textureIndex = bs.readInt()
				cutoutUVCount = bs.readInt()
				patterns.append([uvTrans, left, top, right, bottom, textureIndex, cutoutUVCount])
				topLeft = (top, left, 0)
				bottomLeft = (bottom, left, 0)
				topRight = (top, right, 0)
				bottomRight = (bottom, right, 0)
				UVs = [topLeft, bottomRight, bottomLeft, topRight, bottomRight, topLeft]
				cutOutUVs = []
				for k in range(cutoutUVCount):
					cutoutUV = (bs.readFloat(), bs.readFloat(), 0)
					cutOutUVs.append(cutoutUV)
				cutOutUVsFaces = []
				for k in range(len(cutOutUVs)):
					if k == len(cutOutUVs) - 2:
						cutOutUVsFaces.extend([cutOutUVs[k], cutOutUVs[k+1], cutOutUVs[0]])
					elif k == len(cutOutUVs) - 1:
						cutOutUVsFaces.extend([cutOutUVs[k], cutOutUVs[0], cutOutUVs[1]])
					else:
						cutOutUVsFaces.extend([cutOutUVs[k], cutOutUVs[k+1], cutOutUVs[k+2]])
				UVs.extend(cutOutUVsFaces)
				runtime.rapi.rpgSetTransform((runtime.NoeVec3((1,0,0)), runtime.NoeVec3((0,-1,0)), runtime.NoeVec3((0,0,-1)), runtime.NoeVec3((0,0,0))))
				runtime.rapi.rpgSetName("Sequence" + str(i) + "_Pattern_" + str(j))
				if len(uvsMatList) > textureIndex:
					runtime.rapi.rpgSetMaterial(uvsMatList[textureIndex].name)
				runtime.rapi.immBegin(runtime.noesis.RPGEO_TRIANGLE)
				#print ("AR is", aspectRatios[textureIndex][0], aspectRatios[textureIndex][1])
				for k in range(0, len(UVs)):
					stretched = [UVs[k][0] * aspectRatios[textureIndex][0], UVs[k][1] * aspectRatios[textureIndex][1], 0]
					runtime.rapi.immUV2(UVs[k])
					runtime.rapi.immVertex3(stretched)
				runtime.rapi.immEnd()

			mdl = runtime.rapi.rpgConstructModel()
			if uvsTexList and uvsMatList:
				mdl.setModelMaterials(runtime.NoeModelMaterials(uvsTexList, uvsMatList))
			mdlList.append(mdl)
			runtime.rapi.rpgClearBufferBinds()

			bs.seek(pos)
		return 1

	def SCNCheckType(data):
		bs = runtime.NoeBitStream(data)
		magic = bs.readUInt()
		if magic == 5129043:
			return 1
		else:
			print("Fatal Error: Unknown file magic: " + str(hex(magic) + " expected 'SCN '!"))
			return 0

	def SCNLoadModel(data, mdlList):

		# Shared state is owned by runtime.
		fName = runtime.rapi.getInputName().upper()
		guessedName = "RE8" if "RE8" in fName else "RE7" if "RE7" in fName else "RE2" if "RE2" in fName else "RE3" if "RE3" in fName else "RE7" if "RE7" in fName \
		else "SF6" if "SF6" in fName else "MHRise" if "MHRISE" in fName else "RE4" if "RE4" in fName else "ExoPrimal" if ("EXO" in fName or "EXP" in fName) else "DMC5" if "DMC5" in fName \
		else "DD2" if "DD2" in fName else "DRDR" if "DRDR" in fName else "AJ_AAT"
		guessedName = guessedName + "RT" if (guessedName + "RT") in fName else guessedName

		msg = ''.join([name + ", " for name, formatList in formats.items()])
		inputName = runtime.noesis.userPrompt(runtime.noesis.NOEUSERVAL_FILEPATH, "SCN Import", "Input the game name:  " + msg, guessedName, None)
		if not inputName:
			return 0
		#inputName = inputName.upper()
		isRTRemake = (inputName != "RE7RT" and "RT" in inputName)
		inputName = inputName.replace("RT", "") if isRTRemake else inputName
		if inputName not in formats:
			print ("Not a valid game!")
			return 0
		runtime.sGameName = inputName
		current_pak_location = runtime.LoadExtractedDir(runtime.sGameName)
		runtime.sGameName = "RERT" if isRTRemake else runtime.sGameName

		def getAlignedOffset(tell, alignment):
			mask = alignment - 1
			return (tell + mask) & ~mask

		def readByteAndReturn(bs):
			out = bs.readByte()
			bs.seek(-1, 1)
			return out

		def detectedFloat(bs):
			if bs.tell() + 4 > bs.getSize():
				return False
			flt = abs(bs.readFloat())
			return flt == 0 or 0.000000001 <= flt <= 100000000.0

		def detectedBools(bs, atAddress):
			returnPos = bs.tell()
			bs.seek(atAddress)
			nonBoolTotal = sum(abs(bs.readByte()) > 1 for i in range(4))
			bs.seek(returnPos)
			#print(returnPos, nonBoolTotal)
			return nonBoolTotal == 0

		def detectedXform(bs):
			if bs.tell() + 32 >= bs.getSize():
				return False
			returnPos = bs.tell()
			bs.seek(getAlignedOffset(returnPos, 16))
			detected = all(detectedFloat(bs) for i in range(12) if i < 3 or i > 7)
			bs.seek(returnPos)
			return detected

		def checkByteIsUnicodeAlt(bs):
			altByte = bs.readUByte()
			return altByte == 0 or 30 <= altByte <= 150 #try to detect Japanese

		def detectedString(bs, offset):
			returnPos = bs.tell()
			result = False
			bs.seek(offset)
			if bs.readByte() != 0 and checkByteIsUnicodeAlt(bs) and bs.readByte() != 0 and checkByteIsUnicodeAlt(bs) and bs.readByte() != 0 and checkByteIsUnicodeAlt(bs):
				result = True
			bs.seek(returnPos)
			return result

		def redetectStringBehind(bs, is_second_time):
			pos = bs.tell()
			slash_detected = False
			if detectedString(bs, bs.tell()):
				while detectedString(bs, bs.tell()):
					bs.seek(-2, 1)
					slash_detected = slash_detected or ((readByteAndReturn(bs)) == 47)
				bs.seek(-2, 1)
			if not is_second_time and (detectedString(bs, bs.tell())):
				bs.seek(-10, 1)
				redetectStringBehind(bs, True)
				if not detectedString(bs, bs.tell()+4):
					bs.seek(pos)
			if slash_detected:
				bs.seek(pos)

		viaGameObject = namedtuple('viaGameObject', ['Name', 'Tag', 'DrawSelf', 'UpdateSelf', 'TimeScale'])

		def readViaGameObject(bs, timescale_offset):
			bs.seek(getAlignedOffset(bs.tell(), 4)+4)
			Name = runtime.ReadUnicodeString(bs)
			bs.seek(getAlignedOffset(bs.tell(), 4)+4)
			Tag = runtime.ReadUnicodeString(bs)
			DrawSelf = bs.readByte()
			UpdateSelf = bs.readByte()
			bs.seek(timescale_offset)
			#bs.seek(getAlignedOffset(bs.tell(), 4))
			TimeScale = bs.readFloat()
			return viaGameObject(Name, Tag, DrawSelf, UpdateSelf, TimeScale)

		viaTransform = namedtuple('viaTransform', ['LocalPosition', 'LocalRotation', 'LocalScale', 'ParentBoneSize', 'ParentBone', 'SameJointsConstraints', 'AbsoluteScaling'])

		def readViaTransform(bs):
			bs.seek(getAlignedOffset(bs.tell(), 16))
			LocalPosition = runtime.NoeVec3((bs.readFloat(), bs.readFloat(), bs.readFloat()))
			bs.seek(4,1)
			LocalRotation = runtime.NoeQuat((bs.readFloat(), bs.readFloat(), bs.readFloat(), bs.readFloat()))
			LocalScale = runtime.NoeVec3((bs.readFloat(), bs.readFloat(), bs.readFloat()))
			bs.seek(4,1)
			bs.seek(getAlignedOffset(bs.tell(), 4))
			ParentBoneSize = bs.readInt()
			ParentBone = runtime.ReadUnicodeString(bs)
			SameJointsConstraints = bs.readByte()
			AbsoluteScaling = bs.readByte()
			return viaTransform(LocalPosition, LocalRotation, LocalScale, ParentBoneSize, ParentBone, SameJointsConstraints, AbsoluteScaling)

		def findMesh(bs, limitPoint):
			pos = bs.tell()
			meshPath = runtime.ReadUnicodeString(bs)
			output = [None, None]
			print("Scanning from", pos, "to", limitPoint, "for meshes")
			while meshPath.find(".mesh") == -1:
				if bs.tell() >= limitPoint: break
				while not detectedString(bs, bs.tell()):
					if bs.tell() >= limitPoint: break
					if bs.tell() + 4 > bs.getSize():
						return output
					bs.seek(4,1)
				try:
					bs.seek(getAlignedOffset(bs.tell()-2, 4))
					meshPath = runtime.ReadUnicodeString(bs)
					bs.seek(getAlignedOffset(bs.tell()+1, 4))
				except:
					break
			if meshPath.find(".mesh") != -1 and meshPath.lower().find("occ") == -1:
				meshPath = meshPath.replace("/", "\\")
				meshPath = current_pak_location + meshPath + formats[runtime.sGameName]["modelExt"]
				print("Found mesh:", meshPath, "\n")
				bs.seek(getAlignedOffset(bs.tell(), 4)+4)
				mdfPath = runtime.ReadUnicodeString(bs)
				if mdfPath.find(".mdf2"):
					mdfPath = mdfPath.replace("/", "\\")
					mdfPath = current_pak_location + mdfPath + formats[runtime.sGameName]["mdfExt"].replace(".mdf2", "")
				output = [meshPath, mdfPath]

			return output

		def findGameObjects(bs):
			GameObjectAddresses = []
			GameObjects = []
			fileSize = bs.getSize()
			pos = 0
			bs.seek(0)
			tester = bs.readUInt()
			while tester != 5919570 and bs.tell() + 4 < fileSize: #find "RSZ" magic
				bs.seek(-3,1)
				tester = bs.readUInt()
			if tester == 5919570:
				bs.seek(getAlignedOffset(bs.tell(), 4))
				while bs.tell() + 4 < fileSize:
					while tester != 3212836864 and bs.tell() + 4 < fileSize: # 00 00 80 BF , timescale -1.0
						tester = bs.readUInt()
					boolSearchPos = bs.tell()-8
					foundBools = detectedBools(bs, bs.tell()-8)
					foundXform = detectedXform(bs)
					if pos < fileSize - 16 and foundBools and foundXform:
						print ("\nFound possible GameObject at ", bs.tell())
						GameObjectAddresses.append(bs.tell())
					else:
						print ("\nFound possible GameObject at ", bs.tell(), "but xform:", foundXform, "and bools:", foundBools, boolSearchPos)
					tester = bs.readUInt()

				if len(GameObjectAddresses) > 0:
					GameObjectAddresses.append(fileSize)
					for i in range(len(GameObjectAddresses)-1):
						bs.seek(GameObjectAddresses[i])
						transform = readViaTransform(bs)
						bs.seek(GameObjectAddresses[i]-28)
						pos2 = bs.tell()
						while not detectedString(bs, bs.tell()) and pos2 - bs.tell() < 12:
							bs.seek(-2,1)
						if pos2 - bs.tell() == 12:
							bs.seek(pos2)
						if detectedString(bs, bs.tell()):
							redetectStringBehind(bs, False)
						st = bs.tell()
						gameobject = readViaGameObject(bs, GameObjectAddresses[i]-4)
						if gameobject.Name and abs(gameobject.DrawSelf) <= 1 and abs(gameobject.UpdateSelf) <= 1 and gameobject.TimeScale == -1:
							meshMDF = findMesh(bs, GameObjectAddresses[i+1])
							GameObjects.append([gameobject, transform, meshMDF[0], meshMDF[1]])
						elif not (abs(gameobject.DrawSelf) <= 1 and abs(gameobject.UpdateSelf) <= 1):
							#print("1. Failed to add GameObject at", st, pos2, abs(gameobject.DrawSelf),  abs(gameobject.UpdateSelf), gameobject.TimeScale, gameobject.Name)
							bs.seek(st - 8)
							pos2 = bs.tell()
							while not detectedString(bs, bs.tell()) and pos2 - bs.tell() < 12:
								bs.seek(-2,1)
							if pos2 - bs.tell() == 12:
								bs.seek(pos2)
							if detectedString(bs, bs.tell()):
								redetectStringBehind(bs, False)
							st = bs.tell()
							gameobject = readViaGameObject(bs, GameObjectAddresses[i]-4)
							if gameobject.Name and abs(gameobject.DrawSelf) <= 1 and abs(gameobject.UpdateSelf) <= 1 and gameobject.TimeScale == -1:
								meshMDF = findMesh(bs, GameObjectAddresses[i+1])
								GameObjects.append([gameobject, transform, meshMDF[0], meshMDF[1]])
							else:
								print("2. Failed to add GameObject at", st, pos2, abs(gameobject.DrawSelf),  abs(gameobject.UpdateSelf), gameobject.TimeScale, gameobject.Name)

			print("Num detected:", len(GameObjectAddresses), len(GameObjects))
			return GameObjects

		ss = runtime.NoeBitStream(data)
		gameObjs = findGameObjects(ss)
		ctx = runtime.rapi.rpgCreateContext()

		totalTexList = []
		totalMatList = []
		totalBoneList = []
		totalRemapTable = []
		ids = []
		parentIds = []
		gameObjsDict = {}

		ss.seek(64+16)
		for i in range(runtime.readUIntAt(ss, 4)):
			ids.append(ss.readUInt())
			parentIds.append(ss.readUInt())
			ss.seek(24,1)

		counter = 0
		usedNames = {}
		print("Expected GameObject count:", len(parentIds), ", Num found GameObjects:", len(gameObjs))
		#for i, gameObj in enumerate(gameObjs):
		#	print(i, gameObj)
		#return 1

		for i, tup in enumerate(gameObjs):
			try:
				gameObjsDict[ids[i]] = tup
			except:
				pass

			if tup[2] != None and runtime.rapi.checkFileExists(tup[2]) and tup[0].Name.find("AIMap") == -1:
				mesh = runtime.meshFile(runtime.rapi.loadIntoByteArray(tup[2]), tup[2])
				mesh.meshFile = tup[2]
				mesh.mdfFile = tup[3]
				mesh.pos = tup[1].LocalPosition
				mesh.rot = tup[1].LocalRotation
				mesh.scl = tup[1].LocalScale
				if i < len(parentIds):
					parentPosition = gameObjsDict[parentIds[i]][1].LocalPosition if parentIds[i] in gameObjsDict else runtime.NoeVec3((0,0,0))
					parentRotation = gameObjsDict[parentIds[i]][1].LocalRotation if parentIds[i] in gameObjsDict else runtime.NoeQuat((0,0,0,1))
					mesh.pos *= parentRotation.transpose()
					mesh.pos += parentPosition
					mesh.rot = parentRotation * mesh.rot

				mesh.fullTexList = totalTexList
				mesh.fullMatList = totalMatList
				mesh.fullBoneList = totalBoneList
				mesh.fullRemapTable = totalRemapTable
				mesh.name = tup[0].Name
				nameCtr = 1
				while mesh.name in usedNames:
					mesh.name = tup[0].Name + "#" + str(nameCtr)
					nameCtr += 1
				usedNames[mesh.name] = True
				mesh.loadMeshFile()
				counter += 1
		#return 1
		try:
			mdl = runtime.rapi.rpgConstructModelAndSort()
			mdl.setModelMaterials(runtime.NoeModelMaterials(totalTexList, totalMatList))
		except:
			mdl = runtime.NoeModel()

		mdl.setBones(totalBoneList)
		runtime.collapseBones(mdl)

		mdlList.append(mdl)
		print("\nLoaded", counter, "MESH files comprised of", len(mdl.meshes), "submeshes")

		return 1

	return (
		UVSCheckType,
		UVSLoadModel,
		SCNCheckType,
		SCNLoadModel,
	)
