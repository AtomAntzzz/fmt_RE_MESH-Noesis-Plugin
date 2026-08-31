# RE Engine Noesis / Maya Tool

[中文](./README.md) | [English](./README.en.md)

This repository combines alphaZomega's Noesis plugin for RE Engine assets with AtomAntzzz's Maya animation workflow under one maintained project. The current tree does not include the 3ds Max MaxScript tools.

## Files

- `fmt_RE_MESH.py`: a Noesis plugin for reading and exporting RE Engine MESH, TEX, MDF/MDF2, MOTLIST, and related assets.
- `REEM_Noesis_Maya.py`: a Maya tool that drives Noesis to import MESH/MOTLIST files, reads animation logs, and splits animation clips in batches.

## Games listed by upstream v3.28

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

This list is retained from alphaZomega's public v3.28 documentation. It does not claim support for newer games that have not completed sample-based regression. Resident Evil 9 and Monster Hunter Wilds are not part of this repository's currently verified support statement; PRAGMATA has only the strictly scoped single-profile support described below.

## Scoped PRAGMATA support

Current support is limited to one observed candidate 002 exact MESH profile: external suffix `.mesh.251121828`, internal version `250707828`, ordinary standalone, non-MPLY, skinned, with one LOD / group / submesh. The frozen sample SHA-256 is `78001dd7dd85da34434e48ae4a9426ba71d023d54dab30f3c490f69471fa4068`.

- Read-only import of this exact profile is `readable`; its geometry-only Noesis preview is `previewable`.
- GUI verification reported `Models 1 / Meshes 1 / Textures 0 / Materials 0 / Bones 229`. Zero textures/materials means materialized preview is not supported, and visual correctness of bones/weights has not been verified.
- Candidate 001, other `.251121828` structures, multi-LOD, multi-material, streaming, MPLY, TEX/MDF2/MOTLIST, export, independent re-import, and game runtime are outside this claim.
- The plugin fails this capability closed when files with the same suffix do not satisfy the exact structural invariants. This single-sample profile must not be read as support for the whole PRAGMATA format family.

No PRAGMATA commercial samples, filename lists, extraction manifests, or GUI evidence files are included in this repository.

## Install the Noesis plugin

1. Download and install Noesis from the [official Noesis page](https://www.richwhitehouse.com/index.php?content=inc_projects.php&showproject=91).
2. Copy `fmt_RE_MESH.py` into `[Noesis installation]/plugins/python/`.
3. Restart Noesis. The plugin will participate when supported `.mesh.*`, `.tex.*`, or `.motlist.*` files are opened.

In the MESH selection window, double-click related MESH files from the same directory and use **Load** to import their models, skeletons, materials, and textures together. For MOTLIST animation export, select the top `[ALL]` collection to export all animations at once.

## Install the Maya tool

1. In Maya, open **Windows → General Editors → Script Editor**.
2. In the Script Editor, choose **File → Open Script** and select `REEM_Noesis_Maya.py`.
3. Choose **File → Save Script to Shelf**.
4. Open REEM and use **Browse** to select the Noesis executable.

## Maya animation workflow

1. Select a `.mesh.*` or `.motlist.*` file in REEM.
2. For MOTLIST files, double-click `[ALL]` in the Noesis selection window and click **Load**.
3. After Maya imports the result, REEM fills **Animation List** from the Noesis log.
4. Use **Export Selected Animations** or **Export All Animations** to export clips.

Some animations that Noesis cannot fully parse may contain only the first frame while the log still reports the original frame count. REEM removes explicit Warning entries and normalizes zero-frame and `blend_pose` entries to one frame. For remaining cases, use **Manually Paste Noesis List** and change the affected `frames` value to 1. Validate these animations separately before importing them into Unreal Engine.

## Windows UTF-8 compatibility

`REEM_Noesis_Maya.py` launches Noesis in a hidden CP936 console for compatibility with the embedded Python plugin loader in Noesis 4.474. Command-line export should therefore avoid `Detected file type: Unknown` even when Windows' “Beta: Use Unicode UTF-8 for worldwide language support” setting is enabled.

This only affects the Noesis child process created by REEM. It does not change the Windows system locale, and the interactive selectors for related MESH files and MOTLIST `[ALL]` animations remain available.

## Sources and notice

- Noesis plugin source: [alphazolam/fmt_RE_MESH-Noesis-Plugin](https://github.com/alphazolam/fmt_RE_MESH-Noesis-Plugin)
- Original Maya repository: [AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool](https://github.com/AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool)
- Additional Maya workflow notes: [Zhihu article](https://zhuanlan.zhihu.com/p/685480151)

See [NOTICE.md](./NOTICE.md) for source attribution, merged history, and rights information.
