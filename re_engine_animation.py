"""Animation implementation bound to one plugin runtime."""

import json
import os
import copy
import re_engine_common as re_common
import struct
from re_engine_config import (
	PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY,
	PRAGMATA_MOTLIST_1057_MTRE_ONLY_CAPABILITY,
	PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY,
)
from re_engine_types import (
	MeshProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'NoeBone',
	'NoeKeyFramedAnim',
	'NoeKeyFramedBone',
	'NoeKeyFramedValue',
	'NoeModel',
	'NoeQuat',
	'NoeVec3',
	'PragmataMotlistSelectionMotion',
	'PragmataMotlistSelectionSource',
	'_buildPragmataMotlistBones',
	'_buildPragmataMotlistKeyFramedBones',
	'_formatPragmataMotlistRate',
	'_openMotlistSelectionDialog',
	'_printPragmataMotlistStats',
	'cleanBoneName',
	'detectPragmataMotlistCapability',
	'dialogOptions',
	'fDefaultMeshScale',
	'getChildBones',
	'hash_wide',
	'noesis',
	'openOptionsDialogImportWindow',
	'rapi',
	'sGameName',
)


def bind(runtime):
	def detectPragmataMotlistCapability(data, path):
		if not path.lower().endswith(".motlist.1057"):
			return None
		exact_error = None
		try:
			re_common.parse_pragmata_motlist_1057_exact(
				data, path, error_type=MeshProfileError)
			return PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY
		except MeshProfileError as caught:
			exact_error = caught
		try:
			profile = re_common.parse_pragmata_motlist_1057_multi(
				data, path, error_type=MeshProfileError)
		except MeshProfileError:
			if (len(data) >= 0x3C and
					struct.unpack_from("<I", data, 0x38)[0] == 1):
				raise exact_error
			raise
		counts = profile["counts"]
		if counts["mot"]:
			return PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY
		if counts["mtre"]:
			return PRAGMATA_MOTLIST_1057_MTRE_ONLY_CAPABILITY
		raise MeshProfileError("unsupported-motlist-content:empty")

	def _buildPragmataMotlistBones(bone_records):
		bones = []
		model_matrices = []
		for index, bone_data in enumerate(bone_records):
			parent_index = bone_data["parent_index"]
			if parent_index is not None and parent_index >= index:
				raise MeshProfileError("structural-profile-mismatch:bone-parent")
			local_matrix = runtime.NoeQuat(
				bone_data["local_rotation"]).transpose().toMat43()
			local_scale = bone_data["local_scale"]
			local_matrix[0] = local_matrix[0] * local_scale[0]
			local_matrix[1] = local_matrix[1] * local_scale[1]
			local_matrix[2] = local_matrix[2] * local_scale[2]
			local_matrix[3] = runtime.NoeVec3(
				bone_data["local_translation"]) * runtime.fDefaultMeshScale
			model_matrix = local_matrix
			if parent_index is not None:
				model_matrix = local_matrix * model_matrices[parent_index]
			model_matrices.append(model_matrix)
			bones.append(runtime.NoeBone(
				bone_data["index"], bone_data["name"], model_matrix, None,
				-1 if parent_index is None else parent_index))
		return bones

	def _buildPragmataMotlistKeyFramedBones(tracks, frame_rate, bone_count):
		keyframed_bones = []
		keyframed_by_index = {}
		component_keys = set()
		skipped_external = 0
		for track in tracks:
			bone_index = track["bone_index"]
			if bone_index is None:
				if track.get("binding_status") != "external-skeleton-required":
					raise MeshProfileError("structural-profile-mismatch:track-binding")
				skipped_external += 1
				continue
			if bone_index < 0 or bone_index >= bone_count:
				raise MeshProfileError("structural-profile-mismatch:track-bone-index")
			component_key = (bone_index, track["kind"])
			if component_key in component_keys:
				raise MeshProfileError("structural-profile-mismatch:duplicate-track-component")
			component_keys.add(component_key)
			keyframed_bone = keyframed_by_index.get(bone_index)
			if keyframed_bone is None:
				keyframed_bone = runtime.NoeKeyFramedBone(bone_index)
				keyframed_by_index[bone_index] = keyframed_bone
				keyframed_bones.append(keyframed_bone)
			values = []
			for key_time, value in zip(track["times"], track["values"]):
				if track["kind"] == "translation":
					converted = runtime.NoeVec3(value) * runtime.fDefaultMeshScale
				elif track["kind"] == "rotation":
					converted = runtime.NoeQuat(value).transpose()
				elif track["kind"] == "scale":
					converted = runtime.NoeVec3(value)
				else:
					raise MeshProfileError("unsupported-track-kind:" + track["kind"])
				values.append(runtime.NoeKeyFramedValue(
					key_time / float(frame_rate), converted))
			if track["kind"] == "translation":
				keyframed_bone.setTranslation(
					values, runtime.noesis.NOEKF_TRANSLATION_VECTOR_3)
			elif track["kind"] == "rotation":
				keyframed_bone.setRotation(
					values, runtime.noesis.NOEKF_ROTATION_QUATERNION_4)
			else:
				keyframed_bone.setScale(values, runtime.noesis.NOEKF_SCALE_VECTOR_3)
		return keyframed_bones, skipped_external

	def buildPragmataMotlist1057Model(data, path):
		decoded = re_common.decode_pragmata_motlist_1057_exact(
			data, path, error_type=MeshProfileError)
		bones = runtime._buildPragmataMotlistBones(decoded["bones"])

		keyframed_bones, _skipped_external = runtime._buildPragmataMotlistKeyFramedBones(
			decoded["tracks"], decoded["action"]["frame_rate"], len(bones))

		anim = runtime.NoeKeyFramedAnim(
			decoded["action"]["name"], bones, keyframed_bones,
			float(decoded["action"]["frame_rate"]))
		model = runtime.NoeModel()
		model.setBones(bones)
		model.setAnims([anim])
		runtime.rapi.setPreviewOption(
			"setAnimSpeed", str(float(decoded["action"]["frame_rate"])))
		runtime._printPragmataMotlistStats(
			PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY, bones, [anim],
			len(decoded["tracks"]), 0, 0)
		return model

	def _formatPragmataMotlistRate(rate):
		integer_rate = int(rate)
		return str(integer_rate) if integer_rate == rate else str(rate)

	def _printPragmataMotlistStats(capability, bones, animations,
									bound_tracks, skipped_external, skipped_mtre):
		print("RE_MOTLIST_STATS_JSON:" + json.dumps({
			"schema": "noesis-pragmata-motlist-stats/v1",
			"capability": capability,
			"model_count": 1,
			"bone_count": len(bones),
			"animation_count": len(animations),
			"keyframed_bone_count": sum(
				len(animation.kfBones) for animation in animations),
			"bound_track_count": bound_tracks,
			"skipped_external_track_count": skipped_external,
			"skipped_mtre_entry_count": skipped_mtre,
		}, sort_keys=True))

	class PragmataMotlistSelectionMotion:
		def __init__(self, action):
			self.slot_index = action["slot_index"]
			self.motion_id = action["motion_id"]
			self.action_name = action["name"]
			self.frameCount = action["frame_count"]
			self.motionID = self.motion_id
			frame_count = int(self.frameCount)
			frame_text = (str(frame_count) if frame_count == self.frameCount
						  else str(self.frameCount))
			self.base_name = "%s (%s frames) ID: %s" % (
				self.action_name, frame_text, str(self.motion_id))
			self.name = self.base_name

	class PragmataMotlistSelectionSource:
		# Contract consumed by the shared animation selection window.
		gameName = "PRAGMATA"
		fileSuffix = ".motlist.1057"

		def __init__(self, decoded, path):
			self.decoded = decoded
			self.path = path
			self.name = decoded.get("motlist", {}).get("name") or os.path.basename(
				path).split(".motlist.")[0]
			self.mots = [
				runtime.PragmataMotlistSelectionMotion(action)
				for action in decoded["actions"]
			]
			base_name_counts = {}
			for motion in self.mots:
				base_name_counts[motion.base_name] = (
					base_name_counts.get(motion.base_name, 0) + 1)
			for motion in self.mots:
				if base_name_counts[motion.base_name] > 1:
					motion.name += " [slot %d]" % motion.slot_index
			self.all_label = "[ALL] - " + self.name
			self._slot_by_name = dict(
				(motion.name, motion.slot_index) for motion in self.mots)

		@classmethod
		def load(cls, path):
			data = runtime.rapi.loadIntoByteArray(path)
			capability = runtime.detectPragmataMotlistCapability(data, path)
			if capability == PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY:
				decoded = re_common.decode_pragmata_motlist_1057_multi(
					data, path, error_type=MeshProfileError)
			elif capability == PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY:
				exact = re_common.decode_pragmata_motlist_1057_exact(
					data, path, error_type=MeshProfileError)
				action = copy.copy(exact["action"])
				action["slot_index"] = 0
				action["tracks"] = exact["tracks"]
				decoded = {
					"motlist": {
						"name": os.path.basename(path).split(".motlist.")[0],
					},
					"bones": exact["bones"],
					"actions": [action],
					"skipped_entries": [],
				}
			elif capability == PRAGMATA_MOTLIST_1057_MTRE_ONLY_CAPABILITY:
				decoded = {
					"motlist": {
						"name": os.path.basename(path).split(".motlist.")[0],
					},
					"bones": [],
					"actions": [],
					"skipped_entries": [],
				}
			else:
				raise MeshProfileError("unsupported-motlist-capability")
			return cls(decoded, path)

		def selection_for_slot(self, slot_index):
			return {"path": self.path, "decoded": self.decoded, "slot_index": slot_index}

		def slots_for_items(self, items):
			if self.all_label in items:
				return [motion.slot_index for motion in self.mots]
			slots = []
			for item in items:
				if item not in self._slot_by_name:
					raise MeshProfileError(
						"structural-profile-mismatch:animation-selection")
				slot_index = self._slot_by_name[item]
				if slot_index not in slots:
					slots.append(slot_index)
			return slots

	def _mapAnimationTracks(tracks, source_bones, mesh_bones):
		# Keep the MESH bind pose and weight indices; only remap animation tracks.
		by_hash = {}
		for index, bone in enumerate(mesh_bones):
			bone_hash = runtime.hash_wide(runtime.cleanBoneName(bone.name), True)
			if bone_hash in by_hash:
				raise MeshProfileError("animation-binding-ambiguous-bone")
			by_hash[bone_hash] = index
		source_by_hash = dict((bone["hash"], bone) for bone in source_bones)
		mapped = []
		for track in tracks:
			mapped_track = dict(track)
			target_index = by_hash.get(track["bone_hash"])
			source = source_by_hash.get(track["bone_hash"])
			if target_index is not None and source is not None:
				parent = source["parent_index"]
				target_parent = mesh_bones[target_index].parentIndex
				if parent is None and target_parent != -1:
					# Mounted local roots (e.g. facial clips), as in the legacy loader.
					target_index = None
				elif parent is not None:
					mapped_parent = by_hash.get(source_bones[parent]["hash"])
					if mapped_parent != target_parent:
						raise MeshProfileError("animation-binding-parent")
			mapped_track["bone_index"] = target_index
			mapped_track["binding_status"] = (
				"bound" if target_index is not None else "external-skeleton-required")
			mapped.append(mapped_track)
		return mapped

	def buildPragmataMotlist1057MultiModel(
			data, path, selected_slots=None, decoded=None, mesh_bones=None):
		if decoded is None:
			decoded = re_common.decode_pragmata_motlist_1057_multi(
				data, path, error_type=MeshProfileError)
		selected_rows = []
		if selected_slots is None:
			selected_rows = [(decoded, action) for action in decoded["actions"]]
		else:
			record_input = selected_slots and isinstance(selected_slots[0], dict)
			selections = selected_slots if record_input else [
				{"decoded": decoded, "path": path, "slot_index": slot}
				for slot in selected_slots]
			seen_actions = set()
			for selection in selections:
				selection_decoded = selection.get("decoded")
				slot_index = selection.get("slot_index")
				selection_path = selection.get("path")
				if selection_decoded is None or (record_input and selection_path is None):
					raise MeshProfileError(
						"structural-profile-mismatch:animation-selection")
				actions_by_slot = dict(
					(action["slot_index"], action)
					for action in selection_decoded["actions"])
				identity = (selection_path, slot_index)
				if identity in seen_actions or slot_index not in actions_by_slot:
					raise MeshProfileError(
						"structural-profile-mismatch:animation-selection")
				seen_actions.add(identity)
				selected_rows.append(
					(selection_decoded, actions_by_slot[slot_index]))
		selected_actions = [row[1] for row in selected_rows]
		bone_records = selected_rows[0][0]["bones"] if selected_rows else decoded["bones"]
		for selection_decoded, _action in selected_rows:
			if mesh_bones is None and selection_decoded["bones"] != bone_records:
				raise MeshProfileError(
					"structural-profile-mismatch:animation-selection-skeleton")
		bones = (runtime._buildPragmataMotlistBones(bone_records)
				 if mesh_bones is None else mesh_bones)
		animations = []
		skipped_external = 0
		selected_track_count = 0
		for selection_decoded, action in selected_rows:
			tracks = action["tracks"]
			if mesh_bones is not None:
				tracks = _mapAnimationTracks(tracks, selection_decoded["bones"], mesh_bones)
			selected_track_count += len(tracks)
			keyframed_bones, action_skipped = (
				runtime._buildPragmataMotlistKeyFramedBones(
					tracks, action["frame_rate"], len(bones)))
			skipped_external += action_skipped
			animations.append(runtime.NoeKeyFramedAnim(
				action["name"], bones, keyframed_bones,
				float(action["frame_rate"])))

		if mesh_bones is not None and selected_track_count == skipped_external:
			raise MeshProfileError("animation-binding-no-matching-tracks")
		model = runtime.NoeModel()
		model.setBones(bones)
		model.setAnims(animations)
		selected_sources = []
		for selection_decoded, _action in selected_rows:
			if selection_decoded not in selected_sources:
				selected_sources.append(selection_decoded)
		mtre_slots = []
		for selection_decoded in selected_sources:
			mtre_slots.extend(
				entry["slot_index"]
				for entry in selection_decoded.get("skipped_entries", []))
		if mtre_slots:
			print("PRAGMATA MOTLIST: skipped MTRE slots: " +
				  ", ".join(str(value) for value in mtre_slots))
		if skipped_external:
			print("PRAGMATA MOTLIST: skipped external-skeleton tracks: " +
				  str(skipped_external))
		rates = sorted(set(action["frame_rate"] for action in selected_actions))
		if len(rates) == 1:
			runtime.rapi.setPreviewOption("setAnimSpeed", str(float(rates[0])))
		elif rates:
			print("PRAGMATA MOTLIST: animation FPS values: " +
				  ", ".join(runtime._formatPragmataMotlistRate(rate) for rate in rates))
		runtime._printPragmataMotlistStats(
			PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY, bones, animations,
			selected_track_count - skipped_external,
			skipped_external, len(mtre_slots))
		return model

	def getGlobalMatrix(noebone, bonesList): #doesnt work 100%?
		mat = noebone.getMatrix()
		parent = bonesList[noebone.parentIndex] if noebone.parentIndex != -1 else None
		if parent:
			mat *= parent.getMatrix().inverse()
		return mat.transpose()

	def getChildBones(parentBone, boneList, doRecurse=False):
		children = []
		for bone in boneList:
			if bone.parentName == parentBone.name and bone not in children:
				children.append(bone)
				if doRecurse:
					children.extend(runtime.getChildBones(bone, boneList, True))
				break
		return children

	def cleanBoneName(name):
		splitted = name.split(":", 1)
		return splitted[len(splitted)-1]

	def generateBoneMap(mdl):
		usedBones = [False for bone in mdl.bones]
		boneNames = [bone.name.lower() for bone in mdl.bones]
		boneMapCount = 0
		for bone in mdl.bones:
			if bone.parentIndex != -1 and bone.parentName:
				bone.parentIndex = boneNames.index(bone.parentName.lower())
		for mesh in mdl.meshes:
			for weightList in mesh.weights:
				for idx in weightList.indices:
					usedBones[idx] = True
		for i, bone in enumerate(mdl.bones):
			bone.name = runtime.cleanBoneName(bone.name)
			if usedBones[i]:
				bone.name = "b" + "{:03d}".format(boneMapCount) + ":" + bone.name
				boneMapCount += 1
		for bone in mdl.bones:
			if bone.parentIndex != -1:
				bone.parentName = mdl.bones[bone.parentIndex].name

	def collapseBones(mdl, threshold=0.01):
		print("Collapsing skeleton")
		newBones = []
		newBoneMap = []
		newBoneMapNames = []
		allBoneNames = [runtime.cleanBoneName(bone.name).lower() for bone in mdl.bones]
		for i, bone in enumerate(mdl.bones):
			boneMapId = i
			name = allBoneNames[i].split(".", 1)[0]
			try:
				sameBoneIdx = allBoneNames.index(name)
			except ValueError:
				print("ERROR:", name, " not in bones list!")
				continue
			#if sameBoneIdx != i and (getGlobalMatrix(mdl.bones[sameBoneIdx], mdl.bones)[3] - getGlobalMatrix(bone, mdl.bones)[3]).length() < threshold * fDefaultMeshScale:
			if sameBoneIdx != i: # and (mdl.bones[sameBoneIdx].getMatrix()[3] - bone.getMatrix()[3]).length() < threshold * fDefaultMeshScale:
				boneMapId = sameBoneIdx
			elif bone.parentIndex != bone.index:
				newBones.append(bone)
			newBoneMapNames.append(mdl.bones[boneMapId].name.lower())
		for i, bone in enumerate(newBones):
			bone.index = i
			if bone.parentIndex != -1:
				mat = bone.getMatrix() * mdl.bones[bone.parentIndex].getMatrix().inverse()
				bone.parentName = newBoneMapNames[bone.parentIndex]
				bone.setMatrix(mat * mdl.bones[allBoneNames.index(bone.parentName)].getMatrix()) #relocate bone
			elif i > 0:
				bone.parentName = newBones[0].name
		newBoneNames = [bone.name.lower() for bone in newBones]
		for i, boneName in enumerate(newBoneMapNames):
			newBoneMap.append(newBoneNames.index(boneName))
		for mesh in mdl.meshes:
			for weightList in mesh.weights:
				weightList.indices = list(weightList.indices)
				for i, idx in enumerate(weightList.indices):
					weightList.indices[i] = newBoneMap[idx]
		'''for anim in mdl.anims:
			anim.bones = newBones
			for kfBone in anim.kfBones:
				kfBone.boneIndex = newBoneMap[kfBone.boneIndex]'''

		mdl.setBones(newBones)

	def _openMotlistSelectionDialog(source):
		# Shared state is owned by runtime.
		previous_game_name = runtime.sGameName
		previous_current_dir = runtime.dialogOptions.currentDir
		previous_dialog = runtime.dialogOptions.dialog
		try:
			dialog = runtime.openOptionsDialogImportWindow(None, None, {
				"motlist": source,
				"isMotlist": True,
				"selectionSource": type(source),
			})
			dialog.createMotlistWindow()
			return dialog
		finally:
			runtime.sGameName = previous_game_name
			runtime.dialogOptions.currentDir = previous_current_dir
			runtime.dialogOptions.dialog = previous_dialog

	def selectPragmataMotlistActions(decoded, path):
		source = runtime.PragmataMotlistSelectionSource(decoded, path)
		dialog = runtime._openMotlistSelectionDialog(source)
		if dialog.isCancelled or not dialog.selectedActions:
			return None
		return dialog.selectedActions

	def shouldPromptPragmataMotlistSelection():
		optWasInvoked = getattr(runtime.noesis, "optWasInvoked", None)
		return not (optWasInvoked and (
			optWasInvoked("-b") or optWasInvoked("-noprompt")))

	return (
		detectPragmataMotlistCapability,
		_buildPragmataMotlistBones,
		_buildPragmataMotlistKeyFramedBones,
		buildPragmataMotlist1057Model,
		_formatPragmataMotlistRate,
		_printPragmataMotlistStats,
		PragmataMotlistSelectionMotion,
		PragmataMotlistSelectionSource,
		buildPragmataMotlist1057MultiModel,
		getGlobalMatrix,
		getChildBones,
		cleanBoneName,
		generateBoneMap,
		collapseBones,
		_openMotlistSelectionDialog,
		selectPragmataMotlistActions,
		shouldPromptPragmataMotlistSelection,
	)
