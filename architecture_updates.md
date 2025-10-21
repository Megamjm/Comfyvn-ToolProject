ComfyVN — Architecture Update Notes (2025-10-21)
================================================

Scope: Snapshot of recent local changes and alignment tasks against `ARCHITECTURE.md`.

- Phase 6 progression: audio cache manager (`comfyvn/core/audio_cache.py`), `/api/music/remix` stub, GUI audio panel hooked to new endpoints, and ComfyUI workflow guide (`docs/comfyui_music_workflow.md`) for real pipelines.
- Phase 7 progression: policy gate + filter endpoints (`policy_api.py`), settings-backed acknowledgements, and advisory-friendly filter previews documented for debugging.
- Runtime storage overhaul: `comfyvn/config/runtime_paths.py` centralises log/config/cache/data directories via `platformdirs`, relocates mutable assets to user-space folders, exposes overrides (`COMFYVN_RUNTIME_ROOT`, `COMFYVN_LOG_DIR`, etc.), and provisions optional symlink shims for legacy `logs/` / `data/settings` references.
- Extension compatibility enforcement: `extensions_discovery` validates `extension.json` manifests (semantic `requires`, entrypoints, API hints), `menu_runtime_bridge` now supports callable callbacks, and GUI reloads surface incompatibilities via the new warning toast log.
- Timeline builder pass: new `TimelineRegistry` + dockable Timeline panel provide drag/drop sequences, notes per entry, and persistence for multiple timelines per project.
- World lore pipeline: seeded default `data/worlds/default_world.json`, `world_prompt.build_world_prompt()` converts SillyTavern-style lore into ComfyUI prompt text with trace metadata, and documentation captured in `docs/world_prompt_notes.md`.
- Sprite & pose controls: `SpritePanel` exposes persona expression switching, sprite previews, and pose assignment via `PoseManager`; persona metadata now retains the applied pose for ComfyUI exports.
- Player persona roster: PersonaManager now persists active player/character state, `/player/*` APIs expose roster + import hooks, and the GUI Player Persona panel drives active selection with live metadata previews.
- Offline LLM registry: provider templates add a `local_llm` runtime, packaged node sets include the ComfyUI LLM bridge, and persona defaults embed offline dialogue profiles for air-gapped production.
- Workflow templates expanded: ComfyUI-ready specs (`sprite_composite_basic`, `pose_blend_basic`, `sprite_pose_composite`) landed with runtime stubs so GUI requests can be simulated without a running ComfyUI instance.
- Production workflows baseline: `comfyvn/bridge/{comfy,tts,remote}.py` provide REST + TTS + remote compute wiring, provider templates live in `comfyvn/providers/`, canonical graphs ship under `comfyvn/workflows/` (`sprite_pack.json`, `scene_still.json`, `video_ad_evolved.json`, `voice_clip_xtts.json`), and `tools/lock_nodes.py` regenerates `nodeset.lock.json` from local nodes.
- SillyTavern bridge now reads configurable settings (base URL + plugin path), the ST extension exposes `/comfyvn/roots` for source directories, and roleplay imports persist raw/processed/final transcripts with detail-level aware LLM passes + editor endpoints (`/preview/{scene_uid}`, `/apply_corrections`, `/sample_llm`).

Recent Changes Observed
----------------------
- CLI (`comfyvn/cli.py`) unified under Typer with `bundle`, `manifest`, `check`, `login`, and `scenes` commands; logging initialised per subcommand.
- Scene bundle workflow is now tracked: `comfyvn/scene_bundle.py`, `docs/scene_bundle.md`, and `tests/test_scene_bundle.py` landed with schema validation hooks.
- `run_comfyvn.py` enhanced with logging normalization (launcher/gui/server log separation) and venv bootstrap. Logging aligns with Phase 1 Part C requirement.
- Base URL authority module (`comfyvn/config/baseurl_authority.py`) centralises host/port resolution: `COMFYVN_BASE_URL` → runtime state file → `settings/config.json` → `comfyvn.json` → default. `run_comfyvn.py` writes the bound host/port back to `config/runtime_state.json` and exports `COMFYVN_SERVER_BASE`/`COMFYVN_BASE_URL` for child processes while `/settings/{set,save}` continues to use the shared `SettingsManager` with deep-merge semantics.
- Asset registry thumbnail generation now happens via a shared background worker so large image imports stop blocking the registration path, and audio/voice assets embed provenance markers when Mutagen is available (MP3/OGG/FLAC/WAV).
- GUI shell updates: menu rebuilt under “Modules” top-level, ServerBridge polling 3s cadence, dock tabification to prevent module overlap. This satisfies Phase 1 Part B acceptance criteria from the architecture doc.
- Presentation planning shim: `comfyvn/presentation/directives.py` defines atomic directive compilation, `/api/presentation/plan` exposes the planner, and the Scenes view embeds a non-blocking preview widget to display compiled plans in JSON form.
- Server bootstrap repaired: `comfyvn/server/app.py` now exposes `create_app()`, enables CORS, configures logging, and registers `/health` + `/status`, fulfilling Phase 1 Part A.
- Legacy entrypoint aligned: `comfyvn/app.py` delegates to the canonical factory, preserves `/healthz` for legacy probes, and documents the logging/debug flow.
- GUI detached-server helper updated to launch `python comfyvn/app.py`, matching the new entrypoint behaviour and writing to `server_detached.log` in the user log directory.
- Phase 2 migration script expanded (`setup/apply_phase06_rebuild.py`) adding project-aware columns and registry tables (variables, templates, providers, settings). Asset registry exposes `register_file` with sidecar output.
- Phase 5 compute span landed: `comfyvn/core/gpu_manager.py`, `/api/gpu/*`, `/api/providers/*`, and `/compute/advise` expose policy-aware device selection, provider health checks, and advisor rationale. Job metadata now includes the selected compute target, and registry/logging emits debug messages for troubleshooting.
- Phase 5 metrics/job queue completed: `/jobs/ws` streams registry updates via FastAPI WebSocket; `JobsPanel` consumes the stream with auto-reconnect + HTTP fallback, writing state changes to `gui.log` in the user log directory for diagnosis.
- VN importer pipeline landed: `comfyvn/server/core/vn_importer.py`, `/vn/import` API, GUI VN importer wiring, TaskRegistry-backed jobs (`/jobs/status/:id`), `GET /vn/import/{job_id}`, and per-import summaries archived under `data/imports/vn/*` for provenance/debugging. GUI follow-ups captured in `docs/gui_followups.md`.
- Arc/unpacker support: `/vn/tools/*` endpoints manage external extractor registrations with legal warnings, importer detects `.arc/.xp3` via registered binaries, and `extensions/tool_installer` surfaces installer docs for GUI integration.
- Documentation: `docs/importer_engine_matrix.md` outlines engine detection signatures + hook expectations; `docs/remote_gpu_services.md` captures provider catalog and advisor inputs for importer-driven GPU recommendations; `docs/tool_installers.md` expanded with config notes.
- Importer scaffolding landed (`comfyvn/importers/*`, `core/normalizer.py`, CLI `bin/comfyvn_import.py`) with comfyvn-pack schema writer and detection heuristics for Ren'Py, KAG, NScripter, Yu-RIS, CatSystem2, BGI, RealLive, Unity VN, TyranoScript, LiveMaker.
- `/api/gpu/advise` leverages new compute advisor heuristics to balance local VRAM vs. curated remote providers; recommendations include cost hints and provider notes for RunPod/Vast.ai/Lambda/AWS/Azure/Paperspace/unRAID.
- Extractor catalog expanded to top 20 community tools (Light.vnTools mirrors, GARbro, KrkrExtract, XP3 tools, CatSystem2/BGI/RealLive utilities, Unity asset rippers). `/vn/tools/catalog` lists metadata; `/vn/tools/install` downloads with license warnings and auto-registration.
- Studio API stubs (`comfyvn/server/modules/studio_api.py`) provide `/api/studio/open_project`, `/switch_view`, `/export_bundle`; `comfyvn/gui/studio_window.py` prototype consumes them via `ServerBridge.post`.
- Roleplay importer endpoints (`POST /roleplay/import`, `GET /roleplay/imports/{job_id}`) hardened: jobs/import rows now created via studio registries, scenes/characters persisted, transcripts registered as assets, and debug logs stored under the imports subfolder of the user log directory.
- Import observability expanded with `/roleplay/imports` listing and `/roleplay/imports/{job_id}/log` streaming so Studio panels can surface queues + logs without touching disk.
- Studio `RoleplayImportView` now binds to the importer endpoints, auto-refreshing every 10s and offering inline log viewing for rapid debugging.
- Studio main window now persists geometry/layout via `QSettings`, and File menu includes New/Close/Recent project actions above the folder shortcuts.
- Scenes/Characters/Imports/Audio/Advisory panels dockable via Modules menu, backed by registry/table endpoints for Phase 4 readiness.
- Assets router rebuilt: `/assets/*` delegates to `AssetRegistry` for list/detail/upload/register/delete, enforces metadata validation, and reuses thumbnail/sidecar helpers.
- Asset provenance pipeline added: `AssetRegistry.register_file` records provenance rows, stamps PNG metadata, returns ledger details, and honours license metadata; tests (`tests/test_asset_provenance.py`) and docs (`docs/studio_assets.md`) describe verification steps.
- Phase 0 scaffolding added: `setup/apply_phase06_rebuild.py`, `comfyvn/studio/core/*`, and `docs/studio_phase0.md`, moving toward Phase 2 “Data layer & registries”.

Gaps vs. Architecture Plan
--------------------------
- `architecture.md` expects StudioShell module (`gui/studio_window.py`) with sidebar/toolbar layout; prototype exists but the primary launcher still favours `main_window`. Decide on migration strategy or update documentation to reflect dual shells.
- Asset pipeline follow-up: wire UI/CLI progress indicators to the async thumbnail worker and document optional Mutagen installation so audio provenance tagging is predictable across environments.
- Importer and compute pipelines lack end-to-end regression tests; add fixtures that exercise `/vn/import`, `/roleplay/import` (list/log), and GPU advisor flows.
- Scripts location mismatch: architecture baseline lists `scripts/run_comfyvn.py`; repo keeps launcher at root. Decide whether to relocate or adjust documentation.

Immediate Repair / Follow-up Tasks
----------------------------------
1. **Studio shell decision (resolved for v0.8)**
   - Decision: Keep `MainWindow` as the primary Studio shell for v0.8; `StudioWindow` remains a lightweight prototype targeting new `/api/studio/*` endpoints.
   - Rationale: `MainWindow` integrates panels, menu registry, and stable polling; switching launchers now would risk regressions without clear user benefit.
   - Next: Fold the useful Studio toolbar actions into `MainWindow` and continue evolving `/api/studio/*` without changing the launcher.
2. **Provenance follow-ups**
   - Introduce background thumbnail worker and extend provenance stamping to audio/voice assets.
3. **Importer/compute regression suite**
   - Add pytest flows covering `/vn/import`, `/roleplay/import` (list/log/GUI), and GPU advisor endpoints to catch regressions.
4. **Docs alignment (started)**
   - `ARCHITECTURE.md` updated to clarify primary shell; launcher remains `comfyvn.gui.main_window` via `run_comfyvn.py`.
5. **Server API polish (resolved 2025-10-23)**
   - Renamed `RegisterAssetRequest.copy` → `copy_file` (kept alias) to silence the Pydantic warning without breaking callers.
   - Added `tests/test_settings_api.py::test_settings_save_deep_merge` to lock deep-merge semantics and `tests/test_launcher_smoke.py` to exercise the launcher `/health` + `/status` smoke path.
   - Documentation touch-up: `docs/studio_assets.md` now explains the new `copy_file` request flag (legacy `copy` still accepted).
  - Roleplay importer responses now include `logs_path`, tests read the runtime log location instead of assuming the legacy `logs/imports/` folder, and async VN import polling waits for the returned summary to avoid flakes.

Use this document as a working checklist while bringing the repo back in sync with the architectural intent.
