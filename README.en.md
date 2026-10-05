# RE Engine Noesis / Maya Tool

[中文](./README.md) | [English](./README.en.md)

This repository combines alphaZomega's Noesis plugin for RE Engine assets with AtomAntzzz's Maya animation workflow under one maintained project. The current release tree does not include the 3ds Max MaxScripts.

## Files

- `fmt_RE_MESH.py`: the Noesis plugin for RE Engine MESH, TEX, MDF/MDF2, MOTLIST, and related assets.
- `re_engine_*.py`: internal modules organized by responsibility; `re_engine_common.py` preserves the original shared interfaces. Install these alongside the entry point.
- `pragmata_gdeflate_x86.dll` / `pragmata_gdeflate_x64.dll`: the GDeflate CPU bridge required by PRAGMATA TEX.
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
- PRAGMATA (models, materials, textures, and standalone skeletal animation; see scope below)

The first 11 games retain alphaZomega's public v3.28 support list; PRAGMATA support is added by this fork. Available features vary by game. Resident Evil 9 and Monster Hunter Wilds are outside this repository's current verified statement. PRAGMATA support covers observed profiles only; it is not a claim for every build, character, or file sharing the same suffix.

## PRAGMATA support scope

`readable` means that a frozen structural profile can be read safely. `previewable` additionally requires separate Noesis preview evidence. Capability selection uses internal versions and structural invariants, not the game name or external suffix alone.

| Asset | Observed identity | Current statement |
| --- | --- | --- |
| MESH/MPLY | `.mesh.251121828`, internal `250707828`, `MESH` or `MPLY` magic | Frozen ordinary candidate 002, standalone multi-material, standalone multi-LOD, the RE-067A reserved-ushort submission boundary, candidate 001 paired streaming, the RE-067B compact one-entry paired-streaming profile, the RE-067C binary16 blend-shape profile, paired MPLY, playergame, and face base-geometry profiles are scoped `readable`; only subsets with separate Noesis GUI evidence are `previewable`. |
| TEX | `.tex.251111100`, internal `251111100` | The observed structural matrix is bounds-safe `readable`; the original 256×256 BC7 / 6-mip exact profile has an independent pixel oracle and is `previewable`. Other formats are limited to the representative evidence below. |
| MDF2 | `.mdf2.51`, observed header version `1` | The candidate 002 single-material exact profile and observed playergame/face multi-material profiles can be parsed and bound. Proprietary master-shader fidelity is not claimed. |
| MOTLIST | Frozen `.motlist.1057` / MOT `993` standalone profiles | The RE-066 single-action/local-bone exact profile and RE-068's 24 observed multi-action/shared-bones profiles are scoped `readable` / `previewable`, using the same shared animation selection dialog as DD2. |

The frozen MESH scope includes ordinary, multi-material, multi-LOD, one paired streaming profile, and one paired MPLY profile. Candidate 002 has geometry/materialized GUI evidence, and multi-LOD has geometry GUI evidence. Player/face now have skeleton-overlay and deterministic diagnostic-pose evidence, but that validates only the observed 12-slot weight influence; it is not full character shading, usable shape keys, or natural-animation preview. Paired streaming/MPLY subsets without independent GUI evidence are not automatically promoted to `previewable` merely because the parser can read them.

TEX breadth evidence covers a structural inventory of 22,346 observed `.tex.251111100` files. Real Noesis runs covered 15 observed DXGI formats plus representative array, cube, and volume files. Only the original exact BC7 profile has an independent pixel-by-pixel oracle; the rest prove an operational representative decode/export path, not pixel-exact coverage for every TEX.

### Player/face evidence limits

- `playergame_mat.mdf2.51`: 14 materials, 206 texture references, and 1,380 properties; headless Noesis created 14 materials and decoded 25 physical TEX files.
- `ch0000_10_mat.mdf2.51`: 6 materials, 51 texture references, and 420 properties; headless Noesis created 6 materials and decoded 8 physical TEX files.
- Material completion means parity with alphazolam's basic texture mapping, not reconstruction of the proprietary PRAGMATA shader. `BaseColor`, albedo-to-diffuse, normal/roughness-to-normal, and basic emissive routing are covered; the GUI reports player `14/25` and face `6/8` Materials/Textures, so this basic material scope is complete. The face iris, unverified packed channels, and master-shader fidelity remain additional coverage debt and do not block that basic claim.
- All 91 observed `ch0000_10` shapes have finite deltas, nonzero statistics, and constructed morph frames. Real Noesis shows numeric frames 4/18, but source-named selection/toggleable shape-key behavior is still unverified, so deformation as a whole is not claimed as `previewable`.
- The observed `ch0100_10` encoding `2` is accepted only for the frozen exact profile with `padding1=1`, submesh reserved `0x100`, and `4 × binary16` records (XYZ plus zero padding). An independent raw-byte oracle and the production parser both verify 107 × 10,982 finite deltas and payload SHA-256 `b9a53224...d5bb6`; real Noesis imports the model and constructs 107 source-named morph frames on the target submesh. This CLI evidence makes that exact profile scoped `readable`, not `previewable`: no GUI toggle evidence exists, and no other encoding or metadata layout is implied.
- The primary+extra 12-slot weight storage and bone-name mapping were checked independently. The observed maxima are 8 nonzero influences for playergame and 9 for face. Real Noesis skeleton overlays and independent pose OBJs validate 6,148 changed player vertices for `L_UpperArm_Twist_2` and 1,871 changed face vertices for `C_Jaw`, both with 0 escaped and no wrong-side mirroring, origin spikes, or explosions. This is a deterministic source-X translation influence diagnostic, not a claim for natural animation, MOTLIST, export, independent re-import, or game runtime.

## Install the Noesis plugin

1. Download and install Noesis from the [official Noesis page](https://www.richwhitehouse.com/index.php?content=inc_projects.php&showproject=91).
2. Copy `fmt_RE_MESH.py` and all root-level `re_engine_*.py` files into `[Noesis installation]/plugins/python/`, keeping all 20 Python runtime files in the same directory. Update the complete module set from the same revision.
3. For 32-bit `Noesis.exe`, place `pragmata_gdeflate_x86.dll` in the same `plugins/python/` directory. For 64-bit `Noesis64.exe`, place `pragmata_gdeflate_x64.dll` there.
4. Both DLLs may coexist. The plugin selects one from the current process pointer size and will not load an x86 DLL into an x64 process or vice versa.
5. Restart Noesis and open a supported `.mesh.*`, `.tex.*`, or frozen exact-profile `.motlist.1057` file.

Without a matching DLL, uncompressed TEX profiles may still work, but TEX files that require GDeflate fail explicitly with `gdeflate-helper-missing:pragmata_gdeflate_x86.dll` or `gdeflate-helper-missing:pragmata_gdeflate_x64.dll`. There is no silent fallback that displays incorrect pixels. Fixed DLL hashes, PE architecture, ABI, source provenance, and license details are in [`tools/pragmata_gdeflate/README.md`](./tools/pragmata_gdeflate/README.md).

### MOTLIST exact-profile boundary

RE-066 is complete for the frozen PRAGMATA MOTLIST v1057 / MOT v993 single-action, local-bone standalone exact profile: an independent oracle agrees on all 21 compressed tracks, and Noesis uses `NoeKeyFramedAnim` from the `NoeAnim` family to import and play the 9-bone, 7-animated-bone, 21-logical-track, 125-frame/60-FPS action.

RE-068 additionally verifies 24 observed multi-action/shared-bones profiles, including observed dense/sparse/mixed entries and shared skeleton layouts. These standalone profiles are scoped `readable` / `previewable` and reuse the same shared animation selection dialog as DD2, including file switching, action selection, and queued loading.

Open PRAGMATA MOTLIST files directly to preview animations with their own skeleton. Direct external MESH binding through the MESH `Select Animations` entry point failed validation in Noesis and is currently unsupported; do not force a PRAGMATA MOTLIST path through that entry point. Tracks that cannot be matched to the skeleton follow the existing skip policy, with the skipped count logged.

This scope does not cover other v1057 layouts outside the observed matrix, MTRE semantics, the 5 MTRE-only files, MOTLIST export, independent re-import, or game runtime. It does not imply support for every `.motlist.1057` file.

## Explicitly unsupported PRAGMATA scope

- General PRAGMATA MESH/TEX writing is not supported and is excluded from the support targets. This means writing native game `.mesh.*` / `.tex.*` files. Candidate 002 has only an experimental, single-sample, source-template exact writer implementation; it is neither general export nor a supported write-back feature.
- This exclusion does not refer to converting loaded models or textures to standard formats such as FBX, OBJ, PNG, or TGA using Noesis exporters. Preservation of skeletons, animations, or morphs depends on the exporter and its options; not every combination has been validated.
- Independent re-import is not provided. The two upstream MaxScripts only perform a 3ds Max FBX → Noesis FBX merge → FBX return trip and do not read PRAGMATA MESH writer output.
- Game runtime has not been validated. Writer output is not claimed to be accepted by the game or an official tool.
- Proprietary master shaders, unverified packed channels, patch-only profiles, other builds, and every file sharing a suffix are not guaranteed.

## Maya animation workflow

1. In Maya, open **Windows → General Editors → Script Editor**.
2. Use **File → Open Script** to select `REEM_Noesis_Maya.py`, then save it to a shelf.
3. In REEM, select the Noesis executable and a `.mesh.*` or `.motlist.*` file.
4. For MOTLIST files supported by upstream, double-click `[ALL]` in the Noesis selector, load, and export clips.

This general Maya workflow does not broaden the RE-066/RE-068 standalone profiles above. The PRAGMATA Maya animation export workflow has not been validated; external MESH binding, out-of-scope layouts, export, independent re-import, and runtime remain unavailable.

## Sources and notice

- Noesis plugin source: [alphazolam/fmt_RE_MESH-Noesis-Plugin](https://github.com/alphazolam/fmt_RE_MESH-Noesis-Plugin)
- Original Maya repository: [AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool](https://github.com/AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool)

See [NOTICE.md](./NOTICE.md) for source attribution, merged history, third-party GDeflate components, and rights information. No PRAGMATA commercial samples, filename lists, extraction manifests, logs, screenshots, or test evidence artifacts are distributed here.
