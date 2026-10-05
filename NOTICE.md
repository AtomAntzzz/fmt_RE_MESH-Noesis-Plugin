# Notice

This repository combines two Git histories:

1. `fmt_RE_MESH.py` and its upstream history originate from alphaZomega's `fmt_RE_MESH-Noesis-Plugin`: <https://github.com/alphazolam/fmt_RE_MESH-Noesis-Plugin>
2. `REEM_Noesis_Maya.py` and its history originate from AtomAntzzz's `RE-Engine-Mesh-Animtion-Noesis-Tool`: <https://github.com/AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool>

The histories are preserved through a Git merge rather than a squash or history rewrite. The original Maya repository was archived after migration. The current tree intentionally omits the former 3ds Max MaxScript files.

No repository-level license file was present in either source repository at migration time. This notice does not relicense either upstream source, does not change its existing file history, and does not grant rights beyond those already provided by the respective authors.

The `re_engine_*.py` modules contain code moved from the upstream plugin alongside the scoped PRAGMATA additions. Moving that code does not change its attribution or rights. The PRAGMATA additions were independently authored from observed binary behavior and regression evidence. The GPLv3 RE-Mesh-Editor project was used only as an external comparison tool; its source and binaries are not copied into this distribution.

## PRAGMATA GDeflate bridge

The small C ABI bridge in `tools/pragmata_gdeflate/pragmata_gdeflate.cpp` links the CPU GDeflate implementation from Microsoft's DirectStorage repository. The reviewed binaries are tied to:

- Microsoft DirectStorage commit `c53f1499d5f67a61b69a1a348d22dcd2b4cb4ede`.
- The DirectStorage `GDeflate/3rdparty/libdeflate` submodule commit `8ba9502fb30d2bf728592d121f0d402e40c8cb05`.

The bridge distribution includes the applicable upstream terms and notices at these exact paths:

- `third_party/licenses/DirectStorage-GDeflate-LICENSE.txt` — GDeflate Apache License 2.0 text.
- `third_party/licenses/DirectStorage-NOTICES.txt` — DirectStorage third-party notices.
- `third_party/licenses/libdeflate-COPYING.txt` — libdeflate MIT license text.

The reviewed x86/x64 bridge DLLs have SHA-256 values `CAB69417470C22F1B3CF9861478D844A949F4A1C32BC71369F35286BD59A70F0` and `1A0A0E834658571F6A7C23E7C73DB30D62507C18331C76E8DCB374AB04AAAA7D`. These third-party license files apply to their respective components. Their inclusion does not relicense the upstream Noesis plugin, the Maya tool, or independently authored PRAGMATA adapter code.
