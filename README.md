ComfyVN Changelog — Version v0.3.2-pre
───────────────────────────────────────────────
Branch: dev/mainline
Previous Tag: v0.2-dev
Date: [Insert current date before commit]
Maintainer: ComfyVN Architect

───────────────────────────────────────────────
CHANGE SUMMARY
───────────────────────────────────────────────
ComfyVN v0.3.2-pre transforms the toolkit from a static Visual Novel renderer into a
multi-layer interactive framework supporting live job management, collaborative roleplay imports,
and system-wide async optimization.  

Key features include:
 • Roleplay Import & Collaboration System (Subsystem 11)
 • WebSocket-based JobManager + GUI Task Console integration
 • Adaptive GUI overlays, tray notifications, and settings system
 • Async-safe FastAPI server core and standardized logging
 • Updated directory hierarchy with subsystem subfolders
 • World, Persona, Audio, and LoRA systems synchronized for Phase 3.2

───────────────────────────────────────────────
DIFF SUMMARY
───────────────────────────────────────────────
[ADDED]
 • /server/modules/job_manager.py
 • /server/modules/ws_utils.py
 • /server/modules/roleplay/ (parser.py, formatter.py, analyzer.py, roleplay_api.py)
 • /gui/components/tray_system.py
 • /gui/dialogs/settings_ui.py
 • /config/paths.json (centralized path management)
 • /docs/schema/scene.json, /docs/schema/world.json
 • /data/roleplay/raw, /data/roleplay/converted, /data/roleplay/preview

[CHANGED]
 • /server/app.py — includes RoleplayRouter and WebSocket routes
 • /server/modules/mode_manager.py — render mode handling
 • /server/modules/scene_preprocessor.py — integrated Roleplay scene validation
 • /gui/main_window.py — async requests, status bar, WebSocket client
 • /gui/components/task_manager_dock.py — live polling, context menu
 • /gui/components/progress_overlay.py — real progress overlay
 • /build/export_renpy.py — filename sanitizer, improved asset bundling
 • Logging unified under /logs/system.log
 • Async refactors across GUI and server for non-blocking I/O

[REMOVED]
 • Deprecated polling loops in GUI (replaced by WebSocket listener)
 • Legacy blocking exports in build_assets.py
 • Redundant import paths in world_loader and persona_manager

───────────────────────────────────────────────
DETAILED CHANGELOG
───────────────────────────────────────────────

🪟 GUI SYSTEM (v1.1.7 → v1.2.0-dev)
 - Added Task Manager Dock with live job updates and color-coded status.
 - Implemented tray notifications via QSystemTrayIcon.
 - Added Settings UI dialog for API base and render mode control.
 - Migrated network calls to httpx.AsyncClient.
 - Introduced WebSocket client scaffold for /jobs/ws.
 - Prepared Import Roleplay dialog placeholder (Phase 3.2 GUI feature).

⚙️ SERVER CORE (v3.0.3 → v3.2.0-pre)
 - Added JobManager module with async-safe job handling.
 - Added /jobs/ws WebSocket route with broadcast support.
 - Added schema validation hooks for scene JSONs.
 - Introduced health check endpoint /status/subsystems.
 - Integrated RoleplayRouter for collaborative imports.
 - Implemented graceful shutdown with WebSocket cleanup.
 - Centralized logs under /logs/server.log.

🌍 WORLD LORE SYSTEM (v1.1.1 → v1.3.0)
 - Added weather/day-night profiles and prop metadata.
 - Added cache TTL system for world reloads.
 - Linked to ModeManager for ambient theme switching.
 - Added active world selector for GUI dropdowns.

🔊 AUDIO & FX (v0.2 → v0.3.1)
 - Created audio_settings.json configuration.
 - Prepared adaptive layering hooks for emotion-based playback.
 - Threaded playback calls for non-blocking GUI integration.

🫂 PERSONA & GROUP (v0.3 → v0.5-dev)
 - Introduced emotion blending and user persona overlay.
 - Added persona state serialization.
 - Coordinated with Roleplay Importer for participant auto-layout.

🧪 PLAYGROUND (v0.2 → v0.4-dev)
 - Added scene mutation API and undo/redo stack base.
 - Integrated mutation logging and safe autosave.
 - Planned integration with Roleplay scenes for live editing.

🧬 LORA MANAGER (v0.3 → v0.4-dev)
 - Added async model registry with metadata cache.
 - Added integrity validation and versioned index.
 - Prepared GUI search bridge.

📦 PACKAGING & BUILD (v0.1 → v0.3-dev)
 - Sanitized file paths and implemented export logging.
 - Added dry-run mode for preview builds.
 - Integrated JobManager logging into build process.

🤝 ROLEPLAY IMPORT & COLLABORATION (NEW)
 - Introduced parser/formatter/analyzer modules.
 - Added /roleplay/import and /roleplay/preview endpoints.
 - Supported automatic participant detection and scene conversion.
 - Future: emotion/tone tagging via LM Studio (Phase 3.3).

───────────────────────────────────────────────
CROSS-SYSTEM IMPROVEMENTS
───────────────────────────────────────────────
 - Standardized logging with rotating file handlers.
 - Centralized configuration via /config/paths.json.
 - All asset and LoRA files gain checksum validation.
 - Async/await patterns replace blocking calls.
 - Schema validation planned for Scene, Persona, and World.
 - Thread cleanup and event-loop guards in GUI.

───────────────────────────────────────────────
DIRECTORY TREE UPDATE
───────────────────────────────────────────────
comfyvn/
├── server/
│   ├── app.py
│   ├── modules/
│   │   ├── job_manager.py
│   │   ├── ws_utils.py
│   │   ├── roleplay/
│   │   ├── mode_manager.py
│   │   ├── scene_preprocessor.py
│   └── schemas/
│       ├── scene.json
│       └── world.json
├── gui/
│   ├── main_window.py
│   ├── components/
│   ├── dialogs/
│   └── resources/
├── data/
│   ├── roleplay/
│   ├── worlds/
│   ├── audio/
│   ├── persona/
│   └── lora/
├── build/
├── logs/
└── docs/

───────────────────────────────────────────────
NEXT ACTIONS
───────────────────────────────────────────────
 • Complete RoleplayRouter integration test.
 • Add WebSocket heartbeat and job locks.
 • Implement GUI “Import Roleplay” menu.
 • Finalize scene.json schema validation.
 • Begin adaptive audio integration (Phase 3.3 target).
 • Tag release after successful tests → v0.3.2-pre.

───────────────────────────────────────────────
END OF CHANGELOG
