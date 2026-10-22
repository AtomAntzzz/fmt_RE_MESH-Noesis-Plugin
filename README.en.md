# RE Engine Noesis / Maya Tool

[中文](./README.md) | [English](./README.en.md)

This repository combines alphaZomega's Noesis plugin for RE Engine assets with AtomAntzzz's Maya animation workflow under one maintained project. The current release tree does not include the 3ds Max MaxScripts.

## Files

- `fmt_RE_MESH.py`: the Noesis plugin for RE Engine MESH, TEX, MDF/MDF2, MOTLIST, and related assets.
- `re_engine_*.py`: internal modules organized by responsibility; `re_engine_common.py` preserves the original shared interfaces. Install these alongside the entry point.
- `pragmata_gdeflate_x86.dll` / `pragmata_gdeflate_x64.dll`: the GDeflate CPU bridge used by compressed PRAGMATA and Monster Hunter Wilds TEX files.
- `REEM_Noesis_Maya.py`: a Maya tool that drives Noesis for MESH/MOTLIST import, reads animation logs, and splits clips in batches.

## Supported games

- Resident Evil 2 Remake
- Resident Evil 3 Remake
- Resident Evil 4 Remake
- Resident Evil 7 (Ray Tracing)
- Resident Evil 8
- Devil May Cry 5
- Monster Hunter Rise
- Street Fighter 6
- Exoprimal
- Apollo Justice: Ace Attorney Trilogy
- Dragon's Dogma 2
- PRAGMATA (models, materials, textures, standalone skeletal animation, and mesh animation binding; see scope below)
- Monster Hunter Wilds (models, basic materials, textures, and mesh-bound animation; see scope below)

The first 11 games retain alphaZomega's public v3.28 support list; PRAGMATA and Monster Hunter Wilds support are added by this fork. Features vary by game. Wilds is implemented in the local branch and has not yet been integrated into the public release. Resident Evil 9 is not on the supported list.

Games share a basic material preview pipeline: locate the model's materials and textures, then apply common mappings for supported color, normal/roughness, transparency, and emission slots. PRAGMATA now uses this pipeline in the local branch; this change is not yet publicly released. Noesis provides an approximate preview, without reproducing full game shaders. Eyes, skin, and layered materials may look different. UE-specific materials and one-click import by slot are not implemented.

## Monster Hunter Wilds: available features

Model, basic material, and texture import and preview are supported, along with binding and playback of compatible animations. Validation uses Windows Steam build 24705561; other builds and game-wide compatibility coverage have not been measured.

| Feature | Available behavior | Known limitations |
| --- | --- | --- |
| Models | Geometry, skeletons, weights, LODs, paired streaming data, and observed MPLY layouts; representative previews cover a static four-part player, handheld/worn equipment, humanoid/nonhuman characters, a building canopy, small props, a simplified tree, and low foliage | 75 of 80 fixed models pass basic material import; 5 are rejected for position encoding or streaming index layouts. Another 5 plant samples pass. Assembled-body animation, other layouts, and game-wide coverage are unverified |
| Materials | Shared lookup tries the exact name, `_mat`, `_00`, `_v00`, and `_a`, then the same game's extraction directory and optional shared-material links with mesh/MDF hash checks; basic color, normal/roughness, and emissive display | Ordinary candidates retain priority; other variants can be selected manually. Links need a verified scene context. Player skin colors may differ between parts, and some terrain appears very dark with default lighting; proprietary shaders and complex blending are not fully supported |
| Textures | TEX decoding and basic display for observed raw/GDeflate data and paired streaming resources | Volume preview uses the first slice; unobserved layouts or codecs may be rejected |
| Animation | Select, bind, and play compatible MOTLIST actions on a model, including multiple actions and cross-file queues; three observed translation encodings are now supported | All 155 unique actions (179 entries) in two natural motion files pass decoding and host binding. Other actions and model pairings have not been comprehensively tested. Standalone opening of `.motlist.992` is not supported |

Applicable file versions: `.mesh.241111606`, `.mdf2.45`, `.tex.241106027`, and `.motlist.992`. Preserve the extracted `natives/stm` and `streaming` directory structure. Models, materials, and textures should come from the same build; renaming an older texture suffix does not convert its format.

Character material lookup now includes a constrained fallback for MDF files shared between male and female variants. Explicit MDF45 primary color and normal slots take priority over detail or damage textures. Vertex colors on character paths are treated as shader masks and are no longer multiplied into preview colors. The parser retains the raw data, but the resulting Noesis models and subsequent standard-format exports omit that vertex color stream. Dark eyes, white FakeAO helper surfaces, and some skin-color differences remain known limitations of the basic preview.

Foliage edges use explicit material alpha-test flags together with an actual mask slot. Solid foliage on the simplified tree does not establish individual-leaf fidelity. Vegetation requiring a new `.stmesh` / STM8 reader is excluded from this delivery, including an identified grass/reed-like example; this does not imply that all grass uses that format.

64-bit Noesis is recommended. Open a model and use the existing animation selection window to load actions; unsupported actions are explicitly rejected. In-game shaders, procedural IK, MTRE semantics, native file writing, and in-game validation are outside current support. Noesis conversion to standard formats is separate from native game-file writing; Maya animation export has not been validated.

## PRAGMATA: available features

Model, basic material, texture, and skeletal animation import and preview are implemented. Textures have large-scale structural validation; models, materials, and animations have representative-sample validation. Game-wide compatibility coverage has not been measured, and some models or actions may still fail to load.

| Feature | Available behavior | Validation and limits |
| --- | --- | --- |
| Models and skeletons | Import geometry, skeletons, and weights; observed multi-material, multi-LOD, single/dual-data-segment streaming and some MPLY layouts; representative previews cover the player, handheld/worn equipment, humanoid/nonhuman characters, a building scene, small props, trees, and low foliage | 83 of 96 fixed models import geometry (82 with basic textures and 1 legitimate textureless outline); 13 remain rejected. Other layouts, game-wide coverage, and per-model visual checks are incomplete |
| Basic materials | Shared lookup and basic color, normal/roughness, alpha-test, and emission display; all 13,032 MDF files in the available extraction pass parsing | Parsing is not full effect reproduction. Eyes may be white, some regions dark, and nonzero emission pure white. Layered surfaces, decals, and glass in large scenes may look black/white or spotted; complex blending is incomplete |
| Textures | raw/GDeflate decoding, array layers and cubemap faces, optional mip loading | 22,346 files in the available extraction passed structural parsing; representatives of 15 pixel formats plus arrays, cubes, and volumes passed Noesis conversion. This is not per-file pixel or visual validation; volume preview uses the first slice |
| Skeletal animation | Standalone skeleton preview, mesh binding, action selection, and cross-file queues | Tested on one single-action sample, 24 motion-bearing files in the player directory, and representative player-model bindings. Other characters, motion layouts, and model/action pairings have not been comprehensively validated |
| Morphs | Numeric-frame preview on some models | Source-named morph selection is not provided; not every facial model has been tested |

Applicable file versions: `.mesh.251121828`, `.mdf2.51`, `.tex.251111100`, and `.motlist.1057` (MOT 993). A matching suffix does not guarantee compatibility; game updates may also change the layout.

Vegetation requiring new `.stmesh` / STM8 support is excluded, including identified grass-blade, flowering-herb, and fern examples. Ordinary MESH/MPLY trees, low foliage, and leaf litter have previews; other unconfirmed live grass is neither claimed as supported nor declared absent. Fixed batch successes indicate actual parsing/loading, not individual visual acceptance of every file.

### Open models and play animations

- Preserve the extracted directory structure and companion files. For streaming models, open the main mesh and keep its streaming companion available; do not open headerless streaming data on its own.
- Open a MOTLIST directly to preview its own skeleton, or load actions onto a model.
- To bind animations: open a MESH → `Select Animations` → select a MOTLIST (a full path can be pasted) → double-click an action or `[ALL]` to queue it → click `Load` to return → click `Load` in the model dialog.
- This uses the same shared animation selection dialog as DD2. Queue actions from multiple files; cancelling and reopening retains the directory and queue.
- Tracks for bones absent from the model are skipped and counted. Binding is rejected when no tracks match or a known parent-space conflict exists. Arbitrary models and actions are not interchangeable.
- `Force Center`, `Sync by Frame Count`, and `Force Merge All` are unavailable and disabled for PRAGMATA; the existing DD2 options remain available.

### Known limitations

- Basic material display is complete; full game shaders are not reproduced. Reading a material parameter does not mean its effect is rendered.
- Common mapping may choose a different primary texture, including a damage texture. The face EyeShell OBJ/MTL texture path may differ from the generated PNG filename and require manual correction. Exported materials are not guaranteed to work directly in UE.
- MTRE animation data is not supported; MTRE-only files cannot be loaded as skeletal actions.
- Repeatedly reloading large MOTLIST files in 32-bit Noesis can run out of memory. This also occurs in the older version and remains unfixed. Repeated reloads of the same large sample have not been verified in 64-bit Noesis, so switching architectures is not a guaranteed fix.
- Native PRAGMATA MESH/TEX/MOTLIST writing, independent re-import, and in-game validation workflows are not provided. The plugin does not produce files validated for writing back into the game.
- This does not prevent Noesis from converting imported content to standard formats such as FBX, OBJ, PNG, or TGA. Preservation of skeletons, animations, and morphs depends on the exporter and its options; not every conversion combination has been tested.

## Install the Noesis plugin

1. Download and install Noesis from the [official Noesis page](https://www.richwhitehouse.com/index.php?content=inc_projects&showproject=91).
2. Copy `fmt_RE_MESH.py` and all root-level `re_engine_*.py` files into `[Noesis installation]/plugins/python/`, for a total of 21 Python runtime files. Replace the whole module set when updating; do not mix versions.
3. For 32-bit `Noesis.exe`, put `pragmata_gdeflate_x86.dll` in the same `plugins/python/` directory. For 64-bit `Noesis64.exe`, use `pragmata_gdeflate_x64.dll`.
4. Both DLLs may coexist; the plugin selects by the running Noesis process architecture. Restart Noesis, then open a model, texture, or motion file.

Both games use this same plugin set; separate installations are unnecessary. To preview materials, enable `Load Textures` in the model loading dialog before clicking `Load`. With this option disabled, only the model is loaded.

For cutout foliage, set `Tools → Data Viewer → Persistent settings → View → Render opacity mask` to `1` and keep shading enabled (`F5` toggles it). Disabling shading may hide leaves. Wind and full game material effects are not provided. The plugin package contains no game assets; any additional resource root must preserve the corresponding `natives/stm` and `streaming` structure.

If the log reports `gdeflate-helper-missing`, check that the matching DLL is in the directory above. Uncompressed textures do not need this helper; GDeflate-compressed textures do. See the [GDeflate notes](./tools/pragmata_gdeflate/README.md) for component details and licenses.

## Maya animation workflow

1. In Maya, open **Windows → General Editors → Script Editor**.
2. Use **File → Open Script** to select `REEM_Noesis_Maya.py`, then save it to a shelf.
3. In REEM, select the Noesis executable and a `.mesh.*` or `.motlist.*` file.
4. For MOTLIST files supported by upstream, double-click `[ALL]` in the Noesis selector, load, and export clips.

The PRAGMATA Maya animation export workflow has not been validated. Successful binding and playback in Noesis do not validate the exported Maya result.

## Sources and notice

- Noesis plugin source: [alphazolam/fmt_RE_MESH-Noesis-Plugin](https://github.com/alphazolam/fmt_RE_MESH-Noesis-Plugin)
- Original Maya repository: [AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool](https://github.com/AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool)

See [NOTICE.md](./NOTICE.md) for source attribution, merged history, third-party GDeflate components, and rights information. Commercial samples, complete filename lists, extraction manifests, logs, and screenshots are not distributed here.
