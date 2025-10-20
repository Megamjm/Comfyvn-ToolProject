### 2025-10-23 — Assets Upload Dependency Guard (chat: Platform Health)
- Added explicit `python-multipart` runtime dependency so the `/assets/upload` FastAPI route loads in headless environments.
- Hardened `comfyvn.server.modules.assets_api` to log a warning + return HTTP 503 when multipart parsing is unavailable, instead of failing router registration silently.
- Extended upload logging with debug-level provenance payload emission to aid troubleshooting in `logs/server.log`.

### 2025-10-22 — Launcher & Server Bridge Alignment (chat: Studio Ops)
- `run_comfyvn.py` now exposes unified CLI flags (`--server-only`, `--server-url`, `--server-reload`, `--uvicorn-app`, etc.) so the same entrypoint drives GUI launches, headless server runs, and remote-attach workflows.
- Launcher propagates `COMFYVN_SERVER_BASE`, `COMFYVN_SERVER_AUTOSTART`, host/port, and uvicorn defaults to the GUI and re-exec bootstrap, enabling reproducible headless test runs.
- `ServerBridge` adds synchronous helpers (`ping`, `ensure_online`, `projects*`) plus optional async callbacks, ensuring GUI menus/panels can connect to remote or local servers without requiring Qt to be installed server-side.
- Main window status polling now consumes the new bridge contract, and settings/gpu panels surface success/error states from REST calls.
- Documentation refreshed (`README.md`, `architecture.md`) with a startup command list and environment variable guide for the new launcher.
- Settings panel exposes a *Compute / Server Endpoints* manager driven by the compute provider registry and provider APIs, including local discovery, manual add/remove, and health probes that keep GPU tooling in sync with remote nodes.
- Reduced GUI log noise by downgrading transient HTTP failures to warnings within `ServerBridge`.
- Launcher now performs a lightweight hardware probe before auto-starting the embedded backend and logs a warning (without crashing) when no suitable compute path is available, defaulting to remote attach flows.
- Studio status bar gained a separate script indicator; script utilities update it with green/amber/red icons while logging failures for post-mortem analysis.

### 2025-10-21 — Asset Provenance Ledger (chat: Core Updates)
- `AssetRegistry.register_file` now records provenance rows, preserves license metadata, and writes sidecars containing provenance ids/source/hash.
- PNG assets receive an inline `comfyvn_provenance` marker (Pillow-backed); unsupported formats log a debug notice without mutating originals.
- REST endpoints (`/assets/upload`, `/assets/register`, `/roleplay/import`) pass provenance payloads so responses include ledger data for debugging.
- Added `ProvenanceRegistry`, updated docs (`docs/studio_assets.md`, `docs/studio_phase2.md`, `architecture.md`), and introduced `tests/test_asset_provenance.py` to validate the workflow.

### 2025-10-20 — VN Importer Pipeline (chat: Importer)
- Added `comfyvn/server/core/vn_importer.py` to unpack `.cvnpack/.zip` bundles with manifest auditing, license capture, and structured logging.
- New `/vn/import` FastAPI endpoint exposes the importer; GUI `VNImporterWindow` now POSTs to the route and surfaces summaries/warnings.
- `/vn/import` runs through `TaskRegistry`, exposing job IDs (`/jobs/status/:id`) and progress updates; GUI polls job status until completion.
- Added `GET /vn/import/{job_id}` for downstream tooling to fetch job metadata + cached summary JSON; importer now records `summary_path` for audit trails.
- Import summary persisted per job (`data/imports/vn/<id>/summary.json`) to assist debugging and provenance checks.
- Tests cover importer + API workflows (`tests/test_vn_importer.py`).

### 2025-10-21 — Audio & Advisory API scaffolding (chat: Audio & Policy)
- TTS stub (`comfyvn/core/audio_stub.py`) now emits artifact + sidecar with deterministic caching and structured logging.
- FastAPI modules expose `/api/tts/synthesize`, `/voice/*`, and `/api/advisory/*` endpoints with validation and debug logs.
- Advisory core now tracks issue IDs, timestamps, and resolution notes for downstream provenance.
- Documentation: added `docs/studio_phase6_audio.md` and `docs/studio_phase7_advisory.md` for subsystem playbooks.

### 2025-10-21 — Server Entrypoint Consolidation (chat: Core Updates)
- `comfyvn/app.py` now delegates to `comfyvn.server.app.create_app`, keeping `/healthz` for legacy checks.
- Added `tests/test_server_entrypoint.py` to verify `/health`, `/healthz`, and `/status` coverage.
- Documentation refreshed with logging/debug guidance and entrypoint notes.

### 2025-10-21 — Roleplay Import + Asset Registry Integration (chats: Asset & Sprite System, Roleplay/World Lore)
- `/roleplay/import` now persists scenes and characters via the studio registries, records jobs/import rows, and archives raw transcripts to `logs/imports/roleplay_*` for debugging.
- `GET /roleplay/imports/{job_id}` aggregates job + import metadata (including log paths) so the GUI can surface importer status.
- `GET /roleplay/imports` + `GET /roleplay/imports/{job_id}/log` expose importer dashboards and inline log streaming for the Studio shell.
- `/assets/*` router delegates to `AssetRegistry` for list/detail/upload/register/delete, validates metadata, and resolves file downloads while keeping sidecars/thumbnails consistent.
- Studio core gains `JobRegistry`, `ImportRegistry`, and character link helpers that underpin the importer pipeline.

### 2025-10-20 — S2 Scene Bundle Export (chat: S2)
- Added `comfyvn/scene_bundle.py` to convert ST raw → Scene Bundle (schema-valid).
- CLI: `comfyvn bundle --raw ...` emits `bundles/*.bundle.json`.
- Tag support: [[bg:]], [[label:]], [[goto:]], [[expr:]] injected as stage events.
- Tests: `tests/test_scene_bundle.py`.

### 2025-10-20 — Studio Phase 1 & 2 Foundations
- Server bootstrap now uses `create_app()` factory with `/health` + `/status`, CORS, and unified logging (`comfyvn/server/app.py`).
- GUI shell stabilised: menu guard, ServerBridge host/save hooks, metrics polling, and dock tabbing (Phase 1 completion).
- Phase-06 rebuild script provisions all studio tables (variables/templates/providers/settings) with column backfills.
- Studio registry package (`comfyvn/studio/core`) gains template/variable registries and asset `register_file` helper emitting sidecars.
- Documentation: `docs/studio_phase1.md`, `docs/studio_phase2.md`, and `docs/studio_assets.md` outline the current state.
- Studio coordination API (`/api/studio/*`) added with logging; new `comfyvn/gui/studio_window.py` prototype uses these endpoints. Docs: `docs/api_studio.md`.
- Roleplay importer hardened: `POST /roleplay/import` + status endpoint emit structured logs, persist raw transcripts, create scenes/characters, and index assets. Docs: `docs/import_roleplay.md`.
- Studio main window now saves/restores UI layout (`QSettings`) and the File menu exposes New/Close/Recent project entries alongside folder shortcuts.
- Added dockable Scenes, Characters, Imports, Audio, and Advisory panels wired to registry and API endpoints to mirror architecture Phase 4 design.



ComfyVN ToolProject
Change Log — Version 0.2 Development Branch

────────────────────────────────────────────
Release Type: Major System Alignment Update
Date: 10-10-2025
────────────────────────────────────────────

Summary:
This release establishes the ComfyVN multi-layer architecture, integrating all subsystems into the unified project baseline. It updates documentation, finalizes the system’s rendering structure, adds world-lore and persona logic, and introduces audio and playground foundations. The project now transitions from scaffold to active development phase.

Core Additions:
• Established Project Integration framework to manage all subsystems.
• Added Server Core using FastAPI for unified endpoint handling.
• Introduced Scene Preprocessor for merging world, character, and emotion data.
• Integrated Mode Manager supporting Render Stages 0–4.
• Implemented Audio_Manager with per-type toggles for sound, music, ambience, voice, and FX.
• Completed World_Loader module for cached world-lore and location theming.
• Added Persona_Manager for user avatar display and multi-character layout logic.
• Added NPC_Manager for background crowd rendering with adjustable density.
• Introduced Export_Manager for batch character dump and sprite sheet generation.
• Implemented LoRA_Manager with local cache and search registration.
• Created Playground_Manager and API for live scene mutation and branch creation.
• Added Packaging scripts for Ren’Py export and asset bundling.
• Established Audio, Lore, Character, Environment, and LoRA data directories.

Changes and Improvements:
• Converted documentation to reflect multi-mode rendering and layered architecture.
• Replaced all Flask references with FastAPI to support async processing.
• Standardized scene data schema to include media toggles, render_mode, and npc_background.
• Updated safety system tiers: Safe, Neutral, and Mature.
• Improved README to align with current system design and terminology.
• Added automatic capability detection for hardware and performance scaling.
• Introduced consistent JSON field naming across all modules.

Fixes:
• Corrected initial import paths and module naming inconsistencies.
• Ensured World_Loader loads active world cache correctly.
• Verified cache and export managers reference local directories safely.
• Removed deprecated directory references from prior VNToolchain iteration.

Known Limitations:
• Cinematic (Stage 4) rendering not yet implemented.
• Audio mixing and crossfade functions incomplete.
• Playground prompt parser currently placeholder only.
• GUI configuration panels under development.
• LoRA training disabled pending resource optimization testing.

Next Phase Goals (Version 0.3):
• Complete cinematic video rendering path (ComfyUI workflow integration).
• Expand GUI and Playground scene editors for interactive content creation.
• Add auto-ambience and world-specific audio themes.
• Enable lightweight LoRA training for recurring characters.
• Begin test exports to Ren’Py using finalized Scene JSON structures.

────────────────────────────────────────────
End of Change Log for ComfyVN v0.2
