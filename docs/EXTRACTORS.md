# Visual Novel Extractors

This stack fetches third-party extraction utilities **on demand** (no binaries are
checked into the repo) after the user acknowledges the legal/liability gate.
It ships three companion scripts:

- `tools/install_third_party.py` — downloads vetted builds into `third_party/`
  with shims and a manifest that records hashes, licenses, and install details.
- `tools/vn_extract.py` — detects the engine from a game folder or archive,
  runs the matching extractor, and emits `extract_log.json` plus a
  `license_snapshot.json` under `imports/<game>/raw_assets/`.
- `tools/doctor_extractors.py` — lists installed tools and probes their shims
  (help output, wine/dotnet availability) so contributors can verify the setup.

All commands are cross-platform; Windows-only binaries run via Wine when
available. Feature flag `features.enable_extractors` remains **OFF** by default—
flip it when wiring the stack into GUI menus or automation flows.

---

## Legal / ToS Reminder

- Use these tools **only** with games you legally own and for which the licence
  permits extraction or modding. The acknowledgement prompt must be accepted
  before the installer will download any binary.
- The manifest retains the download URL, SHA-256 checksum, and licence metadata
  for every tool. The wrapper copies a compact `license_snapshot.json` into
  each extraction job alongside provenance fields (`tool`, `version`, `hash`).
- No third-party binaries are committed to the repository. Everything lives
  under `third_party/` on the user machine and can be wiped safely.

---

## Installing Extractors

```bash
# Inspect the catalog with hashes, OS support, and licence links.
python tools/install_third_party.py --list

# Download a specific tool (ack prompt will appear unless --yes is provided).
python tools/install_third_party.py --tool rpatool

# Install the full catalog and skip acknowledgements (suitable for CI on
# isolated machines where the licence gate was already recorded).
python tools/install_third_party.py --all --yes
```

Key behaviours:

- Downloads are pinned to specific versions with known checksums. Re-running the
  installer is idempotent; when the manifest entry already matches the expected
  version/hash the script simply refreshes the shim.
- Shims live in `third_party/shims/<tool>` (plus `.cmd` wrappers on Windows).
  They read the manifest at runtime, set PYTHONPATH for Python-based tools, and
  call Wine/Dotnet when required.
- Manifest path: `third_party/manifest.json` — safe to inspect or commit to
  CI artifacts for auditing.

---

## Wrapper Usage (`tools/vn_extract.py`)

```bash
# Inspect plan but skip execution.
python tools/vn_extract.py /path/to/game --plan-only

# Dry-run extraction (writes logs + licence snapshot, skips tool execution).
python tools/vn_extract.py /path/to/game --dry-run

# Full run: auto-detect engine, pick installed tool, export into imports/.
python tools/vn_extract.py /path/to/game --output-root imports

# Override detection or tool selection when needed.
python tools/vn_extract.py /path/to/archive.xp3 --engine kirikiri --tool arc_unpacker
```

Outputs:

- `imports/<game>/raw_assets/` — per-archive subfolders with extracted content.
- `imports/<game>/raw_assets/license_snapshot.json` — licence metadata and
  download provenance for the extractor used.
- `imports/<game>/extract_log.json` — detection evidence, tool information,
  per-archive command/status summaries, and file counts (suitable for QA bots).

Debug/API hooks:

- `--plan-only` emits a JSON plan (engine, archives, tool, output paths) without
  touching disk. Handy for automation scripts or Studio preview panes.
- `--dry-run` still writes the JSON artefacts while skipping the actual extractor.
- `--clean` wipes previous `raw_assets/` exports so repeated runs stay deterministic.

---

## Doctor & Troubleshooting

```bash
# JSON report
python tools/doctor_extractors.py

# Human-readable table
python tools/doctor_extractors.py --table
```

The doctor script:

- Verifies the manifest can be read and lists every installed tool with version,
  licence, shim path, and runtime requirements (Wine/Dotnet).
- Runs light `--help` probes for Python-based tools. Windows-specific binaries
  emit warnings when Wine is not present rather than failing the report.
- Returns non-zero when a shim is missing or a probe hard-fails, making it
  suitable for preflight CI steps.

For deeper debugging:

- Inspect `third_party/manifest.json` to confirm hashes and install paths.
- Shims are small Python scripts—open `third_party/shims/<tool>` to see the exact
  command that will run.
- Use `--plan-only` / `--dry-run` on `vn_extract.py` before running heavy
  extractors to avoid partial exports.

---

## Tool Catalog Snapshot

| Key            | Licence           | OS Support                          | Notes                                                                 |
| -------------- | ----------------- | ----------------------------------- | --------------------------------------------------------------------- |
| `rpatool`      | MIT               | Windows / Linux / macOS             | Python Ren'Py extractor (RPA 2/3/4). Preferred for `.rpa` archives.   |
| `unrpa`        | MIT               | Windows / Linux / macOS             | Python module alternative for Ren'Py; runs via `python -m`.           |
| `arc_unpacker` | MIT               | Windows (`wine` on Linux/macOS)     | Broad VN archive support (`.arc`, `.xp3`, `.dat`, …).                 |
| `garbro`       | MIT               | Windows (`wine` on Linux/macOS)     | GUI/CLI tool for many Japanese engines; zip build pinned to 1.4.32.   |
| `krkrextract`  | GPL-3.0-or-later  | Windows (`wine` on Linux)           | KiriKiri XP3 extractor (Lite build).                                  |
| `assetstudio`  | MIT               | Windows (`wine` on Linux)           | Unity asset viewer/extractor; CLI requires .NET runtime.              |
| `wolfdec`      | MIT               | Windows (`wine` on Linux)           | Wolf RPG archive decoder.                                            |

> **Tip:** run `python tools/install_third_party.py --info garbro` to view the
> full metadata payload (hash, download URL, warning copy) for any tool.

---

## Automation Hooks

- All scripts are pure CLI utilities; integrate them into pipelines by calling
  the commands above and parsing the JSON artefacts.
- `vn_extract.py` and the doctor script exit non-zero on failure, allowing CI to
  gate merges or releases.
- The manifest format is stable (`format_version = 1`). Automation can monitor
  `third_party/manifest.json` for changes to surface audits or diff licences.

