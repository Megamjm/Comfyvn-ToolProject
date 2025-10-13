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
