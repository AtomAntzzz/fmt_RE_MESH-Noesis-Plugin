"""Gui implementation bound to one plugin runtime."""

import os
import time
from re_engine_config import (
	formats,
	fullGameNames,
	gamesList,
	texFormatNames,
)
from re_engine_types import (
	DoubleClickTimer,
	MeshProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'LoadExtractedDir',
	'bNoImportMenu',
	'dialogOptions',
	'doConvertMatsForBlender',
	'fDefaultMeshScale',
	'findRootDir',
	'getSameExtFilesInDir',
	'iListboxSize',
	'motlistFile',
	'noesis',
	'noewin',
	'openOptionsDialogImportWindow',
	'rapi',
	'sGameName',
)


def bind(runtime):
	class DialogOptions:
		def __init__(self):
			self.doLoadTex = False
			self.doConvertTex = True
			self.doLODs = False
			self.loadAllTextures = False
			self.reparentHelpers = True
			self.doCreateBoneMap = True
			self.doForceCenter = False
			self.doSync = True
			self.doForceMergeAnims = False
			self.doConvertMatsForBlender = runtime.doConvertMatsForBlender
			self.width = 600
			self.height = 810 - (380 - runtime.iListboxSize)
			self.texDicts = None
			self.gameName = runtime.sGameName
			self.currentDir = ""
			self.motDialog = None
			self.dialog = None

	runtime.dialogOptions = DialogOptions()

	class openOptionsDialogImportWindow:

		def __init__(self, width=runtime.dialogOptions.width, height=runtime.dialogOptions.height, args={}):
			# Shared state is owned by runtime.

			self.width = width
			self.height = height
			self.args = args
			self.selectionSource = args.get("selectionSource")
			self.selectionOnly = self.selectionSource is not None
			if self.selectionOnly:
				runtime.sGameName = self.selectionSource.gameName
			self.pak = args.get("motlist") or args.get("mesh")
			self.isMotlist = args.get("isMotlist")
			self.path = self.pak.path if self.pak else runtime.rapi.getInputName()
			self.loadItems = [runtime.rapi.getLocalFileName(self.path)] if not self.isMotlist else []
			self.fullLoadItems = [self.path] if not self.isMotlist else []
			if self.isMotlist:
				if (not self.selectionOnly and runtime.dialogOptions.motDialog and
						runtime.dialogOptions.motDialog.pak):
					self.pak = runtime.dialogOptions.motDialog.pak
					self.path = runtime.dialogOptions.motDialog.pak.path
					self.loadItems = runtime.dialogOptions.motDialog.loadItems
					self.fullLoadItems = runtime.dialogOptions.motDialog.fullLoadItems
				if self.pak:
					self.motItems = [mot.name for mot in self.pak.mots]
			self.name = runtime.rapi.getLocalFileName(self.path)
			self.localDir = runtime.rapi.getDirForFilePath(self.path)
			if self.selectionOnly:
				runtime.dialogOptions.currentDir = self.localDir
			else:
				runtime.dialogOptions.currentDir = runtime.dialogOptions.currentDir or self.localDir
			self.currentDir = runtime.dialogOptions.currentDir
			self.localRoot = runtime.findRootDir(self.path)
			self.baseDir = runtime.LoadExtractedDir(runtime.sGameName)
			self.allFiles = []
			self.pakFiles = []
			self.subDirs = []
			self.motItems = []
			self.loadedMlists = {}
			self.pakIdx = 0
			self.baseIdx = -1
			self.loadIdx = 0
			self.dirIdx = 0
			self.gameIdx = 0
			self.localIdx = 0
			self.clicker = DoubleClickTimer(name="", idx=0, timer=0)
			runtime.dialogOptions.dialog = self
			self.isOpen = True
			self.isCancelled = False
			self.selectedActions = []
			self.selectionSources = {}
			if self.selectionOnly and self.pak:
				self.selectionSources[self.pak.path] = self.pak
				self.motItems = [mot.name for mot in self.pak.mots]
			elif self.isMotlist and runtime.dialogOptions.motDialog:
				self.motItems = runtime.dialogOptions.motDialog.motItems


			previous = runtime.dialogOptions.motDialog
			if (self.isMotlist and self.selectionOnly and previous and
					previous.selectionSource is self.selectionSource and not args.get("motlist")):
				self.pak = previous.pak
				self.loadItems = list(previous.loadItems)
				self.fullLoadItems = list(previous.fullLoadItems)
				self.selectionSources = dict(previous.selectionSources)
				self.motItems = list(previous.motItems)
				self.currentDir = previous.currentDir
				runtime.dialogOptions.currentDir = self.currentDir

		def openMotlistDialogButton(self, noeWnd, controlId, wParam, lParam):
			if not runtime.dialogOptions.motDialog or not runtime.dialogOptions.motDialog.isOpen:
				runtime.dialogOptions.motDialog = runtime.openOptionsDialogImportWindow(None, None, {
					"isMotlist": True,
					"selectionSource": self.args.get("animationSource"),
				})
				self.noeWnd.closeWindow()
				#dialogOptions.motDialog.createMotlistWindow()

		def clickLoadButton(self):
			if self.selectionOnly:
				selected_actions = self._resolveSelectionItems()
				if not selected_actions:
					return
				self.selectedActions = selected_actions
				self.isOpen = False
				self.noeWnd.closeWindow()
				return
			self.isOpen = False
			if self.isMotlist:
				self.loadedMlists = {}
				bones = self.pak.bones
				totalFrames = self.pak.totalFrames
				mdlBoneNames = [bone.name for bone in bones]
				for path in self.fullLoadItems:
					if ".motlist." in path.lower() and path not in self.loadedMlists and runtime.rapi.checkFileExists(path):
						self.loadedMlists[path] = runtime.motlistFile(runtime.rapi.loadIntoByteArray(path), path)
						self.loadedMlists[path].bones = bones
						self.loadedMlists[path].readBoneHeaders(self.loadItems)
				for i, motName in enumerate(self.loadItems):
					if motName.find("[ALL] - ") == 0:
						fullPath = self.fullLoadItems[i]
						for mot in self.loadedMlists[fullPath].mots:
							if mot.name not in self.loadItems:
								self.loadItems.append(mot.name)
								self.fullLoadItems.append(fullPath)
			self.noeWnd.closeWindow()

		def _resolveSelectionItems(self):
			if len(self.loadItems) != len(self.fullLoadItems):
				raise MeshProfileError(
					"structural-profile-mismatch:animation-selection")
			selections = []
			seen = set()
			for item, path in zip(self.loadItems, self.fullLoadItems):
				source = self.selectionSources.get(path)
				if source is None:
					raise MeshProfileError(
						"structural-profile-mismatch:animation-selection")
				for slot_index in source.slots_for_items([item]):
					identity = (path, slot_index)
					if identity not in seen:
						seen.add(identity)
						selections.append(source.selection_for_slot(slot_index))
			return selections

		def openOptionsButtonLoadEntry(self, noeWnd, controlId, wParam, lParam):
			self.clickLoadButton()

		def openOptionsButtonCancel(self, noeWnd, controlId, wParam, lParam):
			self.isCancelled = True
			self.isOpen = False
			self.noeWnd.closeWindow()

		def openOptionsButtonParentDir(self, noeWnd, controlId, wParam, lParam):
			if self.localIdx == 0:
				self.localRoot = os.path.dirname(self.localRoot)
			else:
				self.baseDir = os.path.dirname(self.baseDir)
			self.setDirList()
			self.setPakList()
			if self.subDirs:
				self.dirList.selectString(self.subDirs[0])

		def pressLoadListUpButton(self, noeWnd, controlId, wParam, lParam):
			selIdx = self.loadList.getSelectionIndex()
			if selIdx > 0:
				self.loadItems[selIdx], self.loadItems[selIdx-1], self.fullLoadItems[selIdx], self.fullLoadItems[selIdx-1] = self.loadItems[selIdx-1], self.loadItems[selIdx], self.fullLoadItems[selIdx-1], self.fullLoadItems[selIdx]
				for item in self.loadItems: self.loadList.removeString(item)
				for item in self.loadItems: self.loadList.addString(item)
				self.loadList.selectString(self.loadItems[selIdx-1])

		def pressLoadListDownButton(self, noeWnd, controlId, wParam, lParam):
			selIdx = self.loadList.getSelectionIndex()
			if selIdx != -1 and selIdx < len(self.loadItems)-1:
				self.loadItems[selIdx], self.loadItems[selIdx+1], self.fullLoadItems[selIdx], self.fullLoadItems[selIdx+1] = self.loadItems[selIdx+1], self.loadItems[selIdx], self.fullLoadItems[selIdx+1], self.fullLoadItems[selIdx]
				for item in self.loadItems: self.loadList.removeString(item)
				for item in self.loadItems: self.loadList.addString(item)
				self.loadList.selectString(self.loadItems[selIdx+1])

		def selectBaseListItem(self, noeWnd, controlId, wParam, lParam):
			self.baseIdx = self.baseList.getSelectionIndex()
			runtime.dialogOptions.baseSkeleton = self.baseList.getStringForIndex(self.baseIdx)

		def selectMotlistItem(self, noeWnd, controlId, wParam, lParam):
			self.motIdx = self.motLoadList.getSelectionIndex()
			if self.clicker.name == "motList" and self.motIdx == self.clicker.idx and time.time() - self.clicker.timer < 0.25:
				addedName = self.motLoadList.getStringForIndex(self.motIdx)
				is_new_item = addedName not in self.loadItems
				if self.selectionOnly:
					is_new_item = (addedName, self.pak.path) not in zip(
						self.loadItems, self.fullLoadItems)
				if is_new_item:
					self.loadItems.append(addedName)
					self.fullLoadItems.append(self.pak.path)
					self.loadList.addString(addedName)
			self.clicker = DoubleClickTimer(name="motList", idx=self.motIdx, timer=time.time())

		def _loadSelectionPak(self, path):
			if path not in self.selectionSources:
				self.selectionSources[path] = self.selectionSource.load(path)
			return self.selectionSources[path]

		def selectPakListItem(self, noeWnd, controlId, wParam, lParam):
			self.pakIdx = self.pakList.getSelectionIndex()
			if self.clicker.name == "pakList" and self.pakIdx == self.clicker.idx and time.time() - self.clicker.timer < 0.25:
				path = runtime.dialogOptions.currentDir + "\\" + self.pakList.getStringForIndex(self.pakIdx)
				if self.pakIdx == 0: #parent directory
					if runtime.dialogOptions.currentDir[-1:] == "\\":
						runtime.dialogOptions.currentDir = os.path.dirname(runtime.dialogOptions.currentDir)
					lastDir = runtime.rapi.getLocalFileName(runtime.dialogOptions.currentDir)
					runtime.dialogOptions.currentDir = os.path.dirname(runtime.dialogOptions.currentDir)
					self.setPakList()
					self.pakList.selectString(lastDir)
				elif self.pakIdx <= len(self.subDirs):
					runtime.dialogOptions.currentDir += "\\" + self.pakList.getStringForIndex(self.pakIdx)
					self.setPakList()
				elif self.isMotlist:
					if self.selectionOnly:
						self.pak = self._loadSelectionPak(path)
					else:
						self.pak = runtime.motlistFile(runtime.rapi.loadIntoByteArray(path), path)
					self.setMotLoadList([mot.name for mot in self.pak.mots])
				elif self.pakList.getStringForIndex(self.pakIdx) not in self.loadItems:
					self.loadItems.append(self.pakList.getStringForIndex(self.pakIdx))
					self.fullLoadItems.append(path)
					self.loadList.addString(self.pakList.getStringForIndex(self.pakIdx))
					#self.fullLoadItems = [x for _, x in sorted(zip(self.loadItems, self.fullLoadItems))]
					#self.loadItems = sorted(self.loadItems)
			self.clicker = DoubleClickTimer(name="pakList", idx=self.pakIdx, timer=time.time())
			self.currentDir = runtime.dialogOptions.currentDir

		def selectLoadListItem(self, noeWnd, controlId, wParam, lParam):
			self.loadIdx = self.loadList.getSelectionIndex()
			if self.clicker.name == "loadList" and self.loadIdx == self.clicker.idx and time.time() - self.clicker.timer < 0.25 and (self.isMotlist or self.loadItems[self.loadIdx] != self.name):
				old_load_items = list(self.loadItems)
				if not self.selectionOnly:
					self.loadList.removeString(self.loadItems[self.loadIdx])
				del self.loadItems[self.loadIdx]
				if not self.isMotlist or self.selectionOnly:
					del self.fullLoadItems[self.loadIdx]
				if self.selectionOnly:
					for item in old_load_items:
						self.loadList.removeString(item)
					for item in self.loadItems:
						self.loadList.addString(item)
				self.loadIdx = self.loadIdx if self.loadIdx < len(self.loadItems) else self.loadIdx - 1
				if abs(self.loadIdx) < len(self.loadItems):
					self.loadList.selectString(self.loadItems[self.loadIdx])
			self.clicker = DoubleClickTimer(name="loadList", idx=self.loadIdx, timer=time.time())
			self.currentDir = runtime.dialogOptions.currentDir

		def selectGameBoxItem(self, noeWnd, controlId, wParam, lParam):
			# Shared state is owned by runtime.
			if self.gameIdx != self.gameBox.getSelectionIndex():
				self.gameIdx = self.gameBox.getSelectionIndex()
				restOfPath = runtime.dialogOptions.currentDir.replace(self.baseDir, "").replace(formats[runtime.sGameName]["nDir"]+"\\", "")
				runtime.sGameName = gamesList[self.gameIdx]
				self.baseDir = runtime.LoadExtractedDir(runtime.sGameName) #BaseDirectories[sGameName]
				if self.localBox.getStringForIndex(self.localIdx) == "Base Directory":
					runtime.dialogOptions.currentDir = self.baseDir
					if restOfPath and os.path.isdir(self.baseDir + restOfPath):
						runtime.dialogOptions.currentDir = self.baseDir + restOfPath
					self.setPakList()
			self.currentDir = runtime.dialogOptions.currentDir

		def selectLocalBoxItem(self, noeWnd, controlId, wParam, lParam):
			if self.localIdx != self.localBox.getSelectionIndex():
				self.localIdx = self.localBox.getSelectionIndex()
				restOfPath = runtime.dialogOptions.currentDir.replace(self.localRoot, "").replace(self.baseDir, "").replace(formats[runtime.sGameName]["nDir"]+"\\", "")
				if self.localBox.getStringForIndex(self.localIdx) == "Base Directory":
					runtime.dialogOptions.currentDir = self.baseDir
					if restOfPath and os.path.isdir(self.baseDir + restOfPath):
						runtime.dialogOptions.currentDir = self.baseDir + restOfPath
				else:
					runtime.dialogOptions.currentDir = os.path.dirname(self.path)
					if restOfPath and os.path.isdir(self.localRoot + restOfPath):
						runtime.dialogOptions.currentDir = self.localRoot + restOfPath
				self.setPakList()
			self.currentDir = runtime.dialogOptions.currentDir

		def setGameBox(self, list_object=None, current_item=None):
			for i, name in enumerate(fullGameNames):
				self.gameBox.addString(name)
			self.gameBox.selectString(fullGameNames[gamesList.index(runtime.sGameName)])
			self.gameIdx = self.gameBox.getSelectionIndex()

		def setLocalBox(self, list_object=None, current_item=None):
			for name in ["Local Folder", "Base Directory"]:
				self.localBox.addString(name)
			self.localBox.selectString("Local Folder")
			self.localIdx = self.localBox.getSelectionIndex()

		def checkLoadTexCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.doLoadTex = not runtime.dialogOptions.doLoadTex
			self.loadTexCheckbox.setChecked(runtime.dialogOptions.doLoadTex)

		def checkLODsCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.doLODs = not runtime.dialogOptions.doLODs
			self.LODsCheckbox.setChecked(runtime.dialogOptions.doLODs)

		def checkConvTexCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.doConvertTex = not runtime.dialogOptions.doConvertTex
			self.convTexCheckbox.setChecked(runtime.dialogOptions.doConvertTex)

		def checkFlipUVsCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.doFlipUVs = not runtime.dialogOptions.doFlipUVs
			self.flipUVsCheckbox.setChecked(runtime.dialogOptions.doFlipUVs)

		def checkLoadAllTexCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.loadAllTextures = not runtime.dialogOptions.loadAllTextures
			self.loadAllTexCheckbox.setChecked(runtime.dialogOptions.loadAllTextures)

		def checkReparentCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.reparentHelpers = not runtime.dialogOptions.reparentHelpers
			self.reparentCheckbox.setChecked(runtime.dialogOptions.reparentHelpers)

		def checkFCenterCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.doForceCenter = not runtime.dialogOptions.doForceCenter
			self.FCenterCheckbox.setChecked(runtime.dialogOptions.doForceCenter)

		def checkSyncCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.doSync = not runtime.dialogOptions.doSync
			self.syncCheckbox.setChecked(runtime.dialogOptions.doSync)

		def checkForceMergeCheckbox(self, noeWnd, controlId, wParam, lParam):
			runtime.dialogOptions.doForceMergeAnims = not runtime.dialogOptions.doForceMergeAnims
			self.forceMergeCheckbox.setChecked(runtime.dialogOptions.doForceMergeAnims)

		def setMotLoadList(self, motItems=[]):
			for name in self.motItems:
				self.motLoadList.removeString(name)
			self.motItems = []
			if motItems:
				motItems.insert(0, "[ALL] - " + self.pak.name)
				for name in motItems:
					self.motLoadList.addString(name)
				self.motItems = motItems
				self.motLoadList.selectString(self.motItems[0])

		def setLoadList(self, loadItems=[]):
			for item in self.loadItems:
				self.loadList.removeString(item)
			if loadItems:
				self.loadItems = loadItems
				for item in self.loadItems:
					self.loadList.addString(item)
				self.loadList.selectString(self.loadItems[0])
			else:
				self.loadItems = [self.name] if not self.isMotlist else []
				if self.loadItems:
					self.loadList.addString(self.loadItems[0])
			self.loadList.selectString((self.pak and self.pak.path) or runtime.rapi.getInputName())

		def setPakList(self):
			for name in self.allFiles:
				self.pakList.removeString(name)
			self.allFiles = [".."]
			self.pakFiles = []
			self.subDirs = []
			fmtKey = "mlistExt" if self.isMotlist else "modelExt"
			exts = [formatTbl[fmtKey] for gameName, formatTbl in formats.items()]
			for item in os.listdir(runtime.dialogOptions.currentDir):
				if os.path.isdir(os.path.join(runtime.dialogOptions.currentDir, item)):
					self.subDirs.append(item)
				is_matching_file = (
					os.path.isfile(os.path.join(runtime.dialogOptions.currentDir, item)) and
					"." in item and os.path.splitext(item)[1] in exts)
				if self.selectionOnly:
					is_matching_file = (
						os.path.isfile(os.path.join(runtime.dialogOptions.currentDir, item)) and
						item.lower().endswith(self.selectionSource.fileSuffix))
				if is_matching_file:
					self.pakFiles.append(item)
			self.subDirs = sorted(self.subDirs)
			self.pakFiles = sorted(self.pakFiles)
			self.allFiles.extend(self.subDirs)
			self.allFiles.extend(self.pakFiles)
			for item in self.allFiles:
				self.pakList.addString(item)
			if self.name in self.allFiles:
				self.pakIdx = self.allFiles.index(self.name)
				self.pakList.selectString(self.name)
			elif self.pak and runtime.rapi.getLocalFileName(self.pak.path) in self.allFiles:
				self.pakIdx = self.allFiles.index(runtime.rapi.getLocalFileName(self.pak.path))
				self.pakList.selectString(self.pakList.getStringForIndex(self.pakIdx))
			elif self.pakIdx < len(self.allFiles):
				self.pakList.selectString(self.pakList.getStringForIndex(self.pakIdx))
			else:
				self.pakIdx = 0
				self.pakList.selectString(self.pakList.getStringForIndex(0))
			self.currentDirEditBox.setText(runtime.dialogOptions.currentDir)

		def inputCurrentDirEditBox(self, noeWnd, controlId, wParam, lParam):
			text = self.currentDirEditBox.getText().lower()
			if text != runtime.dialogOptions.currentDir.lower() and os.path.exists(text):
				runtime.dialogOptions.currentDir = os.path.dirname(text) if os.path.isfile(text) else text
				self.currentDir = runtime.dialogOptions.currentDir
				self.setPakList()
				if os.path.isfile(text):
					lowerAllFiles = [name.lower() for name in self.allFiles]
					if runtime.rapi.getLocalFileName(text) in lowerAllFiles:
						self.pakList.selectString(self.pakList.getStringForIndex(lowerAllFiles.index(runtime.rapi.getLocalFileName(text))))
					if self.isMotlist and ".motlist" in text:
						if self.selectionOnly:
							self.pak = self._loadSelectionPak(text)
						else:
							self.pak = runtime.motlistFile(runtime.rapi.loadIntoByteArray(text), text)
						self.setMotLoadList([mot.name for mot in self.pak.mots])

		def inputGlobalScaleEditBox(self, noeWnd, controlId, wParam, lParam):
			# Shared state is owned by runtime.
			try:
				if self.globalScaleEditBox.getText():
					newScale = float(self.globalScaleEditBox.getText())
					if newScale:
						runtime.fDefaultMeshScale = newScale
			except ValueError:
				print("Non-numeric scale input, resetting to ", runtime.fDefaultMeshScale)
				self.globalScaleEditBox.setText(str(runtime.fDefaultMeshScale))

		def create(self, width=runtime.dialogOptions.width, height=runtime.dialogOptions.height):
			self.noeWnd = runtime.noewin.NoeUserWindow("RE Engine '.mesh' Plugin                                " + runtime.rapi.getLocalFileName(self.name), "HTRAWWindowClass", width, height)
			noeWindowRect = runtime.noewin.getNoesisWindowRect()
			if noeWindowRect:
				windowMargin = 100
				self.noeWnd.x = noeWindowRect[0] + windowMargin
				self.noeWnd.y = noeWindowRect[1] + windowMargin
			return self.noeWnd.createWindow()

		def createMotlistWindow(self, width=runtime.dialogOptions.width, height=800):

			if self.create(width, height):
				self.noeWnd.setFont("Futura", 14)

				self.noeWnd.createStatic("Motlist files from:", 5, 5, width-20, 20)
				index = self.noeWnd.createEditBox(5, 25, width-20, 45, runtime.dialogOptions.currentDir, self.inputCurrentDirEditBox) #EB
				self.currentDirEditBox = self.noeWnd.getControlByIndex(index)

				index = self.noeWnd.createListBox(5, 80, width-20, 160, self.selectPakListItem, runtime.noewin.LBS_NOTIFY | runtime.noewin.WS_VSCROLL | runtime.noewin.WS_BORDER) #LB
				self.pakList = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("Motions:", 5, 240, width-20, 20)
				index = self.noeWnd.createListBox(5, 260, width-20, 200, self.selectMotlistItem, runtime.noewin.LBS_NOTIFY | runtime.noewin.WS_VSCROLL | runtime.noewin.WS_BORDER) #LB
				self.motLoadList = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("Motions to load:", 5, 465, width-20, 20)
				index = self.noeWnd.createListBox(5, 485, width-40, 150, self.selectLoadListItem, runtime.noewin.LBS_NOTIFY | runtime.noewin.WS_VSCROLL | runtime.noewin.WS_BORDER) #LB
				self.loadList = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createButton("↑", width-30, 525, 20, 30, self.pressLoadListUpButton)
				self.noeWnd.createButton("↓", width-30, 565, 20, 30, self.pressLoadListDownButton)

				if True:
					index = self.noeWnd.createCheckBox("Force Center", 10, 640, 100, 30, self.checkFCenterCheckbox)
					self.FCenterCheckbox = self.noeWnd.getControlByIndex(index)
					self.FCenterCheckbox.setChecked(not self.selectionOnly and runtime.dialogOptions.doForceCenter)
					self.noeWnd.enableControlByIndex(index, not self.selectionOnly)

					index = self.noeWnd.createCheckBox("Sync by Frame Count", 10, 670, 160, 30, self.checkSyncCheckbox)
					self.syncCheckbox = self.noeWnd.getControlByIndex(index)
					self.syncCheckbox.setChecked(not self.selectionOnly and runtime.dialogOptions.doSync)
					self.noeWnd.enableControlByIndex(index, not self.selectionOnly)

					index = self.noeWnd.createCheckBox("Force Merge All", 10, 700, 160, 30, self.checkForceMergeCheckbox)
					self.forceMergeCheckbox = self.noeWnd.getControlByIndex(index)
					self.forceMergeCheckbox.setChecked(not self.selectionOnly and runtime.dialogOptions.doForceMergeAnims)
					self.noeWnd.enableControlByIndex(index, not self.selectionOnly)

				self.noeWnd.createStatic("Game:", width-218, 645, 60, 20)
				index = self.noeWnd.createComboBox(width-170, 645, 150, 20, self.selectGameBoxItem, runtime.noewin.CBS_DROPDOWNLIST) #CB
				self.gameBox = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("View:", width-210, 675, 60, 20)
				index = self.noeWnd.createComboBox(width-170, 675, 150, 20, self.selectLocalBoxItem, runtime.noewin.CBS_DROPDOWNLIST) #CB
				self.localBox = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("Scale:", width-215,705, 60, 20)
				index = self.noeWnd.createEditBox(width-170, 705, 80, 20, str(runtime.fDefaultMeshScale), self.inputGlobalScaleEditBox, False) #EB
				self.globalScaleEditBox = self.noeWnd.getControlByIndex(index)

				load_button_text = (
					"Load" if self.selectionOnly or not self.isMotlist or
					self.args.get("motlist") else "OK")
				self.noeWnd.createButton(load_button_text, 5, height-70, width-160, 30, self.openOptionsButtonLoadEntry)
				self.noeWnd.createButton("Cancel", width-96, height-70, 80, 30, self.openOptionsButtonCancel)

				self.setMotLoadList([mot.name for mot in self.pak.mots] if self.pak else [])
				self.setLoadList(self.loadItems)
				self.setPakList()
				self.setGameBox(self.gameBox)
				self.setLocalBox(self.localBox)

				self.noeWnd.doModal()

		def createMeshWindow(self, width=runtime.dialogOptions.width, height=runtime.dialogOptions.height):

			if self.create(width, height):
				self.noeWnd.setFont("Futura", 14)

				self.noeWnd.createStatic("Mesh files from:", 5, 5, width-20, 20)
				index = self.noeWnd.createEditBox(5, 25, width-20, 45, runtime.dialogOptions.currentDir, self.inputCurrentDirEditBox) #EB
				self.currentDirEditBox = self.noeWnd.getControlByIndex(index)

				index = self.noeWnd.createListBox(5, 80, width-20, runtime.iListboxSize, self.selectPakListItem, runtime.noewin.LBS_NOTIFY | runtime.noewin.WS_VSCROLL | runtime.noewin.WS_BORDER) #LB
				self.pakList = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("Files to load:", 5, runtime.iListboxSize+85, width-20, 20)
				index = self.noeWnd.createListBox(5, runtime.iListboxSize+105, width-40, 150, self.selectLoadListItem,  runtime.noewin.LBS_NOTIFY | runtime.noewin.WS_VSCROLL | runtime.noewin.WS_BORDER) #LB
				self.loadList = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createButton("↑", width-30, runtime.iListboxSize+145, 20, 30, self.pressLoadListUpButton)
				self.noeWnd.createButton("↓", width-30, runtime.iListboxSize+185, 20, 30, self.pressLoadListDownButton)

				if True:
					index = self.noeWnd.createCheckBox("Load Textures", 10, runtime.iListboxSize+265, 130, 30, self.checkLoadTexCheckbox)
					self.loadTexCheckbox = self.noeWnd.getControlByIndex(index)
					self.loadTexCheckbox.setChecked(runtime.dialogOptions.doLoadTex)


					index = self.noeWnd.createCheckBox("Load All Textures", 150, runtime.iListboxSize+265, 160, 30, self.checkLoadAllTexCheckbox)
					self.loadAllTexCheckbox = self.noeWnd.getControlByIndex(index)
					self.loadAllTexCheckbox.setChecked(runtime.dialogOptions.loadAllTextures)

					index = self.noeWnd.createCheckBox("Convert Textures", 10, runtime.iListboxSize+295, 130, 30, self.checkConvTexCheckbox)
					self.convTexCheckbox = self.noeWnd.getControlByIndex(index)
					self.convTexCheckbox.setChecked(runtime.dialogOptions.doConvertTex)

					index = self.noeWnd.createCheckBox("Collapse Bones", 150, runtime.iListboxSize+295, 120, 30, self.checkReparentCheckbox)
					self.reparentCheckbox = self.noeWnd.getControlByIndex(index)
					self.reparentCheckbox.setChecked(runtime.dialogOptions.reparentHelpers)

					'''index = self.noeWnd.createCheckBox("Import LODs", 10, iListboxSize+365, 100, 30, self.checkLODsCheckbox) #TODO
					self.LODsCheckbox = self.noeWnd.getControlByIndex(index)
					self.LODsCheckbox.setChecked(dialogOptions.doLODs)'''

					self.noeWnd.createButton("Select Animations", 150, runtime.iListboxSize+325, 200, 30, self.openMotlistDialogButton)

				self.noeWnd.createStatic("Game:", width-248, runtime.iListboxSize+270, 60, 20)
				index = self.noeWnd.createComboBox(width-200, runtime.iListboxSize+265, 180, 20, self.selectGameBoxItem, runtime.noewin.CBS_DROPDOWNLIST) #CB
				self.gameBox = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("View:", width-240, runtime.iListboxSize+300, 60, 20)
				index = self.noeWnd.createComboBox(width-200, runtime.iListboxSize+295, 180, 20, self.selectLocalBoxItem, runtime.noewin.CBS_DROPDOWNLIST) #CB
				self.localBox = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("Scale:", width-145, runtime.iListboxSize+330, 60, 20)
				index = self.noeWnd.createEditBox(width-100, runtime.iListboxSize+330, 80, 20, str(runtime.fDefaultMeshScale), self.inputGlobalScaleEditBox, False) #EB
				self.globalScaleEditBox = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createButton("Load", 5, runtime.iListboxSize+360, width-160, 30, self.openOptionsButtonLoadEntry)

				self.noeWnd.createButton("Cancel", width-96, runtime.iListboxSize+360, 80, 30, self.openOptionsButtonCancel)

				self.setLoadList(self.loadItems)
				self.setPakList()
				self.setGameBox(self.gameBox)
				self.setLocalBox(self.localBox)

				if runtime.noesis.optWasInvoked("-b") or runtime.bNoImportMenu:
					self.clickLoadButton()

				self.noeWnd.doModal()

	class openOptionsDialogExportWindow:

		def __init__(self, width, height, args):
			self.width = width
			self.height = height
			self.filepath = args.get("filepath") or ""
			self.texformat = args.get("texformat") or 98
			self.exportType = args.get("exportType") or os.path.splitext(runtime.rapi.getOutputName())[-1]
			self.sourceList = args.get("sourceList") or runtime.getSameExtFilesInDir(self.filepath)
			self.currentIdx = 0
			self.doWriteBones = False
			self.doRewrite = False
			self.doCancel = True
			self.failed = False
			self.doVFX = runtime.noesis.optWasInvoked("-vfx")
			self.indices = []
			self.LODDist = 0.02667995
			self.flag = -1

		def openOptionsVFXCheckbox(self, noeWnd, controlId, wParam, lParam):
			self.doVFX = not self.doVFX
			self.vfxCheckbox.setChecked(self.doVFX)

		def openOptionsButtonRewrite(self, noeWnd, controlId, wParam, lParam):
			self.doCancel = False
			self.doRewrite = True
			self.noeWnd.closeWindow()

		def openOptionsButtonExport(self, noeWnd, controlId, wParam, lParam):
			self.doCancel = False
			self.noeWnd.closeWindow()

		def openOptionsButtonExportBones(self, noeWnd, controlId, wParam, lParam):
			self.doCancel = False
			self.doWriteBones = True
			self.noeWnd.closeWindow()

		def openOptionsButtonCancel(self, noeWnd, controlId, wParam, lParam):
			self.noeWnd.closeWindow()

		def openBrowseMenu(self, noeWnd, controlId, wParam, lParam):
			filepath = runtime.noesis.userPrompt(runtime.noesis.NOEUSERVAL_FILEPATH, "Inject " + self.exportType.upper(), "Choose a " + self.exportType.upper() + " file to inject", self.filepath, None)
			if filepath:
				self.filepath = filepath
				#self.meshFile.setText(self.filepath)
				#if rapi.checkFileExists(filepath):
				self.clearComboBoxList()
				self.sourceList = runtime.getSameExtFilesInDir(self.filepath)
				self.setComboBoxList(self.meshFileList, self.filepath)

		def openOptionsButtonCancel(self, noeWnd, controlId, wParam, lParam):
			self.noeWnd.closeWindow()

		def inputMeshFileEditBox(self, noeWnd, controlId, wParam, lParam):
			self.meshEditText = self.meshFile.getText()
			self.meshFile.setText(self.meshEditText)
			if runtime.rapi.checkFileExists(self.meshEditText):
				self.filepath = self.meshEditText
				self.clearComboBoxList()
				self.sourceList = runtime.getSameExtFilesInDir(self.filepath)
				self.setComboBoxList(self.meshFileList, self.filepath)

		def inputFlagEditBox(self, noeWnd, controlId, wParam, lParam):
			if self.FlagBox.getText() != "":
				self.flag = int(self.FlagBox.getText())

		def inputLODDistEditBox(self, noeWnd, controlId, wParam, lParam):
			self.LODDist = float(self.LODEditBox.getText())

		def selectTexListItem(self, noeWnd, controlId, wParam, lParam):
			self.currentIdx = self.texType.getSelectionIndex()
			self.texformat = self.indices[self.currentIdx]
			filepath = runtime.rapi.getOutputName()
			filename = runtime.rapi.getExtensionlessName(filepath)
			self.outputFileName = filepath.replace(filename, filename + "." + str(self.texformat))
			print(self.outputFileName)

		def selectSourceListItem(self, noeWnd, controlId, wParam, lParam):
			self.currentIdx = self.meshFileList.getSelectionIndex()
			if self.sourceList and self.currentIdx:
				self.filepath = self.sourceList[self.currentIdx]

		def clearComboBoxList(self, list_object=None):
			#list_object = list_object or self.meshFileList
			for item in self.sourceList:
				self.meshFileList.removeString(item)
			#list_object.resetContent()

		def setComboBoxList(self, list_object=None, current_item=None):
			for item in self.sourceList:
				self.meshFileList.addString(item)
			self.meshFileList.selectString(current_item)
			self.currentIdx = self.meshFileList.getSelectionIndex()

		def create(self, width=None, height=None):
			width = width or self.width
			height = height or self.height
			self.noeWnd = runtime.noewin.NoeUserWindow("RE Engine MESH Options", "HTRAWWindowClass", width, height)
			noeWindowRect = runtime.noewin.getNoesisWindowRect()
			if noeWindowRect:
				windowMargin = 100
				self.noeWnd.x = noeWindowRect[0] + windowMargin
				self.noeWnd.y = noeWindowRect[1] + windowMargin
			return self.noeWnd.createWindow()

		def createMeshWindow(self, width=None, height=None):
			width = width or self.width
			height = height or self.height
			if self.create(width, height):
				row1_y = 0
				row2_y = 30
				exportRow_y = 60
				#row4_y = 100
				self.noeWnd.setFont("Futura", 14)

				#self.noeWnd.createStatic("Export Over Mesh", 5, row1_y, 140, 20)
				#index = self.noeWnd.createEditBox(5, 25, width-20, 20, self.filepath, self.inputMeshFileEditBox)
				#self.meshFile = self.noeWnd.getControlByIndex(index)

				index = self.noeWnd.createCheckBox("VFX Mesh", 5, row1_y, 80, 30, self.openOptionsVFXCheckbox)
				self.vfxCheckbox = self.noeWnd.getControlByIndex(index)
				self.vfxCheckbox.setChecked(self.doVFX)

				index = self.noeWnd.createComboBox(5, row2_y, width-20, 20, self.selectSourceListItem, runtime.noewin.CBS_DROPDOWNLIST)
				self.meshFileList = self.noeWnd.getControlByIndex(index)
				self.setComboBoxList(self.meshFileList, self.filepath)

				self.noeWnd.createButton("Browse", 5, exportRow_y, 80, 30, self.openBrowseMenu)
				if runtime.rapi.checkFileExists(self.filepath):
					self.noeWnd.createButton("Export", width-416, exportRow_y, 80, 30, self.openOptionsButtonExport)
					self.noeWnd.createButton("Export New Bones", width-326, exportRow_y, 130, 30, self.openOptionsButtonExportBones)
				self.noeWnd.createButton("Rewrite", width-186, exportRow_y, 80, 30, self.openOptionsButtonRewrite)
				self.noeWnd.createButton("Cancel", width-96, exportRow_y, 80, 30, self.openOptionsButtonCancel)


				self.noeWnd.createStatic("Rewrite Options:", 450, 100, 140, 20)
				self.noeWnd.createStatic("Flag:", 5, 130, 140, 20)
				index = self.noeWnd.createEditBox(45, 125, 40, 30, "", self.inputFlagEditBox, False)
				self.FlagBox = self.noeWnd.getControlByIndex(index)

				self.noeWnd.createStatic("LOD0 Factor:", 775, 130, 140, 20)
				index = self.noeWnd.createEditBox(885, 125, 100, 30, str(self.LODDist), self.inputLODDistEditBox, False)
				self.LODEditBox = self.noeWnd.getControlByIndex(index)

				self.noeWnd.doModal()
			else:
				print("Failed to create Noesis Window")
				self.failed = True

		def createTexWindow(self, width=None, height=None):
			width = width or self.width
			height = height or self.height
			if self.create(width, height):
				index = self.noeWnd.createComboBox(5, 5, 180, 20, self.selectTexListItem, runtime.noewin.CBS_DROPDOWNLIST)
				self.texType = self.noeWnd.getControlByIndex(index)
				for fmt in texFormatNames:
					fmtName = texFormatNames[fmt]
					self.texType.addString(fmtName)
					self.indices.append(fmt)
					if fmt == self.texformat:
						self.texType.selectString(fmtName)
						self.currentIdx = len(self.indices)
				self.noeWnd.createButton("Import", 190, 5, 80, 30, self.openOptionsButtonImport)
				self.noeWnd.createButton("Cancel", 190, 40, 80, 30, self.openOptionsButtonCancel)
				self.noeWnd.doModal()
			else:
				print("Failed to create Noesis Window")
				self.failed = True

	return (
		DialogOptions,
		openOptionsDialogImportWindow,
		openOptionsDialogExportWindow,
	)
