# External Import Tool Installers

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

## Custom extractors
- You can register any command line tool that accepts the pattern:
  ```
  <tool> <archive> -o <output_dir>
  ```
- Examples: game-specific unpackers, translation community tools, archive converters.
- Use `/vn/tools/register` to declare new tools and `/vn/tools` to audit what is installed.
- Definitions are stored locally in `config/import_tools.json`; edit with care if you prefer manual configuration control.

## GUI follow-up tasks
- The Tool Installer extension surfaces this doc via the Modular Loader.
- GUI team should provide a panel that:
  - Lists registered tools with their warnings.
  - Offers buttons to open the upstream project page.
  - Supports manual path selection and validation.
  - Exposes a per-tool “run test extraction” action for troubleshooting.

Stay safe: always review licence terms and local laws before unpacking VN content.
