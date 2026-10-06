"""Workflows implementation bound to one plugin runtime."""

import json
from re_engine_animation import loadMotionImport, attachSelectedAnimations, makeAnimationSelectionSource
from re_engine_runtime import beginImportSession
from re_engine_config import (
	formats,
	composeImportProfile,
	PRAGMATA_250707828,
	PRAGMATA_MPLY_250707828,
)
from re_engine_types import (
	MeshProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = ('NoeBitStream', 'NoeModel', 'NoeModelMaterials', 'Version', '_detectPragmataIdentity', '_parsePragmataMeshData', '_parsePragmataMplyData', 'collapseBones', 'detectMeshCapability', 'dialogOptions', 'generateBoneMap', 'loadPragmataStreamingCompanion', 'meshFile', 'noesis', 'openOptionsDialogImportWindow', 'parsePragmataHeader', 'parsePragmataMplyHeader', 'rapi', 'sGameName')



def loadSelectedMeshes(runtime, session, dialog):
	"""Load the ordered queue; retain the existing multi-profile restriction."""
	initial_rule = session.profile["mesh"]["construction"]
	# Initial MPLY affects sorting only if the final queue loads a strict mesh.
	rule = "legacy-sort-fallback" if initial_rule == "mply-unsorted-strict" else initial_rule
	stats = []
	strict_suffixes = tuple(record["modelExt"] for record in formats.values()
		if record["import"]["mesh"]["construction"] != "legacy-sort-fallback")
	candidates = [path for path in dialog.fullLoadItems if path.lower().endswith(strict_suffixes)]
	if len(candidates) > 1:
		count = 0
		for path in candidates:
			capability = runtime.detectMeshCapability(runtime.rapi.loadIntoByteArray(path), path)
			if capability in (PRAGMATA_250707828, PRAGMATA_MPLY_250707828):
				count += 1
		if count > 1:
			print("RE_MESH_PROFILE_ERROR:multiple-pragmata-load-items")
			return None
	for path in dialog.fullLoadItems:
		data = runtime.rapi.loadIntoByteArray(path)
		if path == session.input_path:
			mesh = runtime.meshFile(data, path, import_profile=session.profile)
		else:
			mesh = runtime.meshFile(data, path)
		mesh.fullBoneList = session.resources["bones"]
		mesh.fullRemapTable = session.resources["remap"]
		mesh.fullTexList = session.resources["textures"]
		mesh.fullMatList = session.resources["materials"]
		mesh.loadMeshFile()
		profile = getattr(mesh, "importProfile", None)
		if profile is None:  # Existing callers may supply a mesh-compatible object.
			profile = composeImportProfile(runtime.sGameName, formats[runtime.sGameName], mesh.capability)
		incoming = profile["mesh"]["construction"]
		if incoming != "legacy-sort-fallback":
			if initial_rule == "mply-unsorted-strict":
				rule = initial_rule
			elif rule != "mply-unsorted-strict":
				rule = incoming
			if mesh.importStats is not None:
				stats.append(mesh.importStats)
	return rule, stats


def constructImportedModel(runtime, construction_rule):
	if construction_rule == "legacy-sort-fallback":
		try:
			model = runtime.rapi.rpgConstructModelAndSort()
			if model.meshes[0].name.find("_") == 4:
				print("\nWARNING: Noesis split detected!\n   Export this mesh to FBX with the advanced option '-fbxmeshmerge'\n")
		except:
			print("Failed to construct model from rpgeo context")
			model = runtime.NoeModel()
		return model
	try:
		model = (runtime.rapi.rpgConstructModel() if construction_rule == "mply-unsorted-strict"
			else runtime.rapi.rpgConstructModelAndSort())
	except Exception:
		print("RE_MESH_PROFILE_ERROR:model-construction-failed")
		return None
	if not getattr(model, "meshes", None):
		print("RE_MESH_PROFILE_ERROR:model-construction-failed")
		return None
	if model.meshes[0].name.find("_") == 4:
		print("\nWARNING: Noesis split detected!\n   Export this mesh to FBX with the advanced option '-fbxmeshmerge'\n")
	return model


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
		beginImportSession(runtime, "motion", input_name)
		mdlList.append(loadMotionImport(runtime, data, input_name))
		return 1

	def meshLoadModel(data, mdlList):

		runtime.noesis.logPopup()
		print("\n\n	RE Engine MESH model import", runtime.Version, "by alphaZomega\n")

		ctx = runtime.rapi.rpgCreateContext()
		session = beginImportSession(runtime, "mesh", runtime.rapi.getInputName())
		mesh = runtime.meshFile(data)
		session.profile = getattr(mesh, "importProfile", None)
		session.resources = {"bones": mesh.fullBoneList, "remap": mesh.fullRemapTable,
			"textures": mesh.fullTexList, "materials": mesh.fullMatList}
		# This object supplies selection state; actual loads use separate instances.
		mesh._profileSnapshot = None
		mesh.setGameName()
		if session.profile is None:
			session.profile = composeImportProfile(runtime.sGameName, formats[runtime.sGameName], mesh.capability)
		pragmataStats = []
		runtime.dialogOptions.motDialog = None
		runtime.dialogOptions.dialog = None
		runtime.dialogOptions.currentDir = ""
		meshGame = runtime.sGameName
		meshArgs = {"mesh": mesh}
		if session.profile["mesh"]["construction"] != "mply-unsorted-strict":
			meshArgs["animationSource"] = makeAnimationSelectionSource(runtime, session.profile)
		dialog = runtime.openOptionsDialogImportWindow(None, None, meshArgs)
		dialog.path = runtime.rapi.getInputName()
		dialog.createMeshWindow()

		while runtime.dialogOptions.motDialog and runtime.dialogOptions.motDialog.isOpen:
			mlDialog = runtime.dialogOptions.motDialog
			try:
				mlDialog.createMotlistWindow()
			finally:
				mlDialog.isOpen = False
				if mlDialog.selectionOnly:
					runtime.sGameName = meshGame
					runtime.dialogOptions.dialog = dialog
					runtime.dialogOptions.currentDir = dialog.currentDir
			if dialog.isOpen:
				runtime.dialogOptions.currentDir = dialog.currentDir
				dialog.createMeshWindow()

		if not dialog.isCancelled:
			loaded = loadSelectedMeshes(runtime, session, dialog)
			if loaded is None:
				return 0
			construction_rule, pragmataStats = loaded
			mdl = constructImportedModel(runtime, construction_rule)
			if mdl is None:
				return 0
		else:
			mdl = runtime.NoeModel()

		doLoadAnims = (runtime.dialogOptions.motDialog and runtime.dialogOptions.motDialog.loadItems and not runtime.dialogOptions.motDialog.isCancelled)
		mlDialog = runtime.dialogOptions.motDialog
		if mlDialog and mlDialog.selectionOnly:
			doLoadAnims = bool(mlDialog.selectedActions) and not mlDialog.isCancelled and not dialog.isCancelled
		if doLoadAnims:
			attachSelectedAnimations(runtime, mdl, mlDialog, dialog.pak.fullBoneList, "mesh")
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
