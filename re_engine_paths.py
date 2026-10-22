"""Paths implementation bound to one plugin runtime."""

import os
import ntpath
import hashlib
import json
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


def _checkMaterialSearchPath(path):
	"""Reject ambiguous Windows components before producing lookup candidates."""
	normalized = path.replace("/", "\\")
	_drive, tail = ntpath.splitdrive(normalized)
	parts = tail.lstrip("\\").split("\\")
	if (any(char in tail for char in (":", "\x00", "*", "?", '"', "<", ">", "|")) or
			any(part in ("", ".", "..") or part.rstrip(" .") != part for part in parts)):
		raise MaterialProfileError("material-search-path-mismatch")
	return normalized


def materialCompanionCandidates(meshPath, format_record, extractedRoots=()):
	"""Return deterministic same-game MDF candidates for loaders and extraction.

	The first three suffixes retain the established exact companion priority.
	Additional roots are natives/<platform> roots, never a cross-game search.
	"""
	meshSuffix = ".mesh" + format_record["modelExt"]
	if not meshPath.lower().endswith(meshSuffix.lower()):
		raise MaterialProfileError("mesh-suffix-mismatch")
	normalized = _checkMaterialSearchPath(meshPath)
	stem = meshPath[:-len(meshSuffix)]
	stems = [stem]
	marker = "\\natives\\" + format_record["nDir"].lower() + "\\"
	index = normalized.lower().find(marker)
	if index >= 0:
		relative = normalized[index + len(marker):-len(meshSuffix)]
		for root in extractedRoots:
			if not root:
				continue
			root = _checkMaterialSearchPath(root.rstrip("\\/"))
			if not ntpath.isabs(root):
				raise MaterialProfileError("material-search-root-mismatch")
			stems.append(ntpath.join(root, relative))
	result, seen = [], set()
	for base in stems:
		for suffix in ("", "_mat", "_00", "_v00", "_a"):
			candidate = base + suffix + format_record["mdfExt"]
			key = ntpath.normcase(ntpath.normpath(candidate))
			if key not in seen:
				result.append(candidate)
				seen.add(key)
	# Observed character companions can be shared between gender directories.
	# Change the two explicit identity components together, never arbitrary digits.
	if format_record.get("materialGenderFallback", False):
		for base in stems:
			parts = base.replace("/", "\\").split("\\")
			lower = [part.lower() for part in parts]
			for start in range(len(parts) - 5):
				if lower[start:start + 3] != ["art", "model", "character"]:
					continue
				identity = parts[-1].split("_")
				if (len(identity) != 3 or identity[0].lower() != lower[start + 3]
						or identity[1] not in ("000", "001")
						or parts[start + 4] != identity[1]):
					continue
				other = "001" if identity[1] == "000" else "000"
				parts[start + 4] = other
				identity[1] = other
				parts[-1] = "_".join(identity)
				candidate = "\\".join(parts) + format_record["mdfExt"]
				key = ntpath.normcase(candidate)
				if key not in seen:
					result.append(candidate)
					seen.add(key)
	return result


def findMaterialCompanionPath(meshPath, format_record, fileExists, extractedRoots=()):
	for candidate in materialCompanionCandidates(meshPath, format_record, extractedRoots):
		if fileExists(candidate):
			return candidate
	return None


def findLinkedMaterialPath(meshPath, format_record, extractedRoots=()):
	"""Resolve an optional, hash-bound scene material link after normal lookup.

	Links live next to the versioned MESH and name one MDF relative to its
	platform root. A link selects a scene variant; it is not a global mapping.
	"""
	normalized = _checkMaterialSearchPath(meshPath)
	marker = "\\natives\\" + format_record["nDir"].lower() + "\\"
	if marker not in normalized.lower():
		return None
	normalized, root = _materialNativesRoot(normalized, format_record)
	relative = normalized[len(root):]
	roots = [root]
	for extra in extractedRoots:
		if extra:
			extra = _checkMaterialSearchPath(extra.rstrip("\\/"))
			if not ntpath.isabs(extra):
				raise MaterialProfileError("material-link-root-mismatch")
			roots.append(extra)
	def uniqueObject(pairs):
		result = {}
		for key, value in pairs:
			if key in result:
				raise ValueError("duplicate-key")
			result[key] = value
		return result
	def fileHash(path):
		digest = hashlib.sha256()
		with open(path, "rb") as stream:
			for block in iter(lambda: stream.read(1024 * 1024), b""):
				digest.update(block)
		return digest.hexdigest()
	for root in roots:
		linkPath = ntpath.join(root, relative) + ".material-link.json"
		if not os.path.isfile(linkPath):
			continue
		try:
			with open(linkPath, "rb") as stream:
				raw = stream.read(65537)
			if len(raw) > 65536:
				raise ValueError("size")
			link = json.loads(raw.decode("utf-8"), object_pairs_hook=uniqueObject)
			if not isinstance(link, dict) or link.get("schema") != "re-engine-material-link/v1":
				raise ValueError("schema")
			for field in ("mesh_sha256", "material_sha256"):
				value = link.get(field)
				if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
					raise ValueError("hash-format")
			resource = link.get("material")
			if not isinstance(resource, str):
				raise ValueError("material-path")
			resource = _checkMaterialSearchPath(resource)
			if ntpath.splitdrive(resource)[0] or ntpath.isabs(resource) or not resource.lower().endswith(format_record["mdfExt"].lower()):
				raise ValueError("material-path")
			target = ntpath.normpath(ntpath.join(root, resource))
			# Windows CPython 3.2 realpath is only abspath. Resolve actual file
			# handles there so junctions cannot defeat the containment check.
			canonical = getattr(ntpath, "_getfinalpathname", None) if os.name == "nt" else os.path.realpath
			if canonical is None:
				raise ValueError("canonical-path-unavailable")
			actualRoot, actualTarget = canonical(root), canonical(target)
			if not os.path.normcase(actualTarget).startswith(os.path.normcase(actualRoot.rstrip("\\/") + os.sep)):
				raise ValueError("material-containment")
			if fileHash(meshPath) != link["mesh_sha256"]:
				raise ValueError("mesh-hash")
			if fileHash(target) != link["material_sha256"]:
				raise ValueError("material-hash")
			return target
		except (IOError, OSError, ValueError, UnicodeError, RuntimeError) as error:
			raise MaterialProfileError("material-link-invalid:" + str(error))
	return None


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
		relative = normalized[insert_at:]
		# Validate before even checking existence: Windows normalizes traversal
		# and trailing dots/spaces, and ':' can address an alternate data stream.
		if (":" in relative or "\x00" in relative or any(
			component in ("", ".", "..") or component.rstrip(" .") != component
			for component in relative.split("\\"))):
			raise MeshProfileError("invalid-streaming-main-path")
		return normalized[:insert_at] + "streaming\\" + relative

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
