"""Paths implementation bound to one plugin runtime."""

import os
from re_engine_config import (
	formats,
)
from re_engine_types import (
	MaterialProfileError,
	MeshProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'LoadExtractedDir',
	'_pragmataNativesRoot',
	'noesis',
	'rapi',
	'resolvePragmataStreamingPath',
	'resolvePragmataTexturePath',
	'sGameName',
)


def _materialNativesRoot(meshPath, format_record):
	normalizedMesh = meshPath.replace("/", "\\")
	lowerMesh = normalizedMesh.lower()
	meshSuffix = ".mesh" + format_record["modelExt"]
	if not lowerMesh.endswith(meshSuffix):
		raise MaterialProfileError("mesh-suffix-mismatch")
	marker = "\\natives\\" + format_record["nDir"] + "\\"
	markerIndex = lowerMesh.find(marker)
	if markerIndex < 0:
		raise MaterialProfileError("natives-root-missing")
	return (normalizedMesh, normalizedMesh[:markerIndex + len(marker)])

def resolveTextureResourcePath(meshPath, textureResourcePath, format_record):
	normalizedMesh, nativesRoot = _materialNativesRoot(meshPath, format_record)
	resourcePath = textureResourcePath.replace("/", "\\")
	components = resourcePath.split("\\")
	if (not resourcePath.lower().endswith(".tex") or resourcePath.startswith("\\")
			or ":" in resourcePath or not components
			or any([component in ("", ".", "..") for component in components])):
		raise MaterialProfileError("texture-resource-path-mismatch")
	targetPath = os.path.normpath(nativesRoot + resourcePath + format_record["texExt"])
	rootPrefix = os.path.normcase(os.path.normpath(nativesRoot) + os.sep)
	if not os.path.normcase(targetPath).startswith(rootPrefix):
		raise MaterialProfileError("texture-resource-path-mismatch")
	return targetPath

def resolveMaterialCompanionPath(meshPath, format_record):
	meshSuffix = ".mesh" + format_record["modelExt"]
	if not meshPath.lower().endswith(meshSuffix):
		raise MaterialProfileError("mesh-suffix-mismatch")
	return meshPath[:-len(meshSuffix)] + "_mat" + format_record["mdfExt"]


def bind(runtime):
	def _pragmataNativesRoot(meshPath):
		return _materialNativesRoot(meshPath, formats["PRAGMATA"])

	def resolvePragmataTexturePath(meshPath, textureResourcePath):
		return resolveTextureResourcePath(meshPath, textureResourcePath, formats["PRAGMATA"])

	def resolvePragmataMdfPath(meshPath):
		return resolveMaterialCompanionPath(meshPath, formats["PRAGMATA"])

	def resolvePragmataMaterialCompanions(meshPath, textureResourcePath):
		normalizedMesh, nativesRoot = runtime._pragmataNativesRoot(meshPath)
		return {
			"mdf2": resolvePragmataMdfPath(normalizedMesh),
			"tex": runtime.resolvePragmataTexturePath(meshPath, textureResourcePath),
		}

	def resolvePragmataStreamingPath(path):
		normalized = path.replace("/", "\\")
		marker = "\\natives\\stm\\"
		marker_index = normalized.lower().find(marker)
		if marker_index < 0 or normalized.lower().find(marker + "streaming\\") >= 0:
			raise MeshProfileError("invalid-streaming-main-path")
		insert_at = marker_index + len(marker)
		return normalized[:insert_at] + "streaming\\" + normalized[insert_at:]

	def loadPragmataStreamingCompanion(path):
		companion_path = runtime.resolvePragmataStreamingPath(path)
		try:
			if runtime.rapi.checkFileExists(companion_path):
				return companion_path, bytes(runtime.rapi.loadIntoByteArray(companion_path))
		except (AttributeError, RuntimeError, NameError):
			pass
		if os.path.isfile(companion_path):
			with open(companion_path, "rb") as stream:
				return companion_path, stream.read()
		raise MeshProfileError("missing-streaming-companion")

	def GetRootGameDir(path=""):
		path = runtime.rapi.getDirForFilePath(path or runtime.rapi.getInputName())
		while len(path) > 3:
			lastFolderName = os.path.basename(os.path.normpath(path)).lower()
			if lastFolderName == "stm" or lastFolderName == "x64":
				break
			else:
				path = os.path.normpath(os.path.join(path, ".."))
		
		return path	+ "\\"

	def LoadExtractedDir(gameName=None):
		gameName = gameName or runtime.sGameName
		nativesPath = ""
		try: 
			with open(runtime.noesis.getPluginsPath() + '\python\\' + gameName + 'NativesPath.txt') as fin:
				nativesPath = fin.read()
				fin.close()
		except IOError:
			pass
		if not os.path.isdir(nativesPath):
			return ""
		return nativesPath

	def SaveExtractedDir(dirIn, gameName=None):
		gameName = gameName or runtime.sGameName
		try: 
			print (runtime.noesis.getPluginsPath() + 'python\\' + gameName + 'NativesPath.txt')
			with open(runtime.noesis.getPluginsPath() + 'python\\' + gameName + 'NativesPath.txt', 'w') as fout:
				print ("Writing string: " + dirIn + " to " + runtime.noesis.getPluginsPath() + 'python\\' + gameName + 'NativesPath.txt')
				fout.flush()
				fout.write(str(dirIn))
				fout.close()
		except IOError:
			print ("Failed to save natives path: IO Error")
			return 0
		return 1

	def findRootDir(path):
		idx = path.find("\\natives\\")
		if idx != -1:
			return path[:(idx + 9)]
		return path

	def forceFindTexture(FileName, startExtension=""):
		# Shared state is owned by runtime.
		
		for gameName, table in formats.items():
			runtime.sGameName = gameName
			ext = table["texExt"]
			texFile = runtime.LoadExtractedDir() + FileName + ext
			
			if runtime.rapi.checkFileExists(texFile):
				return texFile, ext
				
		return 0, 0

	def getSameExtFilesInDir(filename=None, ext=None):
		ext = ext or os.path.splitext(runtime.rapi.getOutputName())[-1]
		filename = filename or runtime.rapi.getOutputName()
		sourceList = []
		for item in os.listdir(os.path.dirname(runtime.rapi.getOutputName())):
			if os.path.splitext(item)[1] == ext:
				sourceList.append(os.path.join(os.path.dirname(filename), item))
		return sourceList

	return (
		_pragmataNativesRoot,
		resolvePragmataTexturePath,
		resolvePragmataMdfPath,
		resolvePragmataMaterialCompanions,
		resolvePragmataStreamingPath,
		loadPragmataStreamingCompanion,
		GetRootGameDir,
		LoadExtractedDir,
		SaveExtractedDir,
		findRootDir,
		forceFindTexture,
		getSameExtFilesInDir,
	)
