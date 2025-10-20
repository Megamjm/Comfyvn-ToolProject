# Importer Engine Matrix

A quick reference for the Importer chat while adapters are implemented. The
matrix lists signatures we rely on, typical archive formats, recommended
user-supplied extractor hooks, and notes on post-processing.

| Engine              | Detect by (examples)                                           | Primary archives / scripts         | Optional hooks                                | Normalization notes |
|---------------------|----------------------------------------------------------------|------------------------------------|-----------------------------------------------|---------------------|
| Ren'Py              | `game/`, `*.rpy/.rpyc`, `*.rpa`                                 | `.rpa`, loose `game/` assets       | `rpatool`, `unrpa`                             | Preserve Ren'Py text tags, map voices via filenames, respect interpolation placeholders. |
| KiriKiri / KAG      | `data.xp3`, any `.xp3`, `*.ks`, `Config.tjs`                   | `.xp3`, `.ks`, `.tlg` images        | `arc_unpacker`, `xp3tools`, `tlg2png`         | Convert `.tlg` to PNG when tool present; maintain `[r]`, `[cm]`, ruby tags. |
| NScripter family    | `nscript.dat`, `0.txt`, `.nsa/.ns2/.sar`                       | `.nsa`, `.ns2`, `.sar`, plain text  | `nsadec`, `kikiriki`                           | Retain wait codes and branching markers; support Shift-JIS decoding. |
| Yu-RIS              | `*.ypf`, `yst*.ybn`                                            | `.ypf`, `.ybn`                      | Community YST converters (user provided)      | Keep voice ↔ line mapping; detect multi-voice scenes. |
| CatSystem2          | `.int`, `.dat`, `.cst`, `.fes`, `.anm`, `.hg2/.hg3`            | `.int`, `.dat`, `.cst`, `.hg?`      | GARbro CLI, `hg2bmp`                          | Convert proprietary images; treat `.cst` as scene + timeline definitions. |
| BGI / Ethornell     | `data*.arc`, `_bp/*.org`, `bgi.exe`                            | `.arc`, `.org`, `.ke`, `.utf`       | GARbro CLI, BGI-specific extractors           | Preserve control codes; map voice assets located in separate trees. |
| RealLive / Siglus   | `RealLive.exe`, `Scene.pck`, `.ss`, `.org`, `Gameexe.dat`       | `.pck`, `.ss`, `.org/.utf`          | RLDev, Siglus scripts (user-provided)         | Maintain scene graph info and event flow states. |
| Unity VN            | `*_Data/`, `globalgamemanagers`, `*.assets`, AssetBundles      | AssetBundles, `.assets`             | UnityPy, AssetStudio CLI                      | Require user-exported textures/audio when possible; keep GUID mapping. |
| TyranoScript        | `data/scenario/*.ks`, `data/bgimage`, `data/fgimage`           | Plain folders                       | N/A                                           | Direct copy with Tyrano tags preserved; normalize to comfyvn-pack schema. |
| LiveMaker           | Self-extracting EXE / LiveMaker archive signatures             | Proprietary archive                 | pylivemaker CLI                               | Convert scripts into node graphs; export PNG/audio as available. |

Key principles:
- **Detect, don’t guess**: rely on unambiguous signatures before selecting an adapter.
- **Hooks are optional**: we never run extractors unless the user registers a path
  via `/vn/tools/register`.
- **Normalize with care**: keep traceability by storing raw dumps under
  `comfyvn_pack/raw/` alongside transformed assets.

See `docs/tool_installers.md` for installation guidance and legal reminders.
