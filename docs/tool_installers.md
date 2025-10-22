# External Import Tool Installers

> **Note:** The legacy REST/GUI installer flow described below has been
> superseded by the CLI utilities documented in `docs/EXTRACTORS.md`.
> Keep this file for historical context until the GUI wiring is refreshed.

_ComfyVN does not ship third-party extraction tools.  Use this checklist to install
optional helpers when you own the content you are importing._

## arc_unpacker (Visual Novel archive extractor)
- Project: <https://github.com/vn-tools/arc_unpacker>
- Features: Extracts proprietary VN archive formats (`.arc`, `.xp3`, `.dat`, more).
- Installation
  1. Download a release for your platform from the project page.
  2. Place the binary somewhere in your PATH (or note the absolute file path).
  3. Register the tool with ComfyVN using `POST /vn/tools/register` (or the future GUI panel).
     ```json
     {
       "name": "arc_unpacker",
       "path": "/path/to/arc_unpacker",
       "extensions": [".arc", ".xp3", ".dat"],
       "warning": "Use only on content you are legally allowed to extract in your jurisdiction."
     }
     ```
  4. When importing, supply `{"tool": "arc_unpacker"}` or let the system auto-detect supported extensions.
- Legal reminder: Some regions restrict reverse engineering of game assets.  Only extract archives you
  are authorised to access (e.g., personal backups or permitted modding kits).

### API quick start

- `POST /vn/tools/install` with payload `{"name":"arc_unpacker","accept_terms":true}` downloads the
  latest release into `tools/extractors/arc_unpacker/` and registers it automatically.
- All installers require `accept_terms=true` to acknowledge the licensing warning above. The response will
  include the tool path and any follow-up notes.

## Custom extractors
- You can register any command line tool that accepts the pattern:
  ```
  <tool> <archive> -o <output_dir>
  ```
- Examples: game-specific unpackers, translation community tools, archive converters.
- Use `/vn/tools/register` to declare new tools and `/vn/tools` to audit what is installed.
- Definitions are stored locally in `config/import_tools.json`; edit with care if you prefer manual configuration control.
- The installer endpoint (`/vn/tools/install`) supports the predefined entries listed in
  `comfyvn/server/core/extractor_installer.py::KNOWN_EXTRACTORS`.

## Curated extractor catalog (top 20)

The installer catalog exposes the following community tools. Invoke `GET /vn/tools/catalog` to retrieve
the live list (IDs shown below). All downloads require `accept_terms=true` when calling `/vn/tools/install`.

| ID | Purpose | Notes |
|----|---------|-------|
| arc_unpacker | Multi-engine archives (.arc/.xp3/.dat) | MIT-licensed Windows binary; primary recommendation. |
| rpatool | Ren'Py .rpa | Python script; run with local Python interpreter. |
| unrpa | Ren'Py .rpa | Alternative Python implementation. |
| lightvntools_github / lightvntools_gitlab | General VN archives | GPL utilities covering multiple formats (build from source). |
| garbro_cli | GUI/CLI archive explorer | Extracts many commercial engines (.arc/.xp3/.dat). |
| krkrextract, xp3tools | Kirikiri/KAG archives | Range of XP3/TLG unpackers. |
| nsadec | NScripter archives | Decompresses .nsa/.ns2/.sar packages. |
| siglusextract | SiglusEngine | Handles Scene.pck, .ss scripts. |
| ypf_unpacker | Yu-RIS | Extracts .ypf archives. |
| catsystem2_tools, hg2_converter | CatSystem2 | Decrypts .int/.dat and converts .hg2/.hg3 images. |
| bgi_tools | Buriko General Interpreter | Works with data*.arc / _bp/*.org. |
| unity_asset_ripper, assetstudio_cli | Unity AssetBundles | GUI/CLI for Unity-based VN ports. |
| livemaker_unpacker | LiveMaker archives | Extracts .paz/.lmd. |
| tyrano_parser | TyranoScript data | Parses scenario files. |
| krgem_unpacker | Kirikiri Z / EM variants | Supports modern XP3 overlays. |
| reallive_tools | RealLive/Siglus scripts | RLDev toolchain fork. |

## GUI follow-up tasks
- The Tool Installer extension surfaces this doc via the Modular Loader.
- GUI team should provide a panel that:
  - Lists registered tools with their warnings.
  - Offers buttons to open the upstream project page.
  - Supports manual path selection and validation.
  - Exposes a per-tool “run test extraction” action for troubleshooting.

Stay safe: always review licence terms and local laws before unpacking VN content.
