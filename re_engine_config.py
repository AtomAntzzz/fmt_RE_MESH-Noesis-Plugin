"""Single source of game and observed format configuration."""

from re_engine_types import MeshCapability

texFormatLayouts = {
	10: (1, 1, 8),
	28: (1, 1, 4),
	29: (1, 1, 4),
	49: (1, 1, 2),
	61: (1, 1, 1),
	71: (4, 4, 8),
	72: (4, 4, 8),
	77: (4, 4, 16),
	78: (4, 4, 16),
	80: (4, 4, 8),
	83: (4, 4, 16),
	95: (4, 4, 16),
	96: (4, 4, 16),
	98: (4, 4, 16),
	99: (4, 4, 16),
}

# Candidate 002 single-material profile constraints (not general MDF counts).
MDF2_51_EXACT_TEXTURE_COUNT = 15
MDF2_51_EXACT_PROPERTY_COUNT = 148

MDF2_51_ENTRY_SIZE = 0x6C

MDF2_51_TEXTURE_ENTRY_SIZE = 0x20

MDF2_51_PROPERTY_ENTRY_SIZE = 0x18

PRAGMATA_TEXTURE_SEMANTICS = {
	"BaseDielectricMap": ("albedo", "strong-inference", "preview-mapping"),
	"NormalRoughnessMap": ("normal-roughness", "strong-inference", "preview-mapping"),
	"NormalRoughnessCavityMap": ("normal-roughness-cavity", "strong-inference", "preview-mapping"),
	"IrisBaseMap": ("albedo", "strong-inference", "preview-mapping"),
	"ScleraMap": ("albedo", "strong-inference", "preview-mapping"),
	"EmissiveMap": ("emissive", "strong-inference", "preview-mapping"),
}

PRAGMATA_MESH_CAPABILITY_KEY = "pragmata-250707828-ordinary-skinned-v1"

PRAGMATA_CANDIDATE_002_SOURCE_SHA256 = (
	"78001dd7dd85da34434e48ae4a9426ba71d023d54dab30f3c490f69471fa4068"
)

PRAGMATA_CANDIDATE_002_POSITION_SNAP_EPSILON = 1.0e-7

PRAGMATA_250707828 = MeshCapability(
	PRAGMATA_MESH_CAPABILITY_KEY,
	250707828,
	"late-176",
	"late-two-u64-96",
	"dr32",
	"six-u10",
)

PRAGMATA_MPLY_250707828 = MeshCapability(
	"pragmata-250707828-mply-streaming-v1",
	250707828,
	"mply-176",
	"cluster-streaming",
	"meshlet-u8",
	"none",
)

PRAGMATA_MPLY_VERTEX_FLAGS = frozenset((
	0x84840310, 0x84841310, 0x84842310,
	0x84844310, 0x84845310, 0x84846310,
	0x84848310, 0x84849310, 0x8484A310,
))

PRAGMATA_HEADER_FIELDS = (
	("vertices_offset", 0x28),
	("lod_offset", 0x30),
	("blend_shape_offset", 0x50),
	("mesh_offset", 0x58),
	("aabb_offset", 0x70),
	("skeleton_offset", 0x78),
	("material_remap_offset", 0x80),
	("bone_remap_offset", 0x88),
	("blend_name_offset", 0x90),
	("names_offset", 0x98),
	("streaming_offset", 0xA0),
)

PRAGMATA_MESH_RANGE_LABELS = (
	"mesh-header",
	"vertex-elements",
	"vertex-buffer",
	"face-buffer",
)

PRAGMATA_MOTLIST_1057_EXACT_CAPABILITY = (
	"pragmata-motlist-1057-mot-993-single-action-local-bones-v1")

PRAGMATA_MOTLIST_1057_MULTI_CAPABILITY = (
	"pragmata-motlist-1057-mot-993-multi-shared-bones-v1")

PRAGMATA_MOTLIST_1057_MTRE_ONLY_CAPABILITY = (
	"pragmata-motlist-1057-mtre-22-recognized-only-v1")

formats = {
	"RE7":			{ "modelExt": ".-1", 		 "texExt": ".8", 		 "mmtrExt": ".69", 		   "nDir": "x64", "mdfExt": ".mdf2.6",  "meshVersion": 0, "mdfVersion": 0, "mlistExt": ".60", "meshMagic":352921600 },
	"RE2":			{ "modelExt": ".1808312334", "texExt": ".10",		 "mmtrExt": ".1808160001", "nDir": "x64", "mdfExt": ".mdf2.10", "meshVersion": 1, "mdfVersion": 1, "mlistExt": ".85", "meshMagic":386270720, "motionIDsData":[24,8] },
	"DMC5":			{ "modelExt": ".1808282334", "texExt": ".11", 		 "mmtrExt": ".1808168797", "nDir": "x64", "mdfExt": ".mdf2.10", "meshVersion": 1, "mdfVersion": 1, "mlistExt": ".85", "meshMagic":386270720, "motionIDsData":[24,8]  },
	"RE3": 			{ "modelExt": ".1902042334", "texExt": ".190820018", "mmtrExt": ".1905100741", "nDir": "stm", "mdfExt": ".mdf2.13", "meshVersion": 1, "mdfVersion": 2, "mlistExt": ".99", "meshMagic":386270720, "motionIDsData":[24,8] },
	"RE8": 			{ "modelExt": ".2101050001", "texExt": ".30", 		 "mmtrExt": ".2102188797", "nDir": "stm", "mdfExt": ".mdf2.19", "meshVersion": 2, "mdfVersion": 3, "mlistExt": ".486", "meshMagic":2020091500, "motionIDsData":[24,8] },
	"MHRise":		{ "modelExt": ".2008058288", "texExt": ".28", 		 "mmtrExt": ".2109301553", "nDir": "stm", "mdfExt": ".mdf2.19", "meshVersion": 2, "mdfVersion": 3, "mlistExt": ".484", "meshMagic":21091000, "motionIDsData":[72,8] },
	"MHRSunbreak":	{ "modelExt": ".2109148288", "texExt": ".28", 		 "mmtrExt": ".220427553",  "nDir": "stm", "mdfExt": ".mdf2.23", "meshVersion": 2, "mdfVersion": 3, "mlistExt": ".528", "meshMagic":21091000, "motionIDsData":[72,8] },
	"ReVerse":		{ "modelExt": ".2102020001", "texExt": ".31", 		 "mmtrExt": ".2108110001", "nDir": "stm", "mdfExt": ".mdf2.20", "meshVersion": 2, "mdfVersion": 3, "mlistExt": ".500", "meshMagic":2020091500, "motionIDsData":[24,8] },
	"RERT": 		{ "modelExt": ".2109108288", "texExt": ".34", 		 "mmtrExt": ".2109101635", "nDir": "stm", "mdfExt": ".mdf2.21", "meshVersion": 2, "mdfVersion": 3, "mlistExt": ".524", "meshMagic":21041600, "motionIDsData":[72,8] },
	"RE7RT": 		{ "modelExt": ".220128762",  "texExt": ".35", 		 "mmtrExt": ".2109101635", "nDir": "stm", "mdfExt": ".mdf2.21", "meshVersion": 2, "mdfVersion": 3, "mlistExt": ".524", "meshMagic":21041600, "motionIDsData":[72,8] },
	"SF6": 			{ "modelExt": ".230110883",  "texExt": ".143230113", "mmtrExt": ".221102761",  "nDir": "stm", "mdfExt": ".mdf2.31", "meshVersion": 3, "mdfVersion": 4, "mlistExt": ".653", "meshMagic":230403828, "motionIDsData":[72,8] },
	"ExoPrimal": 	{ "modelExt": ".220907984",  "texExt": ".40", 		 "mmtrExt": ".221007878",  "nDir": "stm", "mdfExt": ".mdf2.31", "meshVersion": 3, "mdfVersion": 4, "mlistExt": ".643", "meshMagic":220705151, "motionIDsData":[72,8] },
	"RE4": 			{ "modelExt": ".221108797",  "texExt": ".143221013", "mmtrExt": ".221007879",  "nDir": "stm", "mdfExt": ".mdf2.32", "meshVersion": 3, "mdfVersion": 4, "mlistExt": ".663", "meshMagic":220822879, "motionIDsData":[72,8] },
	"AJ_AAT": 		{ "modelExt": ".230612127",  "texExt": ".719230324", "mmtrExt": ".230815080",  "nDir": "stm", "mdfExt": ".mdf2.37", "meshVersion": 3, "mdfVersion": 4, "mlistExt": ".750", "meshMagic":230406984, "motionIDsData":[72,8] },
	"DD2": 			{ "modelExt": ".231011879",  "texExt": ".760230703", "mmtrExt": ".230815080",  "nDir": "stm", "mdfExt": ".mdf2.40", "meshVersion": 3, "mdfVersion": 4, "mlistExt": ".751", "meshMagic":230517984, "motionIDsData":[72,8] },
	"DRDR": 		{ "modelExt": ".240424828",  "texExt": ".240606151", "mmtrExt": ".240405143",  "nDir": "stm", "mdfExt": ".mdf2.40", "meshVersion": 3, "mdfVersion": 4, "mlistExt": ".854", "meshMagic":240423829, "motionIDsData":[72,8] },
	"PRAGMATA": 	{ "texVersion": 251111100, "modelExt": ".251121828",  "texExt": ".251111100",   "mmtrExt": "",            "nDir": "stm", "mdfExt": ".mdf2.51", "meshVersion": 3, "mdfVersion": 5, "mlistExt": "",     "meshMagic":250707828, "motionIDsData":[72,8] },
}

extToFormat = { #incomplete, just testing
	"10": {
		"albm":   [99,5],
		"albmsc": [99,5],
		"alba":	  [99,1],
		"alb":    [72,0],
		"nrmr":   [98,6],
		"nrm":	  [98,1],
		"iam":	  [99,8],
		"atos":   [71,4],
		"msk1":   [80,3],
	},
	"34": {
		"albm":   [99,5],
		"albmsc": [99,5],
		"alba":	  [99,1],
		"alb":    [72,0],
		"nrmr":   [98,6],
		"nrm":	  [98,1],
		"iam":	  [99,8],
		"atos":   [71,4],
		"msk1":   [80,3],
	},
}

extToFormat["8"] = extToFormat["10"]

extToFormat["11"] = extToFormat["10"]

extToFormat["190820018"] = extToFormat["10"]

extToFormat["30"] = extToFormat["34"]

extToFormat["35"] = extToFormat["34"]

extToFormat["28"] = extToFormat["34"]

extToFormat["143221013"] = extToFormat["34"]

extToFormat["28.stm"] = extToFormat["28"]

texFormatNames = {
	0: "UNKNOWN",
	1: "R32G32B32A32_TYPELESS",
	2: "R32G32B32A32_FLOAT",
	3: "R32G32B32A32_UINT",
	4: "R32G32B32A32_SINT",
	5: "R32G32B32_TYPELESS",
	6: "R32G32B32_FLOAT",
	7: "R32G32B32_UINT",
	8: "R32G32B32_SINT",
	9: "R16G16B16A16_TYPELESS",
	10: "R16G16B16A16_FLOAT",
	11: "R16G16B16A16_UNORM",
	12: "R16G16B16A16_UINT",
	13: "R16G16B16A16_SNORM",
	14: "R16G16B16A16_SINT",
	15: "R32G32_TYPELESS",
	16: "R32G32_FLOAT",
	17: "R32G32_UINT",
	18: "R32G32_SINT",
	19: "R32G8X24_TYPELESS",
	20: "D32_FLOAT_S8X24_UINT",
	21: "R32_FLOAT_X8X24_TYPELESS",
	22: "X32_TYPELESS_G8X24_UINT",
	23: "R10G10B10A2_TYPELESS",
	24: "R10G10B10A2_UNORM",
	25: "R10G10B10A2_UINT",
	26: "R11G11B10_FLOAT",
	27: "R8G8B8A8_TYPELESS",
	28: "R8G8B8A8_UNORM",
	29: "R8G8B8A8_UNORM_SRGB",
	30: "R8G8B8A8_UINT",
	31: "R8G8B8A8_SNORM",
	32: "R8G8B8A8_SINT",
	33: "R16G16_TYPELESS",
	34: "R16G16_FLOAT",
	35: "R16G16_UNORM",
	36: "R16G16_UINT",
	37: "R16G16_SNORM",
	38: "R16G16_SINT",
	39: "R32_TYPELESS",
	40: "D32_FLOAT",
	41: "R32_FLOAT",
	42: "R32_UINT",
	43: "R32_SINT",
	44: "R24G8_TYPELESS",
	45: "D24_UNORM_S8_UINT",
	46: "R24_UNORM_X8_TYPELESS",
	47: "X24_TYPELESS_G8_UINT",
	48: "R8G8_TYPELESS",
	49: "R8G8_UNORM",
	50: "R8G8_UINT",
	51: "R8G8_SNORM",
	52: "R8G8_SINT",
	53: "R16_TYPELESS",
	54: "R16_FLOAT",
	55: "D16_UNORM",
	56: "R16_UNORM",
	57: "R16_UINT",
	58: "R16_SNORM",
	59: "R16_SINT",
	60: "R8_TYPELESS",
	61: "R8_UNORM",
	62: "R8_UINT",
	63: "R8_SNORM",
	64: "R8_SINT",
	65: "A8_UNORM",
	66: "R1_UNORM",
	67: "R9G9B9E5_SHAREDEXP",
	68: "R8G8_B8G8_UNORM",
	69: "G8R8_G8B8_UNORM",
	70: "BC1_TYPELESS",
	71: "BC1_UNORM",
	72: "BC1_UNORM_SRGB",
	73: "BC2_TYPELESS",
	74: "BC2_UNORM",
	75: "BC2_UNORM_SRGB",
	76: "BC3_TYPELESS",
	77: "BC3_UNORM",
	78: "BC3_UNORM_SRGB",
	79: "BC4_TYPELESS",
	80: "BC4_UNORM",
	81: "BC4_SNORM",
	82: "BC5_TYPELESS",
	83: "BC5_UNORM",
	84: "BC5_SNORM",
	85: "B5G6R5_UNORM",
	86: "B5G5R5A1_UNORM",
	87: "B8G8R8A8_UNORM",
	88: "B8G8R8X8_UNORM",
	89: "R10G10B10_XR_BIAS_A2_UNORM",
	90: "B8G8R8A8_TYPELESS",
	91: "B8G8R8A8_UNORM_SRGB",
	92: "B8G8R8X8_TYPELESS",
	93: "B8G8R8X8_UNORM_SRGB",
	94: "BC6H_TYPELESS",
	95: "BC6H_UF16",
	96: "BC6H_SF16",
	97: "BC7_TYPELESS",
	98: "BC7_UNORM",
	99: "BC7_UNORM_SRGB",
	100: "AYUV",
	101: "Y410",
	102: "Y416",
	103: "NV12",
	104: "P010",
	105: "P016",
	106: "_420_OPAQUE",
	107: "YUY2",
	108: "Y210",
	109: "Y216",
	110: "NV11",
	111: "AI44",
	112: "IA44",
	113: "P8",
	114: "A8P8",
	115: "B4G4R4A4_UNORM",
	130: "P208",
	131: "V208",
	132: "V408",
	0xffffffff:  "FORCE_UINT" 
}

fmtNameToBpp = {
    "R32G32B32A32_TYPELESS": 128,
    "R32G32B32A32_FLOAT": 128,
    "R32G32B32A32_UINT": 128,
    "R32G32B32A32_SINT": 128,
    "R32G32B32_TYPELESS": 96,
    "R32G32B32_FLOAT": 96,
    "R32G32B32_UINT": 96,
    "R32G32B32_SINT": 96,
    "R16G16B16A16_TYPELESS": 64,
    "R16G16B16A16_FLOAT": 64,
    "R16G16B16A16_UNORM": 64,
    "R16G16B16A16_UINT": 64,
    "R16G16B16A16_SNORM": 64,
    "R16G16B16A16_SINT": 64,
    "R32G32_TYPELESS": 64,
    "R32G32_FLOAT": 64,
    "R32G32_UINT": 64,
    "R32G32_SINT": 64,
    "R32G8X24_TYPELESS": 64,
    "D32_FLOAT_S8X24_UINT": 64,
    "R32_FLOAT_X8X24_TYPELESS": 64,
    "X32_TYPELESS_G8X24_UINT": 64,
    "Y416": 64,
    "Y210": 64,
    "Y216": 64,
    "R10G10B10A2_TYPELESS": 32,
    "R10G10B10A2_UNORM": 32,
    "R10G10B10A2_UINT": 32,
    "R11G11B10_FLOAT": 32,
    "R8G8B8A8_TYPELESS": 32,
    "R8G8B8A8_UNORM": 32,
    "R8G8B8A8_UNORM_SRGB": 32,
    "R8G8B8A8_UINT": 32,
    "R8G8B8A8_SNORM": 32,
    "R8G8B8A8_SINT": 32,
    "R16G16_TYPELESS": 32,
    "R16G16_FLOAT": 32,
    "R16G16_UNORM": 32,
    "R16G16_UINT": 32,
    "R16G16_SNORM": 32,
    "R16G16_SINT": 32,
    "R32_TYPELESS": 32,
    "D32_FLOAT": 32,
    "R32_FLOAT": 32,
    "R32_UINT": 32,
    "R32_SINT": 32,
    "R24G8_TYPELESS": 32,
    "D24_UNORM_S8_UINT": 32,
    "R24_UNORM_X8_TYPELESS": 32,
    "X24_TYPELESS_G8_UINT": 32,
    "R9G9B9E5_SHAREDEXP": 32,
    "R8G8_B8G8_UNORM": 32,
    "G8R8_G8B8_UNORM": 32,
    "B8G8R8A8_UNORM": 32,
    "B8G8R8X8_UNORM": 32,
    "R10G10B10_XR_BIAS_A2_UNORM": 32,
    "B8G8R8A8_TYPELESS": 32,
    "B8G8R8A8_UNORM_SRGB": 32,
    "B8G8R8X8_TYPELESS": 32,
    "B8G8R8X8_UNORM_SRGB": 32,
    "AYUV": 32,
    "Y410": 32,
    "YUY2": 32,
    "P010": 24,
    "P016": 24,
    "R8G8_TYPELESS": 16,
    "R8G8_UNORM": 16,
    "R8G8_UINT": 16,
    "R8G8_SNORM": 16,
    "R8G8_SINT": 16,
    "R16_TYPELESS": 16,
    "R16_FLOAT": 16,
    "D16_UNORM": 16,
    "R16_UNORM": 16,
    "R16_UINT": 16,
    "R16_SNORM": 16,
    "R16_SINT": 16,
    "B5G6R5_UNORM": 16,
    "B5G5R5A1_UNORM": 16,
    "A8P8": 16,
    "B4G4R4A4_UNORM": 16,
    "NV12": 12,
    "420_OPAQUE": 12,
    "NV11": 12,
    "BC2_TYPELESS": 8,
    "BC2_UNORM": 8,
    "BC2_UNORM_SRGB": 8,
    "BC3_TYPELESS": 8,
    "BC3_UNORM": 8,
    "BC3_UNORM_SRGB": 8,
    "BC5_TYPELESS": 8,
    "BC5_UNORM": 8,
    "BC5_SNORM": 8,
    "BC6H_TYPELESS": 8,
    "BC6H_UF16": 8,
    "BC6H_SF16": 8,
    "BC7_TYPELESS": 8,
    "BC7_UNORM": 8,
    "BC7_UNORM_SRGB": 8,
    "R8_TYPELESS": 8,
    "R8_UNORM": 8,
    "R8_UINT": 8,
    "R8_SNORM": 8,
    "R8_SINT": 8,
    "A8_UNORM": 8,
    "AI44": 8,
    "IA44": 8,
    "P8": 8,
    "R1_UNORM": 1,
    "BC1_TYPELESS": 4,
    "BC1_UNORM": 4,
    "BC1_UNORM_SRGB": 4,
    "BC4_TYPELESS": 4,
    "BC4_UNORM": 4,
    "BC4_SNORM": 4
}

gamesList = [ "RE7", "RE7RT", "RE2", "RERT", "RE3", "RE4", "RE8", "MHRSunbreak", "DMC5", "SF6", "ReVerse", "ExoPrimal", "AJ_AAT", "DD2", "DRDR", "PRAGMATA" ]

fullGameNames = [
	"Resident Evil 7",
	"Resident Evil 7 RT",
	"Resident Evil 2",
	"Resident Evil 2/3 RT",
	"Resident Evil 3",
	"Resident Evil 4",
	"Resident Evil 8",
	"MH Rise Sunbreak",
	"Devil May Cry 5",
	"Street Fighter 6",
	"Resident Evil ReVerse",
	"ExoPrimal",
	"Apollo Justice AAT",
	"Dragon's Dogma 2",
	"Dead Rising DR",
	"Pragmata",
]
