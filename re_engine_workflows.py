"""Workflows implementation bound to one plugin runtime."""

import json
import re_engine_common as re_common
from re_engine_config import (
	PRAGMATA_250707828,
	PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY,
	PRAGMATA_MOTLIST_1057_MTRE_ONLY_CAPABILITY,
	PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY,
	PRAGMATA_MPLY_250707828,
)
from re_engine_types import (
	MeshProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'NoeBitStream',
	'NoeModel',
	'NoeModelMaterials',
	'Version',
	'_detectPragmataIdentity',
	'_parsePragmataMeshData',
	'_parsePragmataMplyData',
	'buildPragmataMotlist1057Model',
	'buildPragmataMotlist1057MultiModel',
	'collapseBones',
	'detectMeshCapability',
	'detectPragmataMotlistCapability',
	'dialogOptions',
	'generateBoneMap',
	'loadPragmataStreamingCompanion',
	'meshFile',
	'motlistFile',
	'noesis',
	'openOptionsDialogImportWindow',
	'parsePragmataHeader',
	'parsePragmataMplyHeader',
	'rapi',
	'selectPragmataMotlistActions',
	'shouldPromptPragmataMotlistSelection',
)


def bind(runtime):
	def _readMeshProfile(data, path):
		capability = runtime._detectPragmataIdentity(data, path)
		if capability is None:
			return (None, None, None, None)
		companion_path = None
		streaming_data = None
		if capability == PRAGMATA_MPLY_250707828:
			header = runtime.parsePragmataMplyHeader(data, path)
			companion_path, streaming_data = runtime.loadPragmataStreamingCompanion(path)
			parsed = runtime._parsePragmataMplyData(data, header, streaming_data)
		else:
			header = runtime.parsePragmataHeader(data, path)
			if header.get("streaming_entry_count"):
				companion_path, streaming_data = runtime.loadPragmataStreamingCompanion(path)
			parsed = runtime._parsePragmataMeshData(data, header, streaming_data)
		return (capability, header, parsed, companion_path)

	def detectMeshCapability(data, path):
		return _readMeshProfile(data, path)[0]

	def meshCheckType(data):
		input_name = runtime.rapi.getInputName()
		if input_name.lower().endswith(".251121828"):
			try:
				runtime.detectMeshCapability(data, input_name)
				return 1
			except MeshProfileError as error:
				print("RE_MESH_PROFILE_ERROR:" + str(error))
				return 0
		bs = runtime.NoeBitStream(data)
		magic = bs.readUInt()

		if magic == 0x4853454D:
			return 1
		else:
			print("Fatal Error: Unknown file magic: " + str(hex(magic) + " expected 'MESH'!"))
			return 0

	def motlistLoadModel(data, mdlList):
		ctx = runtime.rapi.rpgCreateContext()
		input_name = runtime.rapi.getInputName()
		if input_name.lower().endswith(".motlist.1057"):
			capability = runtime.detectPragmataMotlistCapability(data, input_name)
			if capability == PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY:
				model = runtime.buildPragmataMotlist1057Model(data, input_name)
			elif capability == PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY:
				decoded = re_common.decode_pragmata_motlist_1057_multi(
					data, input_name, error_type=MeshProfileError)
				selected_slots = None
				if runtime.shouldPromptPragmataMotlistSelection():
					selected_slots = runtime.selectPragmataMotlistActions(
						decoded, input_name)
					if selected_slots is None:
						mdlList.append(runtime.NoeModel())
						return 1
				model = runtime.buildPragmataMotlist1057MultiModel(
					data, input_name, selected_slots, decoded)
			elif capability == PRAGMATA_MOTLIST_1057_MTRE_ONLY_CAPABILITY:
				raise MeshProfileError("unsupported-motlist-content:mtre-only")
			else:
				raise MeshProfileError("unsupported-motlist-capability")
			mdlList.append(model)
			return 1

		runtime.dialogOptions.motDialog = None
		motlist = runtime.motlistFile(data, runtime.rapi.getInputName())
		mlDialog = runtime.openOptionsDialogImportWindow(None, None, {"motlist":motlist, "isMotlist":True})
		mlDialog.createMotlistWindow()

		mdl = runtime.NoeModel()

		if not mlDialog.isCancelled:
			mdl.setBones(mlDialog.pak.bones)
			runtime.collapseBones(mdl, 100)
			bones = list(mdl.bones)
			mdlBoneNames = [bone.name.lower() for bone in bones]
			sortedMlists = []
			for mlist in [mlDialog.loadedMlists[path] for path in mlDialog.fullLoadItems]:
				if mlist not in sortedMlists:
					sortedMlists.append(mlist)
			for mlist in sortedMlists:
				mlist.readBoneHeaders(mlDialog.loadItems)
				for bone in mlist.bones:
					if bone.name.lower() not in mdlBoneNames:
						bone.index = len(bones)
						bones.append(bone)
			anims = []
			for mlist in sortedMlists:
				mlist.bones = bones
				mlist.readBoneHeaders(mlDialog.loadItems)
				mlist.read(mlDialog.loadItems)
			for mlist in sortedMlists:
				mlist.makeAnims(mlDialog.loadItems)
				anims.extend(mlist.anims)

			mdl.setBones(bones)
			mdl.setAnims(anims)
			runtime.rapi.setPreviewOption("setAnimSpeed", "60.0")

		mdlList.append(mdl)

		return 1

	def meshLoadModel(data, mdlList):

		runtime.noesis.logPopup()
		print("\n\n	RE Engine MESH model import", runtime.Version, "by alphaZomega\n")

		ctx = runtime.rapi.rpgCreateContext()
		mesh = runtime.meshFile(data)
		# This object supplies selection state; actual loads use separate instances.
		mesh._profileSnapshot = None
		mesh.setGameName()
		isPragmataLoad = mesh.capability == PRAGMATA_250707828
		isPragmataMplyLoad = mesh.capability == PRAGMATA_MPLY_250707828
		pragmataStats = []
		runtime.dialogOptions.motDialog = None
		runtime.dialogOptions.dialog = None
		runtime.dialogOptions.currentDir = ""
		dialog = runtime.openOptionsDialogImportWindow(None, None, {"mesh":mesh})
		dialog.path = runtime.rapi.getInputName()
		dialog.createMeshWindow()

		while runtime.dialogOptions.motDialog and runtime.dialogOptions.motDialog.isOpen:
			runtime.dialogOptions.motDialog.createMotlistWindow()
			runtime.dialogOptions.motDialog.isOpen = False
			if dialog.isOpen:
				runtime.dialogOptions.currentDir = dialog.currentDir
				dialog.createMeshWindow()

		if not dialog.isCancelled:
			pragmataCandidatePaths = [
				path for path in dialog.fullLoadItems
				if path.lower().endswith(".251121828")
			]
			if len(pragmataCandidatePaths) > 1:
				pragmataLoadCount = 0
				for fullMeshPath in pragmataCandidatePaths:
					capability = runtime.detectMeshCapability(
						runtime.rapi.loadIntoByteArray(fullMeshPath), fullMeshPath
					)
					if capability in (PRAGMATA_250707828, PRAGMATA_MPLY_250707828):
						pragmataLoadCount += 1
				if pragmataLoadCount > 1:
					print("RE_MESH_PROFILE_ERROR:multiple-pragmata-load-items")
					return 0
			for fullMeshPath in dialog.fullLoadItems:
				meshToLoad = runtime.meshFile(runtime.rapi.loadIntoByteArray(fullMeshPath), fullMeshPath)
				meshToLoad.fullBoneList = dialog.pak.fullBoneList
				meshToLoad.fullRemapTable = dialog.pak.fullRemapTable
				meshToLoad.fullTexList = dialog.pak.fullTexList
				meshToLoad.fullMatList = dialog.pak.fullMatList
				meshToLoad.loadMeshFile()
				if meshToLoad.capability in (PRAGMATA_250707828, PRAGMATA_MPLY_250707828):
					isPragmataLoad = True
					if meshToLoad.capability == PRAGMATA_MPLY_250707828:
						isPragmataMplyLoad = True
					if meshToLoad.importStats is not None:
						pragmataStats.append(meshToLoad.importStats)
			if isPragmataLoad:
				try:
					mdl = (runtime.rapi.rpgConstructModel() if isPragmataMplyLoad else
						runtime.rapi.rpgConstructModelAndSort())
				except Exception:
					print("RE_MESH_PROFILE_ERROR:model-construction-failed")
					return 0
				if not getattr(mdl, "meshes", None):
					print("RE_MESH_PROFILE_ERROR:model-construction-failed")
					return 0
				if mdl.meshes[0].name.find("_") == 4:
					print ("\nWARNING: Noesis split detected!\n   Export this mesh to FBX with the advanced option '-fbxmeshmerge'\n")
			else:
				try:
					mdl = runtime.rapi.rpgConstructModelAndSort()
					if mdl.meshes[0].name.find("_") == 4:
						print ("\nWARNING: Noesis split detected!\n   Export this mesh to FBX with the advanced option '-fbxmeshmerge'\n")
				except:
					print("Failed to construct model from rpgeo context")
					mdl = runtime.NoeModel()
		else:
			mdl = runtime.NoeModel()

		doLoadAnims = (runtime.dialogOptions.motDialog and runtime.dialogOptions.motDialog.loadItems and not runtime.dialogOptions.motDialog.isCancelled)
		if doLoadAnims:
			mlDialog = runtime.dialogOptions.motDialog
			sortedMlists = []
			for mlist in [mlDialog.loadedMlists[path] for path in mlDialog.fullLoadItems]:
				if mlist not in sortedMlists:
					sortedMlists.append(mlist)
			motlist = mlDialog.pak
			mdl.setBones(dialog.pak.fullBoneList)
			runtime.collapseBones(mdl, 100)
			bones = list(mdl.bones)
			mdlBoneNames = [bone.name.lower() for bone in bones]
			for mlist in sortedMlists:
				mlist.meshBones = bones
				mlist.readBoneHeaders(mlDialog.loadItems)
				for bone in mlist.bones:
					if bone.name.lower() not in mdlBoneNames:
						bone.index = len(bones)
						bones.append(bone)
			anims = []
			startFrame = 0
			for mlist in sortedMlists:
				mlist.bones = bones
				mlist.readBoneHeaders(mlDialog.loadItems)
				mlist.totalFrames = startFrame
				mlist.read(mlDialog.loadItems)
				startFrame = mlist.totalFrames
			for mlist in sortedMlists:
				mlist.makeAnims(mlDialog.loadItems)
				anims.extend(mlist.anims)
			mdl.setBones(bones)
			mdl.setAnims(anims)
			runtime.rapi.setPreviewOption("setAnimSpeed", "60.0")
		else:
			mdl.setBones(dialog.pak.fullBoneList)

		mdl.setModelMaterials(runtime.NoeModelMaterials(dialog.pak.fullTexList, dialog.pak.fullMatList))

		if len(dialog.loadItems) > 1:
			if runtime.dialogOptions.reparentHelpers and not doLoadAnims:
				runtime.collapseBones(mdl, 1)
			if runtime.noesis.optWasInvoked("-bonenumbers"):
				runtime.generateBoneMap(mdl)
		mdlList.append(mdl)

		boneNames = {}
		for i, bone in enumerate(mdl.bones):
			if bone.name.lower() in boneNames:
				print("Duplicate Bone Name:", bone.name)
				runtime.collapseBones(mdl, 1)
				break
			boneNames[bone.name.lower()] = True

		for importStats in pragmataStats:
			print("RE_MESH_STATS_JSON:" + json.dumps(
				importStats, sort_keys=True, separators=(",", ":")
			))

		return 1

	return (
		_readMeshProfile,
		detectMeshCapability,
		meshCheckType,
		motlistLoadModel,
		meshLoadModel,
	)
