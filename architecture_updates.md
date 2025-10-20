ComfyVN — Architecture Update Notes (2025-10-21)
================================================

Scope: Snapshot of recent local changes and alignment tasks against `ARCHITECTURE.md`.

- Added audio/advisory API scaffolding with logging (`tts_api.py`, `voice_api.py`, `advisory_api.py`), recorded curl/debug steps in `architecture.md`, and published subsystem playbooks (`docs/studio_phase6_audio.md`, `docs/studio_phase7_advisory.md`).

Recent Changes Observed
----------------------
- CLI (`comfyvn/cli.py`) unified under Typer with `bundle`, `manifest`, `check`, `login`, and `scenes` commands; logging initialised per subcommand.
- Scene bundle workflow is now tracked: `comfyvn/scene_bundle.py`, `docs/scene_bundle.md`, and `tests/test_scene_bundle.py` landed with schema validation hooks.
- `run_comfyvn.py` enhanced with logging normalization (launcher/gui/server log separation) and venv bootstrap. Logging aligns with Phase 1 Part C requirement.
- GUI shell updates: menu rebuilt under “Modules” top-level, ServerBridge polling 3s cadence, dock tabification to prevent module overlap. This satisfies Phase 1 Part B acceptance criteria from the architecture doc.
- Server bootstrap repaired: `comfyvn/server/app.py` now exposes `create_app()`, enables CORS, configures logging, and registers `/health` + `/status`, fulfilling Phase 1 Part A.
- Legacy entrypoint aligned: `comfyvn/app.py` delegates to the canonical factory, preserves `/healthz` for legacy probes, and documents the logging/debug flow.
- GUI detached-server helper updated to launch `python comfyvn/app.py`, matching the new entrypoint behaviour and writing to `logs/server_detached.log`.
- Phase 2 migration script expanded (`tools/apply_phase06_rebuild.py`) adding project-aware columns and registry tables (variables, templates, providers, settings). Asset registry exposes `register_file` with sidecar output.
- Phase 5 compute span landed: `comfyvn/core/gpu_manager.py`, `/api/gpu/*`, `/api/providers/*`, and `/compute/advise` expose policy-aware device selection, provider health checks, and advisor rationale. Job metadata now includes the selected compute target, and registry/logging emits debug messages for troubleshooting.
- Phase 5 metrics/job queue completed: `/jobs/ws` streams registry updates via FastAPI WebSocket; `JobsPanel` consumes the stream with auto-reconnect + HTTP fallback, writing state changes to `logs/gui.log` for diagnosis.
- VN importer pipeline landed: `comfyvn/server/core/vn_importer.py`, `/vn/import` API, GUI VN importer wiring, TaskRegistry-backed jobs (`/jobs/status/:id`), `GET /vn/import/{job_id}`, and per-import summaries archived under `data/imports/vn/*` for provenance/debugging. GUI follow-ups captured in `docs/gui_followups.md`.
- Studio API stubs (`comfyvn/server/modules/studio_api.py`) provide `/api/studio/open_project`, `/switch_view`, `/export_bundle`; `comfyvn/gui/studio_window.py` prototype consumes them via `ServerBridge.post`.
- Roleplay importer endpoints (`POST /roleplay/import`, `GET /roleplay/imports/{job_id}`) hardened: jobs/import rows now created via studio registries, scenes/characters persisted, transcripts registered as assets, and debug logs stored in `logs/imports/`.
- Import observability expanded with `/roleplay/imports` listing and `/roleplay/imports/{job_id}/log` streaming so Studio panels can surface queues + logs without touching disk.
- Studio main window now persists geometry/layout via `QSettings`, and File menu includes New/Close/Recent project actions above the folder shortcuts.
- Scenes/Characters/Imports/Audio/Advisory panels dockable via Modules menu, backed by registry/table endpoints for Phase 4 readiness.
- Assets router rebuilt: `/assets/*` delegates to `AssetRegistry` for list/detail/upload/register/delete, enforces metadata validation, and reuses thumbnail/sidecar helpers.
- Asset provenance pipeline added: `AssetRegistry.register_file` records provenance rows, stamps PNG metadata, returns ledger details, and honours license metadata; tests (`tests/test_asset_provenance.py`) and docs (`docs/studio_assets.md`) describe verification steps.
- Phase 0 scaffolding added: `tools/apply_phase06_rebuild.py`, `comfyvn/studio/core/*`, and `docs/studio_phase0.md`, moving toward Phase 2 “Data layer & registries”.

Gaps vs. Architecture Plan
--------------------------
- `architecture.md` expects StudioShell module (`gui/studio_window.py`) with sidebar/toolbar layout; prototype exists but the primary launcher still favours `main_window`. Decide on migration strategy or update documentation to reflect dual shells.
- Asset registry background thumbnail worker still pending; audio/voice provenance markers require additional ID3 tooling.
- Importer and compute pipelines lack end-to-end regression tests; add fixtures that exercise `/vn/import`, `/roleplay/import` (list/log), and GPU advisor flows.
- Scripts location mismatch: architecture baseline lists `scripts/run_comfyvn.py`; repo keeps launcher at root. Decide whether to relocate or adjust documentation.

Immediate Repair / Follow-up Tasks
----------------------------------
1. **Studio shell decision** — Promote `StudioWindow` to primary launcher (or document why not), migrate views into `gui/views/`, and align with architecture navigation specs.
2. **Provenance follow-ups** — Introduce background thumbnail worker and extend provenance stamping to audio/voice assets.
3. **Importer/compute regression suite** — Add pytest flows covering `/vn/import`, `/roleplay/import`, and GPU advisor endpoints to catch regressions.
4. **Docs alignment** — Update `ARCHITECTURE.md` and Studio docs once shell + asset tasks land, ensuring run scripts and logging guidance stay consistent.

Use this document as a working checklist while bringing the repo back in sync with the architectural intent.
