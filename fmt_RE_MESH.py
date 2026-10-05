#RE Engine [PC] - ".mesh" plugin for Rich Whitehouse's Noesis
#Authors: alphaZomega, Gh0stblade
#Special thanks: Chrrox, SilverEzredes, Enaium
Version = "v3.28 (September 21, 2024)"

#Changelog:
#- Fixed motlist.854 reading


#Options: These are global options that change or enable/disable certain features

#Var												Effect
#Export Extensions
bRayTracingExport			= True					#Enable or disable the export of RE2R, RE3R and RE7 RayTracing meshes and textures
bRE2Export 					= True					#Enable or disable export of mesh.1808312334 and tex.10 from the export list
bRE3Export 					= True					#Enable or disable export of mesh.1902042334 and tex.190820018 from the export list
bDMCExport 					= True					#Enable or disable export of mesh.1808282334 and tex.11 from the export list
bRE7Export 					= True					#Enable or disable export of mesh.32 and tex.8 from the export list
bREVExport 					= True					#Enable or disable export of mesh.2102020001 from the export list (and tex.31)
bRE8Export 					= True					#Enable or disable export of mesh.2101050001 from the export list (and tex.30)
bMHRiseExport 				= False					#Enable or disable export of mesh.2008058288 from the export list (and tex.28)
bMHRiseSunbreakExport 		= True					#Enable or disable export of mesh.2109148288 from the export list (and tex.28)
bSF6Export					= True					#Enable or disable export of mesh.230110883 from the export list (and tex.143230113)
bRE4Export					= True					#Enable or disable export of mesh.221108797 from the export list (and tex.143221013)
bExoExport					= True					#Enable or disable export of mesh.220907984 from the export list (and tex.40)
bApolloExport				= True					#Enable or disable export of mesh.230612127 from the export list (and tex.719230324)
bDD2Export					= True					#Enable or disable export of mesh.231011879 from the export list (and tex.760230703)
bDRDRExport					= True					#Enable or disable export of mesh.240424828 from the export list (and tex.240606151)
bPragmataExport				= True					#Enable the scoped candidate 002 .251121828 source-template writer


#Mesh Global
fDefaultMeshScale 			= 100.0 				#Override mesh scale (default is 1.0)
bMaterialsEnabled 			= True					#Load MDF Materials
bRenderAsPoints 			= False					#Render mesh as points without triangles drawn (1 = on, 0 = off)
bImportAllLODs 				= False					#Imports all LODGroups (as separate models)

#Vertex Components (Import)
bNORMsEnabled 				= True					#Normals
bTANGsEnabled 				= True					#Tangents
bUVsEnabled 				= True					#UVs
bSkinningEnabled 			= True					#Enable skin weights
bColorsEnabled				= True					#Enable Vertex Colors
bDebugNormals 				= False					#Debug normals as RGBA
bDebugTangents 				= False					#Debug tangents as RGBA

#Import Options
bPrintMDF 					= False					#Prints debug info for MDF files
bDebugMESH 					= False					#Prints debug info for MESH files
bPopupDebug 				= True					#Pops up debug window on opening MESH with MDF
bPrintFileList 				= True					#Prints a list of files used by the MDF
bColorize 					= False					#Colors the materials of the model and lists which material is which color
bUseOldNamingScheme 		= False					#Names submeshes by their material ID (like in the MaxScript) rather than by their order in the file
bRenameMeshesToFilenames 	= False					#For use with Noesis Model Merger. Renames submeshes to have their filenames in the mesh names
bImportMaterialNames		= True					#Imports material name data for each mesh, appending it to the end of each Submesh's name
bShorterNames				= True					#Imports meshes named like "LOD_1_Main_1_Sub_1" instead of "LODGroup_1_MainMesh_1_SubMesh_1"
bImportMips 				= False					#Imports texture mip maps as separate images
texOutputExt				= ".tga"				#File format used when linking FBX materials to images
doConvertMatsForBlender		= False					#Load alpha maps as reflection maps, metallic maps as specular maps and roughness maps as bump maps for use with modified Blender FBX importer
bNoImportMenu				= False					#Hide the import menu on loading a mesh

#Export Options
bNewExportMenu				= False					#Show a custom Noesis window on mesh export
bAlwaysRewrite				= False					#Always try to rewrite the meshfile on export
bAlwaysWriteBones			= False					#Always write new skeleton to mesh
bNormalizeWeights 			= False					#Makes sure that the weights of every vertex add up to 1.0, giving the remainder to the bone with the least influence
bCalculateBoundingBoxes		= True					#Calculates the bounding box for each bone
BoundingBoxSize				= 1.0					#With bCalculateBoundingBoxes False, change the size of the bounding boxes created for each rigged bone when exporting with -bones or -rewrite
bRigToCoreBones				= False					#Assign non-matching bones to the hips and spine, when exporting a mesh without -bones or -rewrite
bSetNumModels				= True					#Sets the header byte "NumModels" to defaults when exporting without -rewrite, preventing crashes
bForceRootBoneToBone0		= True					#If the root bone is detected as the last bone in the bones list, this will move it to be the first bone in the list

#Import/Export:
bAddBoneNumbers 			= 2						#Adds bone numbers and colons before bone names to indicate if they are active. 0 = Off, 1 = On, 2 = Auto
bRotateBonesUpright			= False					#Rotates bones to be upright for editing and then back to normal for exporting
bReadGroupIds				= True					#Import/Export with the GroupID as the MainMesh number

#Plugin GUI
iListboxSize  				= 280					#The height of the list box in the plugin's import menu


from inc_noesis import *
from collections import namedtuple
import hashlib
import json
import struct
import noewin
import math
import re_engine_common as re_common
import os
import re
import copy
import time
from re_engine_runtime import PluginRuntime

_runtime = PluginRuntime(globals())

from re_engine_types import (
	MeshCapability,
	MeshProfileError,
	MaterialProfileError,
	DoubleClickTimer,
	BoneHeader,
	BoneClipHeader,
	BoneTrack,
	Unpacks,
	UnpackVec,
)

from re_engine_config import (
	texFormatLayouts,
	MDF2_51_ENTRY_SIZE,
	MDF2_51_TEXTURE_ENTRY_SIZE,
	MDF2_51_PROPERTY_ENTRY_SIZE,
	PRAGMATA_TEXTURE_SEMANTICS,
	PRAGMATA_MESH_CAPABILITY_KEY,
	PRAGMATA_CANDIDATE_002_SOURCE_SHA256,
	PRAGMATA_CANDIDATE_002_POSITION_SNAP_EPSILON,
	PRAGMATA_250707828,
	PRAGMATA_MPLY_250707828,
	PRAGMATA_MPLY_VERTEX_FLAGS,
	PRAGMATA_HEADER_FIELDS,
	PRAGMATA_MESH_RANGE_LABELS,
	PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY,
	PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY,
	PRAGMATA_MOTLIST_1057_MTRE_ONLY_CAPABILITY,
	formats,
	extToFormat,
	texFormatNames,
	fmtNameToBpp,
	gamesList,
	fullGameNames,
)


def registerNoesisTypes():

	def addOptions(handle):
		noesis.setTypeExportOptions(handle, "-noanims -notex")
		noesis.addOption(handle, "-bones", "Write new skeleton on export", 0)
		noesis.addOption(handle, "-rewrite", "Rewrite submeshes and materials structure", 0)
		noesis.addOption(handle, "-flip", "Reverse handedness from DirectX to OpenGL", 0)
		noesis.addOption(handle, "-bonenumbers", "Add bone numbers to imported bones", 0)
		noesis.addOption(handle, "-meshfile", "Export using a given source mesh filename", noesis.OPTFLAG_WANTARG)
		noesis.addOption(handle, "-b", "Run as a batch process", 0)
		noesis.addOption(handle, "-adv", "Show Advanced Export Options window", 0)
		noesis.addOption(handle, "-vfx", "Export as VFX mesh", 0)
		return handle

	handle = noesis.register("RE Engine MESH [PC]", ".1902042334;.1808312334;.1808282334;.2008058288;.2102020001;.2101050001;.2109108288;.2109148288;.220128762;.220301866;.220721329;.221108797;.220907984;.230110883;.230612127;.231011879;.240424828;.251121828;.NewMesh")
	noesis.setHandlerTypeCheck(handle, meshCheckType)
	noesis.setHandlerLoadModel(handle, meshLoadModel)
	noesis.addOption(handle, "-noprompt", "Do not prompt for MDF file", 0)
	noesis.setTypeSharedModelFlags(handle, (noesis.NMSHAREDFL_WANTGLOBALARRAY))

	if bPragmataExport:
		handle = noesis.register(
			"PRAGMATA Candidate 002 MESH Writer", ".251121828")
		noesis.setHandlerWriteModel(handle, pragmataMeshWriteModel)
		noesis.setTypeExportOptions(handle, "-noanims -notex")
		noesis.addOption(handle, "-meshfile",
			"Use the frozen candidate 002 source template",
			noesis.OPTFLAG_WANTARG)
		noesis.addOption(handle, "-noprompt", "Do not show source prompts", 0)

	handle = noesis.register("RE Engine Texture [PC]", ".10;.190820018;.11;.8;.28;.stm;.30;.31;.34;.35;.36;.40;.143221013;.143230113;.719230324;.760230703;.240606151;.251111100")
	noesis.setHandlerTypeCheck(handle, texCheckType)
	noesis.setHandlerLoadRGBA(handle, texLoadDDS)

	handle = noesis.register("RE Engine UVS [PC]", ".5;.7;.8")
	noesis.setHandlerTypeCheck(handle, UVSCheckType)
	noesis.setHandlerLoadModel(handle, UVSLoadModel)

	handle = noesis.register("RE Engine SCN [PC]", ".19;.20")
	noesis.setHandlerTypeCheck(handle, SCNCheckType)
	noesis.setHandlerLoadModel(handle, SCNLoadModel)

	handle = noesis.register("RE Engine MOTLIST [PC]", ".60;.85;.99;.484;.486;.500;.524;.528;.643;.653;.663;.750;.751;.851;.854;.1057")
	noesis.setHandlerTypeCheck(handle, motlistCheckType)
	noesis.setHandlerLoadModel(handle, motlistLoadModel)

	if bRE2Export:
		handle = noesis.register("RE2 Remake Texture [PC]", ".10")
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA)
		handle = noesis.register("RE2 MESH", (".1808312334"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bRE3Export:
		handle = noesis.register("RE3 Remake Texture [PC]", ".190820018")
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA)
		handle = noesis.register("RE3 MESH", (".1902042334"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	#fbxskel export is disabled
	#handle = noesis.register("fbxskel", (".fbxskel.3"))
	#noesis.setHandlerWriteModel(handle, skelWriteFbxskel)
	#noesis.setTypeExportOptions(handle, "-noanims -notex")

	if bDMCExport:
		handle = noesis.register("Devil May Cry 5 Texture [PC]", ".11")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA)
		handle = noesis.register("DMC5 MESH", (".1808282334"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bREVExport or bRE8Export:
		handle = noesis.register("RE8 / ReVerse Texture [PC]", ".30")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);

	if bREVExport:
		handle = noesis.register("ReVerse MESH", (".2102020001"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bRE8Export:
		handle = noesis.register("RE8 MESH", (".2101050001"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bMHRiseExport or bMHRiseSunbreakExport:
		handle = noesis.register("MHRise Texture [PC]", ".28;.stm")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		if bMHRiseExport:
			handle = noesis.register("MHRise MESH", (".2008058288"))
			noesis.setHandlerTypeCheck(handle, meshCheckType)
			noesis.setHandlerWriteModel(handle, meshWriteModel)
			addOptions(handle)
		if bMHRiseSunbreakExport:
			handle = noesis.register("MHRise Sunbreak MESH", (".2109148288"))
			noesis.setHandlerTypeCheck(handle, meshCheckType)
			noesis.setHandlerWriteModel(handle, meshWriteModel)
			addOptions(handle)

	if bRE7Export:
		handle = noesis.register("Resident Evil 7 Texture [PC]", ".8")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA)
		#RE7 MESH support is disabled for this version

	if bRayTracingExport:
		handle = noesis.register("RE2,3 RayTracing Texture [PC]", ".34")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		handle = noesis.register("RE7 RayTracing Texture [PC]", ".35")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		handle = noesis.register("RE2+3 RayTracing MESH", (".2109108288"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)
		handle = noesis.register("RE7 RayTracing MESH", (".220128762"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bSF6Export:
		handle = noesis.register("Street Fighter 6 Texture [PC]", ".143230113;")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		handle = noesis.register("Street Fighter 6 Mesh", (".230110883"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bRE4Export:
		handle = noesis.register("RE4 Remake Texture [PC]", ".143221013")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		handle = noesis.register("RE4 Remake Mesh", (".221108797"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bExoExport:
		handle = noesis.register("ExoPrimal Texture [PC]", ".40")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		handle = noesis.register("ExoPrimal Mesh", (".220907984"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bApolloExport:
		handle = noesis.register("Apollo Justice: Ace Attorney Trilogy Texture [PC]", ".719230324")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		handle = noesis.register("Apollo Justice: Ace Attorney Trilogy Mesh", (".230612127"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bDD2Export:
		handle = noesis.register("Dragon's Dogma 2 Texture [PC]", ".760230703")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		handle = noesis.register("Dragon's Dogma 2 Mesh", (".231011879"))
		noesis.setHandlerTypeCheck(handle, meshCheckType)
		noesis.setHandlerWriteModel(handle, meshWriteModel)
		addOptions(handle)

	if bDRDRExport:
		handle = noesis.register("Dead Rising DR Texture [PC]", ".240606151")
		noesis.setHandlerTypeCheck(handle, texCheckType)
		noesis.setHandlerWriteRGBA(handle, texWriteRGBA);
		#handle = noesis.register("Dead Rising DR Mesh", (".240424828"))
		#noesis.setHandlerTypeCheck(handle, meshCheckType)
		#noesis.setHandlerWriteModel(handle, meshWriteModel)
		#addOptions(handle)


	noesis.logPopup()
	return 1

#Default global variables for internal use:
sGameName = "RE2"
extractedNativesPath = ""
sExportExtension = ".1808312334"
bWriteBones = False
bDoVFX = False
bReWrite = False
openOptionsDialog = None
w1 = 127
w2 = -128


#murmur3 hash algorithm, credit to Darkness for adapting this:


		#bs.seek(0)
		#self.bs = NoeBitStream(bs.readBytes(motEnd))
		#self.anim = NoeKeyFramedAnim(self.name, self.motlist.bones, self.kfBones, 1)


isMeshVer3 = False
BBskipBytes = numNodesLocation = LOD1OffsetLocation = normalsRecalcOffsLocation = bsHdrOffLocation = bsIndicesOffLocation = \
vBuffHdrOffsLocation = bonesOffsLocation = nodesIndicesOffsLocation = namesOffsLocation = floatsHdrOffsLocation = 0


# Bind each responsibility to this plugin instance; callbacks resolve shared
# options and host APIs through _runtime. No owner imports this entry.


from re_engine_materials import bind as _bind_re_engine_materials
(
	_materialCheckedRange,
	_materialScalar,
	_materialUtf16z,
	parsePragmataMdf2Profile,
	bindPragmataMaterialRecords,
	buildNoesisMaterial,
) = _bind_re_engine_materials(_runtime)


from re_engine_gdeflate import bind as _bind_re_engine_gdeflate
(
	loadGDeflateDecoder,
) = _bind_re_engine_gdeflate(_runtime)


from re_engine_tex import bind as _bind_re_engine_tex
(
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
) = _bind_re_engine_tex(_runtime)


from re_engine_paths import bind as _bind_re_engine_paths
(
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
) = _bind_re_engine_paths(_runtime)


from re_engine_mesh_profiles import (
	_detectPragmataIdentity,
	_readMeshScalar,
	_checkedRange,
	_validatePragmataBoneMapCount,
	decodeSixU10,
	parsePragmataSubmesh,
	_validatePragmataWeights,
	_decodePragmataWeightProfile,
	_rangesOverlap,
	parsePragmataMeshBufferHeader,
	parsePragmataBlendShapeProfile,
	_finalizePragmataBlendPayloadProfile,
	decodePragmataBlendDelta,
	_meshHalfBitsToFloat,
	decodePragmataBlendHalfDelta,
	_pragmataNeutralBlendValue,
	_decodePragmataBlendShapes,
	parsePragmataHeader,
	parsePragmataMplyHeader,
	_meshFloat32,
	_decodePragmataMplyPositions,
	_meshTopologyHash,
	_meshHalfAwayFromZero,
	_meshQuantizeSnorm,
	_meshQuantizeColor,
	_meshRoundShiftRightToEven,
	_meshFloatToHalfBits,
	_meshQuantizeWeights,
	_meshPackSixU10,
	_meshValidateVector,
	_meshTransformPointRowVector,
	_readPragmataCString,
	_newPragmataImportStats,
	_parsePragmataMplyData,
	_pragmataMplyNoesisBatches,
	_pragmataNoesisIndexSubmission,
	_parsePragmataMeshData,
)


from re_engine_mesh_writer import bind as _bind_re_engine_mesh_writer
(
	_writePragmataExactTemplate,
	writePragmataCandidate002Exact,
	_pragmataGeometryFromModel,
	_pragmataWriterPathIdentity,
	pragmataMeshWriteModel,
	getExportName,
	meshWriteModel,
) = _bind_re_engine_mesh_writer(_runtime)


from re_engine_mesh import bind as _bind_re_engine_mesh
(
	feedPragmataMorphFrames,
	setOffsets,
	findGameName,
	meshFile,
) = _bind_re_engine_mesh(_runtime)

from re_engine_materials import bind_mesh_materials as _bind_mesh_materials
(meshFile.createMaterials, meshFile._loadPragmataMaterialProfile) = _bind_mesh_materials(_runtime)


from re_engine_animation import bind as _bind_re_engine_animation
(
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
) = _bind_re_engine_animation(_runtime)


from re_engine_motlist import bind as _bind_re_engine_motlist
(
	readPackedBitsVec3,
	convertBits,
	skipToNextLine,
	wRot,
	motFile,
	motlistFile,
	motlistCheckType,
) = _bind_re_engine_motlist(_runtime)


from re_engine_gui import bind as _bind_re_engine_gui
(
	DialogOptions,
	openOptionsDialogImportWindow,
	openOptionsDialogExportWindow,
) = _bind_re_engine_gui(_runtime)


from re_engine_scene import bind as _bind_re_engine_scene
(
	UVSCheckType,
	UVSLoadModel,
	SCNCheckType,
	SCNLoadModel,
) = _bind_re_engine_scene(_runtime)


from re_engine_workflows import bind as _bind_re_engine_workflows
(
	_readMeshProfile,
	detectMeshCapability,
	meshCheckType,
	motlistLoadModel,
	meshLoadModel,
) = _bind_re_engine_workflows(_runtime)


from re_engine_binary import (
	readUIntAt,
	readUShortAt,
	readUByteAt,
	ReadUnicodeString,
	readUnicodeStringAt,
	hash,
	hash_wide,
)


from re_engine_mesh_writer import bind_geometry as _bind_re_engine_geometry
(
	sort_human,
	recombineNoesisMeshes,
) = _bind_re_engine_geometry(_runtime)

# Historical helper names remain entry-only aliases; internal callers use responsibilities.
_pragmataFloat32 = _meshFloat32
_pragmataTopologyHash = _meshTopologyHash
_pragmataHalfAwayFromZero = _meshHalfAwayFromZero
_pragmataQuantizeSnorm = _meshQuantizeSnorm
_pragmataQuantizeColor = _meshQuantizeColor
_pragmataRoundShiftRightToEven = _meshRoundShiftRightToEven
_pragmataFloatToHalfBits = _meshFloatToHalfBits
_pragmataQuantizeWeights = _meshQuantizeWeights
_pragmataPackSixU10 = _meshPackSixU10
_pragmataValidateVector = _meshValidateVector
_pragmataTransformPointRowVector = _meshTransformPointRowVector
_pragmataHalfBitsToFloat = _meshHalfBitsToFloat
loadPragmataGDeflateDecoder = loadGDeflateDecoder
