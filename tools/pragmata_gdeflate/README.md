# PRAGMATA GDeflate bridge

This directory contains only a small C ABI bridge. It links against the CPU GDeflate implementation from the official Microsoft DirectStorage repository; no GPL implementation code is copied here.

The evidence build is pinned to:

- DirectStorage commit `c53f1499d5f67a61b69a1a348d22dcd2b4cb4ede`.
- `GDeflate/3rdparty/libdeflate` commit `8ba9502fb30d2bf728592d121f0d402e40c8cb05`.
- DirectStorage GDeflate license: Apache-2.0, packaged as `third_party/licenses/DirectStorage-GDeflate-LICENSE.txt`, SHA-256 `A8617C1F7CB74E043D7117E1D8C95A2A5F5EFE0688C023EBB297419BAB839B76`.
- DirectStorage notices: packaged as `third_party/licenses/DirectStorage-NOTICES.txt`, SHA-256 `E38AA7F8774D7F035600AEA556D708C83BDF551AAA8D3F086287CA76452A0D1A`.
- libdeflate license: MIT, packaged as `third_party/licenses/libdeflate-COPYING.txt`, SHA-256 `0AC45C1E14353F76F1027349D790B6CB24503FCD6877ECFE0967236A322F384B`.

The reviewed evidence binaries are `pragmata_gdeflate_x86.dll` (133120 bytes, SHA-256 `CAB69417470C22F1B3CF9861478D844A949F4A1C32BC71369F35286BD59A70F0`) and `pragmata_gdeflate_x64.dll` (169984 bytes, SHA-256 `1A0A0E834658571F6A7C23E7C73DB30D62507C18331C76E8DCB374AB04AAAA7D`). Their PE machine values are `0x14C` and `0x8664` respectively. Verify the downloaded files from the repository root in PowerShell, comparing the results with the SHA-256 values above:

```powershell
Get-FileHash pragmata_gdeflate_x86.dll, pragmata_gdeflate_x64.dll -Algorithm SHA256
Get-FileHash third_party/licenses/*.txt -Algorithm SHA256
```

Configure separate x86 and x64 build directories with `DIRECTSTORAGE_ROOT` set to that pinned checkout. The x86 DLL is for `Noesis.exe`; the x64 DLL is for `Noesis64.exe`. Generated PDBs and build trees stay outside Git. Both reviewed DLLs ship with the exact upstream license and notice files listed above.

The exported ABI is deliberately tiny: version query plus bounds supplied by the Python caller for one GDeflate stream. TEX parsing remains in the bounds-safe Python profile code.
