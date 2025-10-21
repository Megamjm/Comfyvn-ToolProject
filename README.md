🚀 Overview

This update transforms ComfyVN from a static scene exporter into a multi-layer, interactive VN engine that merges SillyTavern-style roleplay logs, ComfyUI rendering, and Ren’Py exports under one adaptive framework.

Highlights:

🧩 New Roleplay Import System

🌐 Live WebSocket JobManager

🪟 Expanded GUI with Tray Notifications

🌍 Enhanced World + Audio + Persona sync

⚙️ Unified Logging, Config, and Async Safety

🧱 Fully modular directory structure

✨ New Additions
🤝 Roleplay Import & Collaboration System

(New Subsystem 11)
Enables uploading .txt or .json multi-user chat logs to convert into VN scenes.

New Modules: parser.py, formatter.py, analyzer.py, roleplay_api.py

Endpoints:

POST /roleplay/import → parse & convert logs

GET /roleplay/preview/{scene_id} → preview generated scene JSON

Data Folders:

/data/roleplay/raw

/data/roleplay/converted

/data/roleplay/preview

🧠 Automatically detects participants and outputs VN-ready scene structures.

🌐 WebSocket Job System (Server + GUI)

Introduced full real-time job tracking via /jobs/ws.

New module: server/modules/job_manager.py

GUI now supports async job updates, tray alerts, and task overlays.

/jobs/poll, /jobs/logs, /jobs/reset, /jobs/kill endpoints added.

Graceful WebSocket shutdowns and heartbeats for reliability.

🪟 GUI Framework Expansion

New Version: v1.2.0-dev

Added Task Manager Dock with live updates and right-click actions.

Added TraySystem notifications and job summaries.

Added Settings UI for API/Render configuration.

Implemented Progress Overlay and unified Status Bar.

Async refactor: switched to httpx.AsyncClient.

Scaffolded “Import Roleplay” dialog (Phase 3.2 GUI target).

🌍 World & Ambience Enhancements

Added Day/Night + Weather Profiles.

Added TTL-based cache refresh for active world data.

Linked to AudioManager for ambience syncing.

Extended /data/worlds/ format with environmental metadata.

🫂 Persona & Group Layout

Emotion blending and transitional tweening added.

Persona overlay for “User Character” implemented.

Group auto-layout based on Roleplay participants.

Persona state serialization to /data/persona/state.json.

🔊 Audio & FX Foundation

Centralized audio_settings.json.

Adaptive layering plan (mood-based playback).

Thread-safe audio calls and volume normalization.

🧬 LoRA Management

Async LoRA registry and sha256 verification.

Local index /data/lora/lora_index.json.

Prepared search hooks for GUI and persona consistency.

🧪 Playground Expansion

Scene mutation API stubs created.

Undo/Redo stack base implemented (collections.deque).

Safe auto-backup of live edits to /data/playground/history/.

📦 Packaging & Build

File sanitization for cross-platform exports.

Build logs saved to the user log directory (see **Runtime Storage**) as `build.log`.

Added “dry-run” mode for preview exports.

Packaging roadmap tracked in `docs/packaging_plan.md`.

🖼️ Sprite & Pose Toolkit

- Modules → `Sprites` opens the sprite panel for managing persona expressions, previews, and pose assignments.
- Poses load from user runtime directories (`data/poses`); active pose JSON is embedded in persona metadata and surfaced to ComfyUI workflows.
- Ship with starter ComfyUI workflow templates: `sprite_composite_basic`, `pose_blend_basic`, and `sprite_pose_composite`.

⚙️ Cross-System Improvements
Category	Update
Async Safety	Replaced blocking I/O with asyncio.create_task().
Logging	Standardized under the user log directory (`system.log`) using rotating handlers.
Configuration	Added /config/paths.json for all base URLs and directories.
Validation	Schema templates /docs/schema/scene.json, /docs/schema/world.json.
Thread Safety	Added cleanup hooks and WebSocket lock protection.
Error Handling	Replaced bare except: with structured exceptions and logs.
Testing	Added pytest stubs for API endpoints.

## Running ComfyVN Locally

`python run_comfyvn.py [options]` bootstraps the virtualenv, installs requirements, and then launches either the GUI or the FastAPI server depending on the flags you pass. Handy commands:

- `python run_comfyvn.py` – launch the GUI and auto-start a local backend on the default port.
- `python run_comfyvn.py --server-only --server-host 0.0.0.0 --server-port 9001` – start only the FastAPI server (headless) listening on an alternate interface/port.
- `python run_comfyvn.py --server-url http://remote-host:8001 --no-server-autostart` – open the GUI but connect to an already-running remote server without spawning a local instance.
- `python run_comfyvn.py --server-only --server-reload` – headless development loop with uvicorn’s auto-reload.
- `python run_comfyvn.py --uvicorn-app comfyvn.server.app:create_app --uvicorn-factory` – run the server via the application factory if you need a fresh app per worker.

Environment variables honour the same knobs:

- `COMFYVN_SERVER_BASE` – default base URL for the GUI and CLI helpers (set automatically from `--server-url` or the derived host/port).
- `COMFYVN_SERVER_AUTOSTART=0` – disable GUI auto-start of a local server.
- `COMFYVN_SERVER_HOST`, `COMFYVN_SERVER_PORT`, `COMFYVN_SERVER_APP`, `COMFYVN_SERVER_LOG_LEVEL` – default values consumed by the launcher when flags are omitted.
- The launcher resolves the default port in this order: `--server-port` flag → `COMFYVN_SERVER_PORT` env var → the user config file (`settings/config.json`, see **Runtime Storage**) → fallback `8001`. Once resolved it writes `COMFYVN_SERVER_PORT` for child processes so the GUI, smoke checks, and detached helpers stay in sync.
- GUI → Settings → *Compute / Server Endpoints* now manages both local and remote compute providers: discover loopback servers, toggle activation, edit base URLs, and persist entries to the shared provider registry (and, when available, the running backend).
- The Settings panel also exposes a local backend port selector with a “Find Open Port” helper so you can avoid clashes with other services; the selection is saved to the user config directory (`settings/config.json`), mirrored to the current environment, and honoured by the next launcher run.
- Backend `/settings/{get,set,save}` endpoints now use the shared settings manager with deep-merge semantics, so GUI updates and CLI edits land in the same file without clobbering unrelated sections.
- Asset imports enqueue thumbnail generation on a background worker so large images stop blocking the registration path; provenance metadata is embedded into PNGs and, when the optional `mutagen` package is installed, MP3/OGG/FLAC/WAV assets as well.
- Install `mutagen` with `pip install mutagen` if you need audio provenance tags; without it the system still registers assets but skips embedding the metadata marker.
- The launcher performs a basic hardware probe before auto-starting the embedded backend. When no suitable compute path is found it skips the local server, logs the reason, and guides you to connect to a remote node instead of crashing outright.

### Runtime Storage

ComfyVN Studio stores mutable state outside the repository using the platform-aware directories exposed by `comfyvn.config.runtime_paths` (`platformdirs` under the hood). By default:

- **Logs** live in the user log directory (for example `~/.local/share/ComfyVN Studio/logs` on Linux or `%LOCALAPPDATA%\ComfyVN Studio\Logs` on Windows). Files such as `system.log`, `gui.log`, `server_detached.log`, and timestamped `run-*` folders are written here.
- **Configuration** is persisted beneath the user config directory (`settings/config.json`, `settings/gpu_policy.json`, etc.). Override with `COMFYVN_CONFIG_DIR` or `COMFYVN_RUNTIME_ROOT` if you need a portable layout.
- **Workspaces & user data** are stored under the user data directory (e.g., `workspaces/`, saved layouts, and importer artefacts). Override with `COMFYVN_DATA_DIR`.
- **Caches** (thumbnails, audio/music caches, render scratch space) reside in the user cache directory; set `COMFYVN_CACHE_DIR` to relocate them.

Environment overrides include `COMFYVN_RUNTIME_ROOT` (sets all four roots), or the specific `COMFYVN_LOG_DIR`, `COMFYVN_CONFIG_DIR`, `COMFYVN_DATA_DIR`, and `COMFYVN_CACHE_DIR`. The package bootstraps legacy-friendly symlinks (`logs/`, `cache/`, `data/workspaces`, `data/settings`) when possible so existing scripts continue to function.

The GUI’s “Start Server” helper still delegates to `python comfyvn/app.py`, logging output to `server_detached.log` inside the user log directory, so manual invocations remain in sync with UI behaviour.

### Ren'Py Reference Project

The `renpy_project/` directory is a pristine sample used for rendering validations and export smoke tests. Treat it as read-only—copy assets out if you need to modify them, and keep build artefacts, saves, and caches out of the tree so the reference stays clean.

### Developer System Dependencies

Running the full pytest suite (especially GUI workflows powered by PySide6) requires a few EGL/X11 libraries to be present on the host OS. Debian/Ubuntu developers can install the curated list in `requirements-dev-system.txt` with:

```bash
sudo apt-get update
sudo xargs -a requirements-dev-system.txt apt-get install --yes
```

After system packages are in place, install the Python development extras (including `platformdirs`) with:

```bash
pip install -r requirements-dev.txt
```

Currently the file covers `libegl1`, `libxkbcommon0`, and `libdbus-1-3`; add new entries there whenever additional system packages are needed for tests.

## Logging & Debugging

- Server logs aggregate at `system.log` inside the user log directory. Override defaults with `COMFYVN_LOG_FILE`/`COMFYVN_LOG_LEVEL` before launching `uvicorn` or the CLI.
- GUI messages write to `gui.log`; launcher activity goes to `launcher.log` under the same directory.
- The Studio status bar now shows a dedicated “Scripts” indicator. Installers and scripted utilities update the indicator so failed runs surface as a red icon with the last error message while keeping the application responsive.
- CLI commands (e.g. `python -m comfyvn bundle ...`) create timestamped run directories under `run-*/run.log` in the user log directory via `comfyvn.logging_setup`.
- When tracking regressions, run `pytest tests/test_server_entrypoint.py` to confirm `/health`, `/healthz`, and `/status` remain reachable.
- The quick HTTP/WS diagnostics in `smoke_checks.py` exercise `/limits/status`, `/scheduler/health`, and the collab WebSocket. Run it while the backend is online to capture network traces.

## Health & Smoke Checks

- `curl http://127.0.0.1:8001/health` validates the FastAPI wiring from `comfyvn.server.app`.
- `curl http://127.0.0.1:8001/healthz` remains available for legacy tooling expecting the older probe.
- `python smoke_checks.py` performs REST + WebSocket checks against a locally running server and prints any failures alongside connection debug information.

## Extension Development

See `docs/extension_manifest_guide.md` for the manifest schema, semantic-version negotiation rules, and examples of registering menu callbacks with the new loader.

## World Lore

- Sample world data lives in `defaults/worlds/auroragate.json` (AuroraGate Transit Station). Pair it with `docs/world_prompt_notes.md` and `comfyvn/core/world_prompt.py` to translate lore into ComfyUI prompt strings.
