🧠 SUMMARY

ComfyVN has evolved from a static Visual Novel scene exporter into a multi-layer interactive VN generation framework.
This update introduces the Roleplay Import System, WebSocket job management, adaptive GUI framework, and multi-world integration, preparing for the next milestone — Phase 3.2 Interactive Pipeline Sync.

🪟 GUI SYSTEM (🎨 2. GUI Code Production Chat)

Version: v1.1.7 → v1.2.0-dev
Files Affected:

/gui/main_window.py

/gui/components/task_manager_dock.py

/gui/components/progress_overlay.py

/gui/components/tray_system.py (new)

/gui/dialogs/settings_ui.py (new)

Added:

🧩 Task Manager Dock with live polling and right-click actions (Kill, Reset, Move).

🔄 Job History Rotation (10 log file limit, auto-rotation).

💬 Live Console Viewer (TaskConsoleWindow) with color-coded job states.

🔔 Tray Notification System scaffold using QSystemTrayIcon.

⚙️ Settings UI for path configuration and render mode selection.

🌐 WebSocket Client Stub (ready for /jobs/ws integration).

Improved:

Unified top menu layout (File / View / Help).

Thread termination guards for background listeners.

Status bar integration for job feedback.

Async-safe requests using httpx.

Planned:

Full WebSocket message push (replacing poll).

Import Roleplay dialog integration.

Live mode switch indicator.

⚙️ SERVER CORE (3. Server Core Production Chat)

Version: v3.0.3 → v3.2.0-pre
Files Affected:

/server/app.py

/server/modules/job_manager.py (new)

/server/modules/mode_manager.py

/server/modules/scene_preprocessor.py

/server/modules/ws_utils.py (new)

Added:

🧩 JobManager (create/update/broadcast jobs).

🌐 WebSocket Endpoint /jobs/ws for live GUI push updates.

📜 Job Polling API (/jobs/poll, /jobs/reset, /jobs/logs).

🧱 Schema Validation Plan for scene JSON.

🧭 Subsystem Health Check endpoint (/status/subsystems).

Improved:

Async-safe FastAPI routes.

Locked shared dicts with asyncio.Lock.

Logging standardized to /logs/server.log.

Modularized startup/shutdown events.

Planned:

Scene validator integration (Pydantic).

ComfyUI workflow trigger for cinematic rendering.

🌍 WORLD LORE SYSTEM (4. World Lore Production Chat)

Version: v1.1.1 → v1.3.0
Files Affected: /server/modules/world_loader.py

Added:

🌤 Weather and Day/Night Profiles.

🧠 World Cache System with TTL auto-refresh.

🔄 Active World Selector for GUI dropdown.

📦 World Prop Injection (stage layout data for render).

Improved:

JSON loading with fallback for incomplete fields.

Thread-safe cache invalidation.

Integrated with ModeManager for ambience switching.

🔊 AUDIO & FX (5. Audio & Effects Production Chat)

Version: v0.2 → v0.3.1
Files Affected: /server/modules/audio_manager.py

Added:

🔉 Centralized toggle state JSON config.

🧠 Adaptive layering plan (emotion-based).

⚙️ Volume normalization stubs for ambient/music/fx.

Improved:

Threaded playback for non-blocking operations.

Exception-safe audio calls.

Future integration hooks for Roleplay Analyzer tone.

🫂 PERSONA & GROUP SYSTEM (6. Persona & Group Chat)

Version: v0.3 → v0.5-dev
Files Affected: /server/modules/persona_manager.py

Added:

🧍‍♂️ Layout enum for left/center/right positioning.

🎭 Emotion blend stub (pre-animation tweening).

🪞 User Persona overlay logic.

📁 Persona state serializer /data/persona/state.json.

Improved:

Deterministic layout rotation.

Integration hook for Roleplay participant auto-layout.

Sync to Playground for live updates.

🧪 PLAYGROUND SYSTEM (7. Playground Chat)

Version: v0.2 → v0.4-dev
Files Affected: /server/modules/playground_manager.py

Added:

🧠 Scene mutation API (placeholder).

↩️ Undo/Redo stack base (deque).

🔍 Scene backup system (/data/playground/history/).

Improved:

Async-safe writes.

Mutations return proper job status.

Linked to upcoming Roleplay Import system.

🧬 LORA MANAGER (8. LoRA Chat)

Version: v0.3 → v0.4-dev
Files Affected: /server/modules/lora_manager.py

Added:

🔍 Local LoRA registry with metadata cache.

⚙️ Async search and registration stubs.

🧱 Local index lora_index.json with sha256 validation.

Improved:

Model versioning and integrity checks.

Planned GUI integration for LoRA lookups.

📦 PACKAGING & BUILD (9. Packaging Chat)

Version: v0.1 → v0.3-dev
Files Affected: /build/export_renpy.py, /build/build_assets.py

Added:

🧩 Smart Asset Bundling system (planned).

🪶 Lightweight export preview mode.

📜 Export logs (/logs/build.log).

Improved:

Sanitized scene filenames for cross-platform builds.

Integrated with JobManager.

🧾 CODE UPDATES (10. Code Updates Chat)

Version: Meta
Files: None (central synchronization & QA).

Added:

Unified linter/formatter (black, flake8) setup.

File structure restructure:
