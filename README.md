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

Build logs saved to /logs/build.log.

Added “dry-run” mode for preview exports.

⚙️ Cross-System Improvements
Category	Update
Async Safety	Replaced blocking I/O with asyncio.create_task().
Logging	Standardized under /logs/system.log using rotating handlers.
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
- GUI → Settings → *Compute / Server Endpoints* now manages both local and remote compute providers: discover loopback servers, toggle activation, edit base URLs, and persist entries to the shared provider registry (and, when available, the running backend).
- The Settings panel also exposes a local backend port selector with a “Find Open Port” helper so you can avoid clashes with other services; the value is persisted for the next launch and mirrored to the current process environment.
- The launcher performs a basic hardware probe before auto-starting the embedded backend. When no suitable compute path is found it skips the local server, logs the reason, and guides you to connect to a remote node instead of crashing outright.

The GUI’s “Start Server” helper still delegates to `python comfyvn/app.py`, logging output to `logs/server_detached.log`, so manual invocations remain in sync with UI behaviour.

## Logging & Debugging

- Server logs aggregate at `logs/server.log`. Override defaults with `COMFYVN_LOG_FILE`/`COMFYVN_LOG_LEVEL` before launching `uvicorn` or the CLI.
- GUI messages write to `logs/gui.log`; launcher activity goes to `logs/launcher.log`.
- The Studio status bar now shows a dedicated “Scripts” indicator. Installers and scripted utilities update the indicator so failed runs surface as a red icon with the last error message while keeping the application responsive.
- CLI commands (e.g. `python -m comfyvn bundle ...`) create timestamped run directories under `logs/run-*/run.log` via `comfyvn.logging_setup`.
- When tracking regressions, run `pytest tests/test_server_entrypoint.py` to confirm `/health`, `/healthz`, and `/status` remain reachable.
- The quick HTTP/WS diagnostics in `smoke_checks.py` exercise `/limits/status`, `/scheduler/health`, and the collab WebSocket. Run it while the backend is online to capture network traces.

## Health & Smoke Checks

- `curl http://127.0.0.1:8001/health` validates the FastAPI wiring from `comfyvn.server.app`.
- `curl http://127.0.0.1:8001/healthz` remains available for legacy tooling expecting the older probe.
- `python smoke_checks.py` performs REST + WebSocket checks against a locally running server and prints any failures alongside connection debug information.
