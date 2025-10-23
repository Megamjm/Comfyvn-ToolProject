### 2025-10-30 — SQLite Migrations & Settings API Refresh
- Introduced `comfyvn/db/migrations.py` with SQL payloads under `comfyvn/db/sql/` and a reusable `MigrationRunner`. Apply migrations via `python tools/apply_migrations.py [--list|--dry-run|--verbose]`; integrations should drop `setup/apply_phase06_rebuild.py` in favour of the new tooling.
- Added `tools/db_integrity_check.py` (`PRAGMA integrity_check`) and `tools/seed_demo_data.py` (scenes/characters/assets/jobs/providers) for smoke fixtures, plus `tests/test_db_migrations.py` to guard idempotency.
- Rebuilt the settings stack around a Pydantic model that mirrors data to both `settings/config.json` and the SQLite `settings` table. FastAPI now exposes `/system/settings` (GET/POST) and `/system/settings/schema`; GUI bridge posts to the new endpoint and tests/doc stubs were updated accordingly.

### 2025-10-29 — Integrations Installer Automation
- `python -m comfyvn.scripts.install_manager` now orchestrates SillyTavern extension sync, Ren'Py SDK bootstrap, ComfyUI node pack installs, and model presence checks. Runs append JSON summaries to `logs/install_report.log`, reuse cache entries under `tools/cache/`, and accept `--verify-only` for read-only audits plus `--sillytavern`, `--renpy`, `--comfyui`, and `--models` overrides for targeted installs.
- Ren'Py setup reuses cached archives with SHA256 sidecars (`tools/cache/renpy`) and respects the new `cache_dir` parameter so downstream tooling inherits deterministic downloads while still supporting forced refreshes.
- Added installer smoke coverage (`tests/test_install_manager.py`) and refreshed Ren'Py setup tests to exercise the cache path (`tests/test_renpy_setup.py`), keeping regressions visible in CI.
- Documentation highlights: README “Tools & Ports” section documents the CLI, and `.gitignore` now ignores `tools/cache/` so cached archives stay local.

## v0.5.0-world-seed
- Added schemas for world/scene/timeline/assets.
- Seeded 3 open worlds with timelines and scene openers.
- Standardized ComfyUI → PNG+JSON sidecar pipeline under `exports/assets/worlds/<world_id>/...`.
- ComfyUI connector now honors `metadata.asset_pipeline` to drop renders + schema sidecars into the world export tree and refresh per-world manifests.
- Bootstrapped legacy views: `defaults/worlds/*.json` feed the World Manager, `defaults/characters/*.json` hydrate Character Manager, and `TimelineRegistry` now auto-builds `<World> Openers` sequences from the seeded scene samples when the database is empty.

### 2025-10-24 — Studio Shell Diagnostics & Sparklines
- `comfyvn/gui/studio_window.py` now restores Studio layout from `config/studio.json`, syncs host/theme/pane state across sessions, and wires Ctrl+Shift+D to a diagnostics dialog (provider health + log tail) without leaving the app.
- Expanded Studio nav adds Compute, Audio, Advisory, Import Processing, Export, and Logs views. Each panel consumes the `ServerBridge` event bus so host swaps and `/jobs/ws` updates stay live across tabs.
- Scenes, Characters, Import Processing, and Export views gained “Show raw response” toggles for on-demand JSON inspection; payloads fall back to mock data when the backend is offline.
- `MetricsDashboard` renders 90 s CPU/RAM sparklines in addition to usage bars and the embedded server button, keeping `/system/metrics` trends visible at a glance.
- `comfyvn/gui/services/server_bridge.py` exposes `request/get/post`, `subscribe`, and websocket helpers, improving error toasts and enabling downstream widgets to react to `jobs:progress`, `imports:status`, and `system:metrics` without bespoke pollers.

### 2025-10-23 — Exporter Public Routes & Shared Helpers
- Introduced `comfyvn/server/routes/export_public.py` mounting `POST /export/renpy` and `POST /export/bundle`, mirroring the orchestrator used by the `/api/export/*` routes while defaulting outputs to `exports/renpy/<slug>` and `exports/bundles/<slug>.zip`. Responses now include provenance paths, asset copy counts, and a quick asset validation summary.
- Refactored common export utilities into `comfyvn/exporters/export_helpers.py` (label manifest builder, provenance bundle generator, slugify helper, diff serialization). Both the FastAPI routes and `scripts/export_renpy.py` consume the shared module, keeping CLI and HTTP payloads aligned.
- Updated `scripts/export_renpy.py` to rely on the shared helpers instead of bespoke manifest/provenance code paths; CLI dry-runs embed the same diff structure returned by the new HTTP endpoints.
- Extended `tests/test_export_api.py` to exercise the public exporter routes alongside the legacy `/api/export/*` flows, stubbing policy/feature gates for isolation and verifying bundle/provenance artefacts.

### 2025-10-23 — Core Server Diagnostics & Logging
- Logging is initialised before any server import. `comfyvn/logging_config.py` now emits structured JSON lines (file + stdout), honours `LOG_DIR` alongside the legacy env overrides, and injects the active `X-Request-ID` into every record so diagnostics, Studio, and automation can correlate requests across workers.
- `comfyvn/server/app.create_app()` wires request/response timing + request-id middleware, attaches the JSON error envelope, and records the router catalogue during startup. `/status` responds with `{routers, base_url, log_path}` alongside the version and route list, enabling “copy diagnostics” tooling without introspecting code.
- Introduced `AsyncEventHub` (`comfyvn/server/core/event_stream.py`) and refreshed the events module so `/ws/events` is the canonical WebSocket fan-out (with `/events/ws` retained for legacy clients); SSE and WebSocket consumers now share queue backpressure and optional topic filters. Task registry updates bridge into the hub when available.
- Docs updated (README, architecture notes, this changelog) to highlight the JSON logging shape, the expanded `/status` payload, and the new WebSocket endpoint so ops checklists and dashboards stay in sync.

### 2025-10-23 — Compute Advisor Policy Sync & Echo Adapter
- GPU device policy now persists through the shared settings backend (`settings/config.json` + SQLite) and `/api/gpu/list` mirrors `mode`, `preferred_id`, and summarised VRAM metrics (`mem_total`, `mem_free`, `util`) so Studio and automation agree on the active selection.
- `/api/compute/advise` emits a normalised `target` field (`cpu|gpu|remote`) for UI copy and dashboards, and the new `echo` provider adapter returns health without requiring a real remote GPU endpoint—ideal for smoke tests.
- Documentation sweep: README compute highlights, architecture overview, `docs/COMPUTE_ADVISOR.md`, and `docs/dev_notes_compute_advisor.md` now call out the new fields and the lightweight echo adapter.

### 2025-10-21 — VN Loader Panel & Mini-VN Scene Debugger
- Introduced the SillyTavern chat importer (`comfyvn/importers/st_chat/{parser,mapper}.py`) plus FastAPI router `comfyvn/server/routes/import_st.py`, mounted via `server/modules/st_import_api.py` and gated by `features.enable_st_importer` (default OFF). The pipeline parses SillyTavern `.json`/`.txt` transcripts, segments them into scenario graphs, persists run artefacts under `imports/<runId>/`, writes scenes to `data/scenes/<id>.json`, and appends project history to `data/projects/<projectId>.json`.
- New REST surface `/api/import/st/start` / `/api/import/st/status/{runId}` emits structured progress (`phase`, `progress`, `scenes`, `warnings`, `preview`) and broadcasts modder hooks `on_st_import_started`, `on_st_import_scene_ready`, `on_st_import_completed`, and `on_st_import_failed` so dashboards can follow import runs without scraping logs.
- Added `docs/ST_IMPORTER_GUIDE.md` (export workflow, API payloads, heuristics, run artefacts, troubleshooting) plus `docs/dev_notes_st_importer.md`, refreshed README + architecture docs, and extended the Phase 9 checker profile `p9_st_import_pipeline`. Tests: `tests/test_st_importer.py` covers parser heuristics, mapping, and REST flows.
- Added `comfyvn/gui/panels/vn_loader_panel.py`, a dockable VN loader that lists projects (`GET /api/vn/projects`), triggers rebuilds from import manifests (`POST /api/vn/build`), inspects compiled scenes (`GET /api/vn/scenes`), and opens deterministic Mini-VN previews or a native Ren'Py session on demand.
- Mini-VN previews now reuse the shared `MiniVNPlayer` snapshot logic inside the GUI, keeping digests and thumbnail metadata aligned with the viewer fallback (`/api/viewer/status`, `/api/viewer/mini/*`).
- Documentation sweep: new `docs/VN_VIEWER_GUIDE.md`, README highlights, architecture overview/update entries, and refreshed viewer dev notes to capture Phase 9 loader hooks.
- `p9_viewer_integration` checker updated implicitly via required files to validate the panel + guide before releases.

### 2025-10-22 — Live Fixes: Server Boot, Liability Gate, Tools Panels
- `comfyvn/gui/server_boot.py` now launches detached servers via `python -m uvicorn comfyvn.app:app`, extends the environment with the repository root, and honours the shared runtime authority so Windows launches stop failing with `ModuleNotFoundError: comfyvn`.
- Liability acknowledgements persist to `config/policy_ack.json`, and `/api/policy/ack` returns a lightweight `{ack,status}` payload. CLI/GUI callers can raise `PermissionError` via the new `require_ack_or_raise` helper.
- Tools → Import Assets / Ren'Py Exporter / External Tool Installer ship interactive panels powered by a reusable JSON endpoint tester (`comfyvn/gui/panels/json_endpoint_panel.py`). Presets cover SillyTavern chat/persona/lore imports, FurAffinity drops, roleplay archives, and remote installer dry-runs.
- Added a modal `SettingsWindow` wrapper so Settings can pop as a dialog while keeping the legacy dock for power users. Tools menu gained shortcuts for SillyTavern chat, persona, lore, FurAffinity, and roleplay ingestion.
- Shared `discover_base()` lived in `comfyvn/config/baseurl_authority.py`; both `tools/check_current_system.py` and `tools/doctor_phase_all.py` consume it so automation follows the same CLI/env/config/fallback order.
- Docs: README live-fix highlights, architecture updates entry, and CHANGELOG note. Help menu now opens local docs (`README.md`, `docs/THEME_KITS.md`, etc.) via `QDesktopServices`.

### 2025-10-21 — Ports Source of Truth & REST Controls
- Added `comfyvn/config/ports.py` to manage the canonical `{host, ports[], public_base}` block, apply `COMFYVN_HOST/COMFYVN_PORTS/COMFYVN_BASE` overrides, and stamp configs while persisting `.runtime/last_server.json`.
- Introduced FastAPI router `comfyvn/server/routes/settings_ports.py` exposing `/api/settings/ports/{get,set,probe}` with structured probe attempts so modders and automation can inspect bindings without touching disk.
- `comfyvn/server/app.py` now logs the resolved base once on startup and records runtime state, while `run_comfyvn.py` gained `--host/--port` aliases plus ordered roll-over when the port flag is omitted.
- Documentation sweep: README one-liner, refreshed `docs/PORTS_ROLLOVER.md` (config, env, curl recipes), CHANGELOG entry.

### 2025-12-24 — Desktop Settings: Port Binding Panel
- Added `comfyvn/gui/settings/network_panel.py`, providing a GUI surface for host binding, rollover port order, and optional public base overrides. The panel consumes `/api/settings/ports/{get,set,probe}` so Studio mirrors launcher config updates without editing JSON.
- Shipped `/studio/settings/network.html`, an admin-gated web page that reuses the same API, verifies Bearer tokens via `/api/auth/me`, mirrors probe attempts (“would bind to” summary), and surfaces ready-to-share curl drills for modders and automation teams.
- `/api/settings/ports/probe` responses now surface in the UI, helping teams confirm which port bound successfully before restarting the backend. Probe output includes selected host/port, HTTP status, and latency where available.
- Documentation sweep: refreshed `README.md` (Settings → Network / Port Binding), `architecture.md` (docs index), `architecture_updates.md` (Settings snapshot), new `apps/web/README.md`, updated `docs/PORTS_ROLLOVER.md` for automation/debug drills, and refreshed `docs/dev_notes_network_ports.md` for contributor guidance. Logged in this CHANGELOG.

### 2025-12-23 — Community Connectors: F-List & FurAffinity
- Added `comfyvn/connectors/{flist,furaffinity}.py` to parse F-List profile exports into persona payloads and to store user-supplied FurAffinity uploads with hashed filenames, provenance sidecars, and NSFW tag trimming when the gate is closed.
- Introduced FastAPI router `comfyvn/server/routes/connectors_persona.py` (`/api/connect/flist/consent|import_text`, `/api/connect/furaffinity/upload`, `/api/connect/persona/map`) behind `features.enable_persona_importers`. All routes respect the consent gate (`data/persona/consent.json`) and broadcast new modder hooks `on_flist_profile_parsed`, `on_furaffinity_asset_uploaded`, and `on_connector_persona_mapped` (alongside `on_persona_imported`).
- Extended `comfyvn/persona/schema.py` with `PersonaPreferences` (likes/dislikes/nope) so connector payloads capture roleplay boundaries without custom metadata hacks.
- Documentation sweep: new `docs/COMMUNITY_CONNECTORS.md`, refreshed `docs/NSFW_GATING.md`, new `docs/dev_notes_community_connectors.md`, plus README/architecture/architecture_updates updates. Checker profile `p7_connectors_flist_fa` validates flag defaults, routes, and required docs.

### 2025-12-22 — Asset Ingest Queue & Dedup
- Introduced `comfyvn/ingest/{__init__,queue,mappers}.py`, staging community assets under `data/ingest/staging/`, hashing via the shared `CacheManager`, normalising provider metadata (FurAffinity uploads, Civitai/Hugging Face pulls), and persisting queue state with rate-limited remote fetches.
- Added FastAPI router `comfyvn/server/routes/ingest.py` exposing `/api/ingest/{queue,status,apply}`, feature-gated by `enable_asset_ingest`, broadcasting new modder hooks `on_asset_ingest_enqueued`, `on_asset_ingest_applied`, and `on_asset_ingest_failed`.
- Documentation sweep: new `docs/ASSET_INGEST.md`, new `docs/dev_notes_asset_ingest.md`, refreshed `README.md`, and updated `architecture.md` (docs index + dedup status). Checker profile `p7_asset_ingest_cache` covers flag defaults, routes, and docs.

### 2025-12-22 — License Snapshot & Ack Gate
- Added `comfyvn/advisory/license_snapshot.py` to capture/normalise hub licence text, persist `license_snapshot.json` next to assets (fallback `data/license_snapshots/<slug>/`), and retain per-user acknowledgements with provenance in settings.
- Introduced FastAPI router `comfyvn/server/routes/advisory_license.py` exposing `/api/advisory/license/{snapshot,ack,require}` plus a status reader so connectors can block downloads until the current snapshot hash is acknowledged. Responses echo the normalised text for UI prompts and raise HTTP 423 when ack is missing.
- Snapshots and acknowledgements emit `on_asset_meta_updated` payloads (`meta.license_snapshot` / `meta.license_ack`) for dashboards and automation. Docs sweep: new `docs/ADVISORY_LICENSE_SNAPSHOT.md`, new `docs/dev_notes_license_snapshot.md`, refreshed `README.md`, `architecture.md`, and `architecture_updates.md`. Checker profile `p7_license_eula_enforcer` covers flag state, routes, and documentation.

### 2025-12-21 — Hugging Face Hub Search & Pull Planner
- Added `comfyvn/public_providers/hf_hub.py`, providing health/search/metadata helpers, license-aware pull planners, and token resolution for Hugging Face Hub assets (dry-run only).
- Introduced FastAPI router `comfyvn/server/routes/providers_hf.py` exposing `/api/providers/hf/{health,search,metadata}` and `/api/providers/hf/pull`. Pull plans require an `hf_*` PAT plus explicit license acknowledgement; responses normalize card metadata, tag/license hints, and flag files >= 1 GiB.
- Documentation sweep: new `docs/PROVIDERS_HF_HUB.md`, refreshed `README.md` with feature-flag + PAT guidance. Checker profile `p7_connectors_huggingface` validates flag state, routes, and docs without enabling live pulls.

### 2025-12-20 — Web Publish Redaction Preview
- Added `comfyvn/exporters/web_packager.py` producing deterministic Mini-VN web bundles with hashed assets, manifest/content-map/preview/redaction sidecars, and optional modder hook catalogues. Feature flag `enable_publish_web` gates the new FastAPI surface under `comfyvn/server/routes/publish.py`.
- API endpoints `/api/publish/web/{build,redact,preview}` support NSFW stripping, provenance scrubbing, configurable watermarks, and QA health summaries; responses contain archive paths, diff metadata, and ready-to-serve JSON payloads for dashboards.
- Documentation sweep introducing `docs/PUBLISH_WEB.md`, `docs/dev_notes_publish_web.md`, and refreshed `README.md`, `architecture.md`, `architecture_updates.md`. Checker profile `p6_publish_web` now validates flag/route/doc coverage.

### 2025-10-22 — Translation Manager TM, Review Queue & Live Switch
- Overhauled the translation stack with versioned TM persistence (`comfyvn/translation/tm_store.py`), TM-aware language lookups in `comfyvn/translation/manager.py`, and refreshed FastAPI routes in `comfyvn/server/routes/translation.py` (new `/api/translate/review` GET/POST, expanded batch payloads, scoped exports, meta filters, and debug links).
- `TranslationMemoryStore` now records `{key -> {lang -> text, meta, version}}`, tracks hits/confidence/reviewer fields, and exposes scoped JSON/PO exports with optional metadata.
- `TranslationManager.t()` resolves TM overrides before falling back to table/keys, while `get_table_value` enables debug tooling without triggering fallback logic.
- Documentation sweep: new `docs/TRANSLATION_MANAGER.md`, refreshed `README.md`, `docs/LLM_RECOMMENDATIONS.md`, and `docs/dev_notes_translation_tm_review.md`. Architecture notes appended to `architecture_updates.md` (TM flow & live switch wiring).
- Verification: `pytest tests/test_translation_routes.py` green; checker `python tools/check_current_system.py --profile p5_translation --base http://127.0.0.1:8001` covers flag state, routes, and docs.

### 2025-12-18 — Persona Importers & NSFW Gate
- Introduced `comfyvn/persona/schema.py` (persona schema helpers, tag/palette defaults, NSFW policy) plus `comfyvn/persona/importers/community.py` to normalise community markdown/JSON payloads into the persona profile shape.
- Added `comfyvn/server/routes/persona.py` exposing `/api/persona/{consent,import/text,import/images,map,preview}` behind `features.enable_persona_importers` (default **false**) and respecting `features.enable_nsfw_mode` for adult-tag handling. Consent persists to `data/persona/consent.json`, image uploads hash to `data/persona/imports/<id>/` with `.meta.json` sidecars, `/map` writes `data/characters/<id>/persona.json` + `persona.provenance.json`, and the `on_persona_imported` modder hook broadcasts persisted payloads for dashboards/webhooks.
- Documentation sweep: new `docs/PERSONA_IMPORTERS.md`, new `docs/NSFW_GATING.md`, new `docs/dev_notes_persona_importers.md`, README + architecture/architecture_updates refresh. Checker profile `p6_persona_importers` validates flag defaults, routes, docs, and the consent gate.

### 2025-12-17 — Advisory Gate & Studio Bundle Export
- Added `comfyvn/server/routes/advisory.py` (`/api/policy/ack`, `/api/advisory/scan`) and `comfyvn/server/routes/export.py::/bundle/status` so Studio surfaces and automation can probe feature flags, gate state, and run advisory scans with deterministic `info|warn|block` findings. Routes are gated behind `features.enable_advisory` / `features.enable_export_bundle` defaults.
- `comfyvn/advisory/{policy,scanner}.py` gained an `evaluate_action` helper plus deterministic finding dedupe, keeping provenance logs stable while exposing modder hooks through `policy_enforcer`.
- `scripts/export_bundle.py` now enforces the `enable_export_bundle` feature flag (exit code `3` when disabled), returns the enforcement payload (`log_path`, counts, raw findings), and preserves JSON parity with the server export route.
- Documentation sweep: new `docs/ADVISORY_EXPORT.md`, new `docs/dev_notes_advisory_export.md`, refreshed `README.md`, and `architecture.md`. Verification: `python tools/check_current_system.py --profile p5_advisory_export --base http://127.0.0.1:8001`.

### 2025-12-17 — Image→Persona Analyzer & Style Registry
- Added `comfyvn/persona/image2persona.py` for deterministic image→persona hints (appearance tags, 5–8 color swatches, pose anchors, expression prototypes) with provenance digests and conflict reporting. Analyzer exposes hook points for palette/appearance/anchor/expression overrides plus a helper to merge results into persona metadata.
- Introduced `comfyvn/persona/style_suggestions.py` with a registry-driven style/LoRA suggestion surface (names only) keyed by appearance tags; registry supports contributor overrides via `register_style` and `register_lora`.
- Documentation sweep: new `docs/IMAGE2PERSONA.md`, new `docs/dev_notes_image2persona.md`, refreshed `README.md`, `architecture.md`, and `architecture_updates.md`. Debug checklist now tracks the `p6_image2persona` checker; feature flag `enable_image2persona` remains **OFF** by default.

### 2025-12-19 — 2.5D Animation Auto-Rig & Motion Graph
- Introduced `comfyvn/anim/rig/autorig.py` (anchor normalisation, role inference, constraint derivation, idle/breath/blink synthesis, mouth visemes) and `comfyvn/anim/rig/mograph.py` (guarded idle→turn→emote preview sequencing).
- Added FastAPI router `comfyvn/server/routes/anim.py` exposing `/api/anim/{rig,preview,save}`, gated by `features.enable_anim_25d`, with preset persistence under `cache/anim_25d_presets.json` and new modder hooks `on_anim_rig_generated`, `on_anim_preview_generated`, `on_anim_preset_saved`.
- Documentation sweep: new `docs/ANIM_25D.md`, new `docs/dev_notes_anim_25d.md`, refreshed `README.md`, `architecture.md`, `architecture_updates.md`, and feature flag defaults in `config/comfyvn.json` / `comfyvn/config/feature_flags.py`.
- Verification: `python tools/check_current_system.py --profile p6_anim_25d --base http://127.0.0.1:8001` confirms flag state, route availability, and documentation coverage.

### 2025-12-21 — Editor Blocking Assistant & Snapshot Sheets
- Added `comfyvn/editor/{blocking_assistant,snapshot_sheet}.py` plus FastAPI router `comfyvn/server/routes/editor.py`, introducing `/api/editor/{blocking,snapshot_sheet}` behind new feature flags `enable_blocking_assistant` and `enable_snapshot_sheets` (both default **false**).
- Blocking assistant returns deterministic shot/beat plans (`schema`, `shots[]`, `beats[]`, `determinism{seed,digest}`, optional `narrator_plan`) and emits the new `on_blocking_suggested` hook for automation dashboards.
- Snapshot sheet builder composes cached thumbnails or explicit images into PNG/PDF boards under `exports/snapshot_sheets/` and emits `on_snapshot_sheet_rendered` with digest + output metadata for modder tooling.
- Documentation sweep: new `docs/EDITOR_UX_ADVANCED.md`, new `docs/development/dev_notes_editor_blocking.md`, refreshed `README.md`, `architecture.md`, `architecture_updates.md`, and feature flag defaults in `config/comfyvn.json` / `comfyvn/config/feature_flags.py`.
- Verification: `python tools/check_current_system.py --profile p6_editor_ux --base http://127.0.0.1:8001` covers flags, routes, and documentation coverage.

### 2025-12-20 — Web Publish Redaction Preview
- Added `comfyvn/exporters/web_packager.py` producing deterministic Mini-VN web bundles with hashed assets, manifest/content-map/preview/redaction sidecars, and optional modder hook catalogues. Feature flag `enable_publish_web` gates the new FastAPI surface under `comfyvn/server/routes/publish.py`.
- API endpoints `/api/publish/web/{build,redact,preview}` support NSFW stripping, provenance scrubbing, configurable watermarks, and QA health summaries; responses contain archive paths, diff metadata, and ready-to-serve JSON payloads for dashboards.
- Documentation sweep introducing `docs/PUBLISH_WEB.md`, `docs/dev_notes_publish_web.md`, and refreshed `README.md`, `architecture.md`, `architecture_updates.md`. Checker profile `p6_publish_web` now validates flag/route/doc coverage.

### 2025-12-16 — Asset Gallery Search & Registry Enforcer
- Added `comfyvn/server/routes/assets.py` exposing `/api/assets/search` (type/tag/license/text filters plus optional `include_debug` hook snapshots), `/api/assets/enforce` (sidecar audit + repair), and `/api/assets/rebuild` (disk scan + thumbnail refresh) so automation and tooling can maintain the registry without touching private modules.
- `comfyvn/gui/panels/asset_gallery.py` now includes a metadata/path search field alongside the existing type/tag/licence filters, keeping multi-select bulk edits and clipboard debug exports in sync with registry hooks.
- New `docs/ASSET_REGISTRY.md` documents feature flags, curl recipes, hook payloads, and the recommended `tools/check_current_system.py --profile p5_assets_gallery` verification pass.

### 2025-12-18 — Compute Advisor Debug Mode & Cost Previews
- `comfyvn/compute/advisor.py` now supports `return_details` so `/api/compute/advise` can surface pixels, VRAM demand, queue thresholds, and rationale when callers pass `"debug": true`. Remote recommendations automatically fall back to GPU/CPU when `features.enable_compute` stays **false**.
- `ProviderRegistry.stats()` exposes registry counts and storage metadata; compute routes return these stats whenever query/body `debug` flags are set.
- `JobScheduler.preview_cost()` powers the new `/api/compute/costs` endpoint, returning base/transfer/VRAM breakdowns and human-friendly hints without hitting providers. Responses always note that estimates are advisory only.
- API updates: `/api/gpu/list?debug=1`, `/api/providers?debug=1`, `/api/compute/advise` (debug payloads), and `/api/compute/costs` (optional debug). All responses echo the `enable_compute` feature flag, which now defaults to **false** for opt-in remote offload.
- Documentation sweep: new `docs/COMPUTE_ADVISOR.md`, new `docs/dev_notes_compute_advisor.md`, refreshed `README.md`, `architecture.md`, and `architecture_updates.md`.

### 2025-12-16 — Audio Lab TTS Alignment & Mixer Refresh
- Added the `enable_audio_lab` feature flag (default **OFF**) and extended the audio routes with a stub voice catalog (`GET /api/tts/voices`), enriched `/api/tts/speak` responses (alignment checksum, text SHA-1, lipsync metadata, provenance), and a dedicated `/api/audio/align` endpoint that can persist phoneme JSON + lipsync frames under `data/audio/alignments/<text_sha1>/`.
- `comfyvn/bridge/tts_adapter.py` now tracks cache hits, voice hints, waveform checksums, and emits the `on_audio_tts_cached` modder hook; `comfyvn/audio/mixer.py` records waveform stats (`checksum_sha1`, `peak_amplitude`, `rms`, `rendered_at`) so `/api/audio/mix` can surface deterministic metadata alongside cached WAVs.
- `comfyvn/server/routes/audio.py` gates all Audio Lab routes, emits new modder hooks (`on_audio_alignment_generated`, `on_audio_mix_rendered`), and refreshes responses/sidecars. Documentation sweep: new `docs/AUDIO_LAB.md`, updated `README.md`, `architecture.md`, `architecture_updates.md`, and `docs/dev_notes_audio_alignment_mixer.md`; checker profile `p5_audio_lab` now covers flag defaults, routes, and doc coverage without enabling the feature in production.

### 2025-12-15 — Cloud Sync Manifest & Backup Refresh
- Manifest helpers (`comfyvn/sync/cloud/manifest.py`) now publish default include/exclude sets, expose `checksum_manifest`, and raise `SyncApplyError` when provider runs encounter per-file failures. Provider clients (`s3.py`, `gdrive.py`) aggregate upload/delete errors, continue processing remaining files, and upload refreshed manifests only when the plan completes cleanly.
- Added `comfyvn/server/routes/sync_cloud.py`, replacing the legacy routing with `/api/sync/manifest`, `/api/sync/dry_run`, `/api/sync/run`, plus `/api/backup/{create,restore}` for local ZIP archives under `backups/cloud/` with rotation.
- Documentation sweep: new `docs/CLOUD_SYNC.md`, new `docs/BACKUPS.md`, refreshed `README.md`, `architecture.md`, `architecture_updates.md`, and `docs/development/dev_notes_cloud_sync.md`. Run `python tools/check_current_system.py --profile p4_cloud_sync --base http://127.0.0.1:8001` to verify feature flags, routes, and doc coverage.

### 2025-12-14 — Accessibility UI Scale & Input Presets
- Introduced `comfyvn/accessibility/ui_scale.py` and extended the accessibility manager to persist global UI scale (100–200 %) plus per-view overrides. VN Viewer now registers with the UI scale manager so viewer-specific presets update layouts/fonts alongside color filters, high-contrast palettes, and subtitles.
- Expanded input defaults (`SettingsManager.DEFAULTS["input_map"]`) with numeric choice bindings, narrator/overlay toggles, and an editor pick-winner shortcut. `InputMapManager` gained export/import helpers, reset/import events emit `reason` metadata, and new FastAPI routes `/api/accessibility/{set,export,import}` + `/api/input/{map,reset}` mirror the updated surface.
- Added feature flag `enable_accessibility` (default **OFF**) alongside refreshed docs: new `docs/ACCESSIBILITY.md` & `docs/INPUT_SCHEMES.md`, updated `README.md`, `architecture.md`, `architecture_updates.md`, and `docs/development/accessibility_input_profiles.md`. Run `python tools/check_current_system.py --profile p4_accessibility --base http://127.0.0.1:8001` to verify flag defaults, routes, and documentation files.

### 2025-12-12 — Collaboration REST Headless Flows
- `comfyvn/collab/room.py` now exposes `register_headless_client()` so scripts and CI harnesses can reserve presence slots without opening a WebSocket. Headless entries inherit the same Lamport clocks/locks, presence payloads expose a `headless` flag, and `leave()` reports whether a client was removed so HTTP tooling can confirm teardown.
- New FastAPI surface `comfyvn/server/routes/collab.py` adds `/api/collab/room/{create,join,leave,apply}` plus `/api/collab/room/cache`, mirroring WebSocket envelopes, broadcasting CRDT updates, and emitting `on_collab_operation` for modder dashboards. `room/apply` accepts the same op batches as `doc.apply`, supports `history_since`, and can trigger persistence via `flush` to keep offline editors in sync.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/COLLAB_EDITING.md`, and `docs/development_notes.md` describe headless flows, REST payloads, and debug hooks; regression coverage extends `tests/test_collab_api.py` to exercise the new lifecycle.

### 2025-12-10 — Public GPU/Image/Video Providers (Dry-Run)
- Added GPU adapters for RunPod, Hugging Face Inference Endpoints, Replicate, and Modal (`comfyvn/public_providers/gpu_*.py`) plus refreshed media adapters (Stability, fal.ai, Runway, Pika, Luma) with `metadata()`, `health()`, `submit()`, and `poll()` helpers. Each response now includes `pricing_url`, `last_checked`, capability tags, and deterministic mock ids.
- Unified FastAPI surfaces: `/api/providers/gpu/public/{provider}/{health,submit,poll}` and `/api/providers/{image,video}/{provider}/{health,submit,poll}` share dry-run envelopes, feature-flag context, and task-registry registration. Legacy `/image/generate` and `/video/generate` routes delegate to the new submit path for backwards compatibility.
- Documentation sweep: `README.md`, `architecture_updates.md`, new `docs/PROVIDERS_GPU_IMAGE_VIDEO.md`, and the refreshed `docs/dev_notes_public_media_providers.md` capture opt-in flows, env/secrets matrices, pricing links, and debug hooks; this changelog logs the update. Checker profile `p3_providers_gpu_image_video` now validates catalog + health responses without touching external APIs.

### 2025-12-11 — Dungeon Runtime & Snapshot Hooks
- Introduced `comfyvn/dungeon/api.py` with seeded grid and DOOM-lite backends plus `/api/dungeon/{enter,step,encounter_start,resolve,leave}` FastAPI routes (feature flag `enable_dungeon_api`, default **OFF**). Sessions emit deterministic `room_state`, `snapshot`, and `vn_snapshot` payloads so Snapshot→Node/Fork consumers preserve traversal anchors and encounter logs.
- Registered new modder hooks `on_dungeon_enter`, `on_dungeon_snapshot`, and `on_dungeon_leave` so dashboards, automation, and OBS overlays can react to dungeon events. Hook payloads mirror VN context (`scene`, `node`, `pov`, `worldline`, `vars`) alongside deterministic seeds and anchors.
- Documentation sweep: new `docs/DUNGEON_API.md`, companion `docs/dev_notes_dungeon_api.md`, and updates to `README.md`, `architecture.md`, and `architecture_updates.md`. Checker profile `p3_dungeon` now asserts flag defaults, route availability, and doc presence via `python tools/check_current_system.py --profile p3_dungeon`.

### 2025-12-10 — Observability & Perf Umbrella Flags
- `features.enable_observability` now gates the entire telemetry surface (with `enable_privacy_telemetry` kept as a legacy alias). Consent remains opt-in only: `/api/telemetry/opt_in` flips `telemetry_opt_in` without touching crash uploads or diagnostics, `/api/telemetry/health` reports flag + consent state, and every telemetry response mirrors `feature_flag` so dashboards can short-circuit when observability is disabled. Diagnostics bundles add a `health` block and persist consent metadata in `manifest.json`.
- `features.enable_perf` wraps budget throttling and profiler dashboards (legacy `enable_perf_budgets`/`enable_perf_profiler_dashboard` stay valid). The `/api/perf` surface gains `GET /api/perf/health`, per-response `feature_flag` echoes, and helper summaries from `BudgetManager.health()` + `PerfProfiler.health()` so smoke checks can spot queue pressure or noisy spans without parsing full snapshots.
- Settings panel toggles now update both legacy + umbrella flags so Studio surfaces stay in sync; anonymiser hashing adds `key/secret/serial/address` keywords to avoid PII leaks in diagnostics.
- Documentation sweep: brand-new `docs/OBS_TELEMETRY.md`, `docs/PERF_BUDGETS.md`, and `docs/dev_notes_observability_perf.md` capture curl recipes, budgets/profiler hooks, and verification checklists. `README.md`, `architecture.md`, `architecture_updates.md`, `docs/development_notes.md`, and `docs/development/observability_debug.md` reference the new flags and health routes; `docs/development/perf_budgets_profiler.md` mirrors the umbrella flag terminology.

### 2025-12-10 — Public Language Providers & LLM Router (Dry-Run)
- Landed translation, OCR, speech, and LLM adapters under `comfyvn/public_providers/` with accompanying FastAPI routes (`providers_translate_ocr_speech.py`, `providers_llm.py`). `/api/providers/translate/health` and `/api/providers/llm/registry` return pricing links, last-checked timestamps, and credential diagnostics while honouring `enable_public_translate` / `enable_public_llm`.
- Added dry-run endpoints: `POST /api/providers/translate/public` emits translation payload echoes for Google, DeepL, and Amazon; `POST /api/providers/llm/chat` emits router dispatch plans for OpenAI, Anthropic, Google Gemini, and OpenRouter without hitting upstream services.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/PROVIDERS_LANG_SPEECH_LLM.md`, `docs/LLM_RECOMMENDATIONS.md`, and new dev notes `docs/dev_notes_public_language_providers.md` capture env vars, pricing anchors, module presets, and curl snippets. Checker profile `p3_providers_lang_speech_llm` now validates the routes.

### 2025-12-09 — Viewer Failover & Ren'Py Provenance Bundle
- `/api/viewer/status` promotes fallbacks automatically when the native Ren'Py process exits, recording the exit code in `stub_reason` and swapping the GUI into webview or Mini-VN without another start call. Mini-VN snapshots continue to emit deterministic 16:9 thumbnails and now trigger `on_thumbnail_captured` hooks so external caches stay in sync.
- `scripts/export_renpy.py` writes `<out>/label_manifest.json`, `provenance_bundle.zip`, and a flattened `provenance.json` on every successful run while the summary prints `provenance_bundle`, `provenance_json`, `provenance_findings`, and `provenance_error`. `on_export_completed` mirrors the new fields so CI can archive provenance artefacts or flag advisory findings alongside the weather bake flag.
- Documentation sweep: `README.md`, `docs/EXPORT_RENPY.md`, `docs/dev_notes_viewer_stack.md`, `architecture_updates.md`, and this changelog describe the fallback decision tree, provenance outputs, and hook payload changes.

### 2025-12-08 — Battle UX (Editor Pick) & Game Sim v0 Refresh
- Unified the battle engine flows under a shared deterministic core: `resolve()` now accepts `rounds`/`narrate`, emits breakdowns, RNG state, provenance, and a `predicted_outcome` while still respecting editor overrides, and `simulate()` honours the same signature for silent or narrated roll sheets.
- FastAPI router exposes the new `/api/battle/sim` endpoint (feature flag `enable_battle_sim`, default **OFF**) while keeping `/api/battle/simulate` as a legacy alias; resolve/sim responses share a provenance block and optional narration. Expanded modder hooks (`on_battle_resolved`, `on_battle_simulated`) carry `weights`, `breakdown`, `rng`, `provenance`, `predicted_outcome`, `narrate`, `rounds`, and seeded logs when enabled.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/BATTLE_DESIGN.md`, `docs/development/battle_layer_hooks.md`, `docs/dev_notes_modder_hooks.md`, `docs/development_notes.md`, and `docs/PROMPT_PACKS/BATTLE_NARRATION.md` now reflect the refreshed payloads. New note `docs/dev_notes_battle_sim.md` covers flags, hook payloads, curl recipes, and QA tips; `tools/check_current_system.py --profile p2_battle` was updated to assert `/api/battle/sim`.

### 2025-12-07 — Theme Kits & Swap Wizard
- Expanded `comfyvn/themes/templates.py` with fourteen legal-clean kits (Modern School → Cozy) covering palettes, LUTs, SFX/music packs, camera defaults, prop clusters, prompt flavors, and tag remaps plus curated subtypes and accessibility variants (high-contrast + color-blind). `docs/THEME_KITS.md` captures the flavor matrix and anchor guidance, while `docs/STYLE_TAGS_REGISTRY.md` canonicalises the shared vocabulary across themes, props, and battle overlays.
- FastAPI router `comfyvn/server/routes/themes.py` now exposes `/api/themes/{templates,preview,apply}`. Preview composes checksum-stable deltas (assets, palette, camera, props, style tags, per-character overrides, anchor preservation) without mutating saves; apply forks or updates a VN Branch worldline with provenance metadata so OFFICIAL⭐ lanes stay untouched. Branch IDs are slugged deterministically and include `theme_swap` summaries plus mutation change lists.
- Modder hooks `on_theme_preview` and `on_theme_apply` broadcast the new payloads (theme, subtype, variant, preserved anchors, plan checksum, branch snapshot) for dashboards and automation. README, changelog, and docs were refreshed; `enable_themes` now defaults **false** in config so studios opt in deliberately before wiring the wizard.

### 2025-12-06 — Narrator Outliner & Role Mapping (Phase 2)
- Added `comfyvn/server/routes/narrator.py`, providing Observe → Propose → Apply rails with deterministic proposal ids, a three-turn per-node safety cap, rollback snapshots, and `on_narrator_proposal`/`on_narrator_apply` hook emissions. All `/api/narrator/{status,mode,propose,apply,stop,rollback,chat}` routes respect `features.enable_narrator` (default OFF) while exposing `force` overrides for local development.
- Introduced `comfyvn/llm/orchestrator.py`, an offline-first role→adapter planner that tracks sticky sessions, device assignments, and token budgets for Narrator/MC/Antagonist/Extras. `/api/llm/{roles,assign,health}` surface dry-run routing plans and live assignment state behind `features.enable_llm_role_mapping` so multi-GPU deployments stay opt-in.
- VN Chat panel now routes chat turns through the orchestrator: offline adapter `offline.local` remains the default reply engine, the role selector maps to orchestrator assignments, and last-chat metadata (adapter/model/tokens/budget/session) is surfaced inline for debugging.
- Documentation sweep: refreshed `README.md`, `architecture.md`, `architecture_updates.md`, `docs/NARRATOR_SPEC.md`, `docs/LLM_ORCHESTRATION.md`, `docs/dev_notes_modder_hooks.md`, and `docs/development_notes.md`; `tools/check_current_system.py` gained the `p2_narrator` profile to gate CI with flag/route/file checks.

### 2025-12-06 — Extractor Installer & VN Wrapper
- Delivered `tools/install_third_party.py`, an acknowledgement-gated installer that downloads GARbro, arc_unpacker, rpatool, unrpa, KrkrExtract, AssetStudio, and WolfDec into `third_party/` with pinned hashes, manifest metadata, and Python shims (including Windows `.cmd` helpers). Re-runs are idempotent and refresh shims when the expected version already exists.
- Added `tools/vn_extract.py`, a CLI wrapper that auto-detects engines (Ren'Py, KiriKiri, Wolf RPG, Unity, generic archives), selects an installed tool, and writes `imports/<game>/raw_assets/`, `extract_log.json`, and a `license_snapshot.json` for provenance. Supports `--plan-only`, `--dry-run`, overrides, and clean re-runs for automation.
- Introduced `tools/doctor_extractors.py` to emit a JSON/table report covering installed extractors, shim health, and help-probe status (with graceful Wine/.NET warnings). Useful for local audits and CI gates.
- Documented the workflow in the new `docs/EXTRACTORS.md`, refreshed README (Importing Existing VNs quick start), `architecture_updates.md`, and logged the work order in this changelog. Added dummy dry-run validation so contributors can script against the JSON artefacts without touching real archives.

### 2025-12-05 — Worldline Delta Storage & Snapshot Sidecars
- `comfyvn/pov/worldlines.py` now persists delta-over-base metadata (`_wl_delta`) when lanes fork, ensuring derived worldlines only record the differences from their parent while snapshots inherit lane colour, POV, and sidecar context. Snapshot records enrich metadata with workflow hashes, provenance sidecars `{tool,version,workflow_hash,seed,worldline,pov,theme,weather}`, and emit hook payloads carrying the new fields.
- Timeline overlay nodes surface the new `workflow_hash`, `worldline`, and `sidecar` payloads so GUI scrubbers/modder tooling can correlate thumbnails with sidecars. The overlay lane payload now includes the delta dictionary for downstream automation.
- REST stack: `/api/pov/auto_bio_suggest` returns POV-masked bios summarising worldline deltas and snapshot history; existing `/api/pov/{worlds,worlds/switch,confirm_switch}` responses pick up enriched snapshot metadata. Docs refreshed (`README.md`, `architecture.md`, `docs/POV_DESIGN.md`, `docs/TIMELINE_OVERLAY.md`, `docs/dev_notes_worldlines_timeline.md`) with cURL samples, hook field tables, and delta storage diagrams.

### 2025-12-04 — Flat → Layers Pipeline v1
- Added `comfyvn/pipelines/flat2layers.py`, a deterministic rembg/SAM/MiDaS orchestration that exports `layered/character/<id>/{cutout.png,mask.png,anchors.json}` and depth-sliced background planes with provenance sidecars, hook events (`on_mask_ready`, `on_plane_exported`, `on_debug`, `on_complete`), and optional SAM Playground brushes + Real-ESRGAN upscale.
- Delivered `tools/depth_planes.py`, an interactive CLI for tuning depth thresholds and parallax scale with histogram percentiles, preview exports, and JSON output reusable inside the pipeline options.
- Authored `docs/FLAT_TO_LAYERS.md` covering workflow diagrams, feature flag gating (`enable_flat2layers` default OFF), Playground hook wiring, refinement tips, known failure cases, and troubleshooting.

### 2025-12-03 — Phase 8 Integration Sweep
- Hardened the FastAPI factory: `_include_router_module` now tracks path/method signatures and skips legacy routers when they would collide with the modern `/api/*` stack, and `/health`/`/status` endpoints only register when gaps exist. This keeps the surface deterministic for Studio, automation, and modders while allowing legacy modules to coexist under opt-in prefixes.
- `config/comfyvn.json` gains explicit defaults for the new feature flags: Mini-VN + web viewer fallbacks ship **ON**, `enable_compute` stays **ON** so local tooling can discover compute adapters, while narrator/LLM role-mapping, Playground tiers, worldline overlays, depth-from-2D planes, and all external providers remain **OFF** unless operators opt in. Tests and docs now reference the full flag list so contributors update both JSON and prose together.
- Added `tools/doctor_phase8.py`, a headless audit that bootstraps `create_app()`, asserts the battle/props/weather/viewer/narrator/modder/pov surfaces, checks for duplicate routes, verifies WebSocket hooks, and confirms feature defaults. The script emits a JSON report (`"pass": true`) and returns non-zero on regression—wire it into CI before packaging builds.
- Documentation refresh: README (#Doctor Phase 8, feature-flag defaults, compute toggle), `architecture.md` (router dedupe notes), `docs/development_notes.md` + `docs/dev_notes_modder_hooks.md` (Phase 8 debugging guidance), and new `docs/INTEGRATION_REPORT_PHASE8.md` covering the checks, flag diffs, and regression tests executed.

### 2025-12-02 — Playground Tiers, Offline Stage Bundle
- Studio center router now attaches the new **Playground** tab (`comfyvn/gui/central/playground_view.py`) whenever `enable_playground` flips on. Tier-0 parallax and Tier-1 Stage3D snapshots stream `render_config.json` events back into Studio logs through `_handle_playground_snapshot`, wiring Codex A “Add node/Fork” workflows without leaving the UI.
- The WebGL runtime (`comfyvn/playground/stage3d/viewport.html`) now loads vendored Three.js `0.159.0` + `@pixiv/three-vrm@2.0.1` modules from `comfyvn/playground/stage3d/vendor/`, keeping Stage 3D deterministic and offline-friendly. The import map resolves bare specifiers locally; updating versions only requires refreshing the vendor folder.
- Documentation sweep: `docs/PLAYGROUND.md`, `docs/3D_ASSETS.md`, `README.md`, and `architecture_updates.md` describe the Playground tab workflow, feature flags, and bundled runtime assets; `docs/development_notes.md` records the integration/debug hooks for modders.

### 2025-12-01 — Battle Sim v0, Props Manager, Weather Overlays
- Battle engine upgraded (`comfyvn/battle/engine.py`) with the v0 deterministic formula (`base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng`). `/api/battle/resolve` now surfaces `editor_prompt: "Pick winner"`, optional seeded narration, and emits enriched `on_battle_resolved` payloads. `/api/battle/simulate` is gated by new feature flag `enable_battle_sim` (default **OFF**) and returns roll breakdowns + formula metadata; hook `on_battle_simulated` mirrors the new fields. Tests refreshed (`tests/test_battle_engine.py`, `tests/test_battle_routes.py`).
- Props land via `comfyvn/props/{__init__,manager}.py` and `comfyvn/server/routes/props.py`. Feature flag `enable_props` (default **OFF**) gates `/api/props/{anchors,ensure,apply}` with deterministic sidecars, anchor definitions, tween defaults, condition grammar, and `on_prop_applied` modder hook broadcasts. New docs: `docs/PROPS_SPEC.md`, `docs/VISUAL_STYLE_MAPPER.md`.
- Weather planner gains LUT metadata, bake flags, SFX fade-in/out, and a renamed hook `on_weather_changed`. `/api/weather/state` now checks feature flag `enable_weather_overlays` (default **OFF**). Docs (`README.md`, `docs/WEATHER_PROFILES.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`) and tests (`tests/test_weather_routes.py`) updated. Feature defaults added to `comfyvn/config/feature_flags.py`.

### 2025-11-30 — POV Timeline Overlay & Depth Planes
- Worldline lanes now support OFFICIAL⭐/VN Branch🔵/Scratch⚪ tracks with deterministic snapshot metadata. `comfyvn/pov/worldlines.py` gained lane metadata, fork helpers, cache-key builders (`{scene,node,worldline,pov,vars,seed,theme,weather}`), and emits new modder hooks (`on_worldline_created`, `on_snapshot`). FastAPI `comfyvn/server/routes/pov_worlds.py` adds `/api/pov/confirm_switch`, lane-aware upserts, and snapshot payload handling behind feature flag `enable_worldlines`.
- Timeline overlay controllers live under `comfyvn/gui/overlay/{timeline_overlay,snapshot}.py`, stitching snapshots into scrub-ready lanes, wiring Ctrl/⌘-K captures, and invalidating caches when modder hooks fire. Feature flag `enable_timeline_overlay` gates the GUI/API stack; docs capture payloads + modder hook notes in `docs/TIMELINE_OVERLAY.md`.
- Depth-from-2D auto/manual planes land via `comfyvn/visual/depth2d.py` with per-scene toggles persisted to `cache/depth2d_state.json`. Auto mode produces 3–6 evenly distributed planes; manual masks (`data/depth_masks/<scene>.json`) override when scenes flip to manual. Feature flag `enable_depth2d` keeps the pipeline opt-in.
- Documentation sweep: `README.md`, `architecture.md`, `CHANGELOG.md`, `docs/POV_DESIGN.md`, and new developer note `docs/TIMELINE_OVERLAY.md` outline lane colors, snapshot hooks, confirm/fork workflows, and depth mask formats. Modder hook note updated with the new topics.

### 2025-11-29 — Accessibility & Input Profiles
- Accessibility manager (`comfyvn/accessibility/__init__.py`) now persists font scaling, color filters/high-contrast palettes, and subtitle overlays (logs to `logs/accessibility.log`). LUT overlays live in `comfyvn/accessibility/filters.py`; subtitle widgets live in `comfyvn/accessibility/subtitles.py`.
- Input map manager (`comfyvn/accessibility/input_map.py`) centralises keyboard/controller bindings, exposes Qt shortcut/gamepad listeners, and fires new modder hooks (`on_accessibility_input_map`, `on_accessibility_input`). Defaults live in `SettingsManager.DEFAULTS` and can be reset from Settings → Input & Controllers.
- FastAPI exposes `/api/accessibility/{state,filters,subtitle,input-map,input/event}` behind feature flag `enable_accessibility_api` (default **ON**). Feature flags `enable_accessibility_controls` and `enable_controller_profiles` gate the Settings UI + gamepad adapter. VN Viewer subscribes to both managers for live overlays and remapped navigation feedback.
- Structured docs refreshed: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, and new developer note `docs/development/accessibility_input_profiles.md`. Regression smoke: `python -m compileall comfyvn/accessibility` (CI still exercises viewer smoke harnesses).

### 2025-11-25 — Secrets Vault & Sandbox Guard
- Added `comfyvn/security/{secrets_store,sandbox}.py` to keep `config/comfyvn.secrets.json` encrypted at rest (Fernet + rotation helpers) and enforce deny-by-default networking for plugin sandbox runs. Secrets resolve via env overrides (`COMFYVN_SECRET_<PROVIDER>_<FIELD>`) without touching disk, and every read/write/rotation is recorded in `logs/security.log` (configurable through `COMFYVN_SECURITY_LOG_FILE`).
- New FastAPI router `/api/security/*` (feature flag `enable_security_api`) exposes provider summaries, key rotation, audit tailing, and sandbox allowlist checks. Responses stay value-free for dashboards, and a companion helper in `README.md` includes curl samples.
- Sandbox guard honours per-job `network_allow` lists plus `SANDBOX_NETWORK_ALLOW`, publishes `security.sandbox_blocked` audit/Hook events, and can be relaxed via feature flag `enable_security_sandbox_guard`. Modder hook bus now emits `on_security_secret_read`, `on_security_key_rotated`, and `on_sandbox_network_blocked` payloads with timestamps for automation.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, and new `docs/dev_notes_security.md` capture flows, feature flags, and audit paths. Regression coverage added via `tests/test_security_secrets_store.py`, `tests/test_sandbox_network.py`, and `tests/test_security_api.py`.

### 2025-11-24 — Live Collaboration & Presence
- Replaced the legacy collab stub with a Lamport-clock CRDT (`comfyvn/collab/{crdt,room}.py`) that tracks scene fields, nodes, and script lines while deduplicating ops. FastAPI wiring (`server/core/collab.py`, `server/modules/collab_api.py`) exposes `/api/collab/ws` plus REST helpers (`health`, `presence/{scene}`, `snapshot/{scene}`, `history/{scene}`, `flush`) behind feature flag `enable_collaboration` (default **ON**).
- Structured log lines (`collab.op applied ...`) now land in `logs/server.log`, and the modder hook bus broadcasts `on_collab_operation` envelopes matching the WebSocket payloads. Docs include curl samples + debug checklists, and `docs/dev_notes_modder_hooks.md` lists the payload schema.
- Studio gained a reconnecting `CollabClient` (`comfyvn/gui/services/collab_client.py`) and `SceneCollabAdapter` that diff node edits into CRDT ops, updates presence/lock overlays in `TimelineView`, and applies remote snapshots (presence latency <200 ms on LAN).
- Regression coverage: new tests (`tests/test_collab_crdt.py`, `tests/test_collab_api.py`) cover convergence and API contracts; README, architecture docs, `architecture_updates.md`, `docs/development_notes.md`, `docs/dev_notes_modder_hooks.md`, and `docs/DEBUG_SNIPPETS/STUB_DEBUG_BLOCK.md` document usage, endpoints, and verification steps.

### 2025-11-24 — Playtest Harness & Golden Diffs
- Added `comfyvn/qa/playtest/headless_runner.py` and `golden_diff.py` to generate canonical scene traces (with `.trace.json` + `.log` pairs) and compare them in CI; traces capture provenance (`tool_version`, `seed`, `pov`, `workflow`) and deterministic RNG snapshots for every step.
- Mounted `POST /api/playtest/run` behind feature flag `enable_playtest_harness` (default **OFF**). Payload supports `{scene, seed?, pov?, variables?, prompt_packs?, workflow?, persist?, dry_run?}` and returns `{digest, trace, persisted, dry_run, trace_path?, log_path?}`. Dry runs skip disk artefacts, while persisted runs land under `logs/playtest/`.
- Modder hook bus gained `on_playtest_start`, `on_playtest_step`, and `on_playtest_finished`, exposing seed/Pov/history digests so dashboards and webhooks can stream playtest state without polling.
- Added pytest coverage (`tests/test_playtest_headless.py`, `tests/test_playtest_api.py`) plus helper exports via `comfyvn.qa.playtest.compare_traces` for golden suites. Documentation sweep: README, architecture.md, `docs/dev_notes_modder_hooks.md`, and new dev notes (`docs/dev_notes_playtest_harness.md`) outline workflows, curl samples, and debugging checklists.

### 2025-11-20 — Extension Marketplace & Packaging
- Landed `comfyvn/market/{manifest,packaging,service}.py` with a shared manifest schema (metadata, permissions, trust envelopes), deterministic `.cvnext` packaging, catalog ingestion, and install/uninstall orchestration that writes `.market.json` sidecars.
- Mounted `/api/market/{catalog,installed,install,uninstall}` (feature flags `enable_extension_market`, `enable_extension_market_uploads` default **OFF**) plus structured install/uninstall logging (`event=market.install|market.uninstall`) for provenance.
- Added CLI `bin/comfyvn_market_package.py` (`python -m comfyvn.market.packaging`) that normalises manifests, enforces sandbox allowlists (unverified bundles restricted to `/api/extensions/{id}`), and prints SHA-256 digests for reproducibility.
- GUI + catalog refresh: `comfyvn/core/extension_store.py` now sources catalog data via `MarketCatalog`, the Extension Marketplace window shows trust levels, and `config/market_catalog.json` seeds default entries.
- Updated plugin loader to reuse the new manifest validator (`trust_level`, `permissions`, `hooks` now surface via `/api/extensions`), added feature flag defaults, refreshed README/architecture docs, `docs/extension_manifest_guide.md`, and introduced `docs/dev_notes_marketplace.md` with the Debug & Verification checklist.
- Regression coverage: `tests/test_market_manifest.py`, `tests/test_market_service.py`, and `tests/test_market_api.py` cover schema validation, packaging determinism, installer sandboxing, and API flows.

### 2025-10-22 — Policy Enforcer & Audit Timeline
- Introduced `comfyvn/policy/enforcer.py` and `comfyvn/policy/audit.py`, wiring the new feature flag `enable_policy_enforcer` (default `true`) and JSONL persistence under `logs/policy/enforcer.jsonl`.
- FastAPI gained `POST /api/policy/enforce` (returns `{allow, counts, findings, gate, log_path}` and blocks with HTTP 423 on `block`-level findings) plus `GET /api/policy/audit` (time-ordered events, optional JSON export to `logs/policy/policy_audit_<ts>.json`).
- Import/export flows (`import.chat`, `import.manga`, `import.vn`, `export.renpy`, `export.bundle`, `export.scene`) now call the enforcer before writing to disk, ensure provenance embeds findings, and bubble enforcement payloads in responses.
- Modder hook bus broadcasts `on_policy_enforced` envelopes for dashboards and automation; docs capture payload schemas and subscription notes.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/development_notes.md`, `docs/dev_notes_modder_hooks.md`, and new guide `docs/development/policy_enforcer.md`. Regression coverage added via `tests/test_policy_enforcer.py`.

### 2025-11-18 — Cloud Sync & Secrets Vault
- Introduced `comfyvn/sync/cloud/{manifest.py,s3.py,gdrive.py,secrets.py}` with manifest generation, delta diffing, provider adapters, and an AES-GCM encrypted secrets vault (`config/comfyvn.secrets.json`) that rotates timestamped backups under `config/secrets_backups/`.
- Added FastAPI routes `/api/sync/dry-run` and `/api/sync/run`, guarded by feature flags `enable_cloud_sync`, `enable_cloud_sync_s3`, and `enable_cloud_sync_gdrive`. Dry-run responses list planned uploads/deletions; successful runs persist manifests locally (`cache/cloud/<provider>-local.json`) and remotely upload `manifest.json` plus optional tarball snapshots.
- New modder hooks `on_cloud_sync_plan` and `on_cloud_sync_complete` broadcast delta summaries for Studio dashboards and automation bots. Structured logs capture provider, plan counts, snapshot identifiers, and exclude/include overrides while omitting secrets.
- Documentation sweep: README Cloud Sync section, `architecture.md`, `architecture_updates.md`, and `docs/development/dev_notes_cloud_sync.md` outline feature flags, secrets handling, SDK requirements, and curl samples. Regression coverage added via `tests/test_cloud_sync.py`.

### 2025-11-18 — Rating Matrix, SFW Gate & Reviewer Hooks
- Introduced `comfyvn/rating/classifier_stub.py` with a conservative E/T/M/Adult matrix, JSON-backed overrides, and ack tracking. Export manifests now embed `{rating, rating_gate}` payloads, mirroring the `scripts/export_renpy.py` CLI output.
- Added `/api/rating/{matrix,classify,overrides,ack,acks}` with feature flag `enable_rating_api`, issuing ack tokens when SFW mode blocks high-risk prompts or exports. Reviewer overrides persist with timestamps and reasons for audit trails.
- Tightened prompting/export flows: `/api/llm/test-call` and the Ren'Py orchestrator consume the rating gate, emitting HTTP 423 until `/api/rating/ack` records the acknowledgement. CLI parity via `--rating-ack-token/--rating-acknowledged` ensures headless runs respect the same workflow.
- Expanded modder hook coverage (`on_rating_decision`, `on_rating_override`, `on_rating_acknowledged`) behind `enable_rating_modder_stream`, plus logging in `comfyvn.rating` and export/LLM routes for structured diagnostics.
- Documentation sweep: README highlights the new gate, `architecture.md` tracks the milestone, `config/comfyvn.json`/`feature_flags.py` gained rating toggles, and `docs/dev_notes_rating_gate.md` captures API samples, ack flows, and modder hook payloads.

### 2025-11-15 — Steam & itch Export Publish Pipeline
- Shared publish helpers landed at `comfyvn/exporters/publish_common.py`, factoring deterministic ZIP assembly, license manifest extraction, slug helpers, and provenance logging used by the new platform packagers.
- `comfyvn/exporters/steam_packager.py` and `comfyvn/exporters/itch_packager.py` now write reproducible archives with per-platform builds, `publish_manifest.json`, `license_manifest.json`, provenance sidecars, and optional modder hook inventories for contributors.
- FastAPI route `POST /api/export/publish` (gated by feature flags `enable_export_publish`, `enable_export_publish_steam`, `enable_export_publish_itch`) orchestrates Ren'Py exports, honours dry-run previews, emits modder hooks (`on_export_publish_preview`, `on_export_publish_complete`), and records structured entries to `logs/export/publish.log`.
- Documentation sweep refreshed `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, and published `docs/development/export_publish_pipeline.md` with feature flag guidance, curl samples, and manifest/provenance schemas.
- Regression coverage added via `tests/test_publish_packagers.py`, exercising deterministic Steam builds and dry-run Itch packaging.

### 2025-11-14 — Performance Budgets & Profiler Dashboard
- Added `comfyvn/perf/{budgets,profiler}.py` with shared singletons (`budget_manager`, `perf_profiler`) and mounted `/api/perf/*` routes for configuring CPU/VRAM limits, refreshing queue state, managing lazy asset eviction, emitting profiler marks, and retrieving top offenders by time and memory.
- Introduced feature flags `enable_perf_budgets` and `enable_perf_profiler_dashboard` (disabled by default) plus new modder hook envelopes `on_perf_budget_state` and `on_perf_profiler_snapshot` so dashboards and automation scripts can mirror queue transitions, evictions, spans, and dashboard snapshots.
- `/jobs/submit` now reports `status=delayed` when the budget manager defers work; the budget refresh endpoint promotes jobs once resource pressure eases, preventing deadlocks while keeping over-budget workloads queued.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, and the new guide `docs/development/perf_budgets_profiler.md` outline feature flags, REST payloads, curl samples, and modder hook payloads, while the Debug & Verification checklist highlights the new surfaces.
- Regression coverage added via `tests/test_perf_budgets.py` (queue throttling, lazy asset eviction) and `tests/test_perf_profiler.py` (span recording + dashboard aggregation).

### 2025-11-19 — Observability & Privacy Telemetry (A/B)
- Introduced `comfyvn/obs/anonymize.py` (BLAKE2s hashing, anonymised installation ids) and `comfyvn/obs/telemetry.py` (opt-in `TelemetryStore` with feature counters, hook samples, crash digests). Crash reporter now registers reports with the telemetry store when uploads are enabled.
- Added feature flags `enable_privacy_telemetry` and `enable_crash_uploader` (default `false`) plus a persisted `telemetry` block in `config/comfyvn.json` capturing `{telemetry_opt_in, crash_opt_in, diagnostics_opt_in, dry_run}`. API surface `/api/telemetry/{summary,settings,events,features,hooks,crashes,diagnostics}` ships with curl examples and hashed identifiers.
- Modder hook bus forwards every event into telemetry, storing the last five anonymised payload samples per hook; automation can inspect `/api/telemetry/hooks` for coverage without leaking raw asset IDs.
- Diagnostics export (`GET /api/telemetry/diagnostics`) now emits scrubbed zip bundles (`manifest.json`, `telemetry.json`, `crashes.json`); outputs land under `logs/diagnostics/`. Telemetry counters persist to `logs/telemetry/usage.json`, sharing a dry-run friendly format for dashboards.
- Documentation sweep: updated `README.md`, `architecture.md`, `architecture_updates.md`, `docs/development_notes.md`, and `docs/development/observability_debug.md` with privacy guidance, config instructions, and curl samples. Regression coverage landed in `tests/test_observability.py`.

### 2025-11-21 — Diff/Merge & Worldline Graph (A/B)
- Introduced `comfyvn/diffmerge/scene_diff.py` (POV-masked node/choice/asset deltas) and `comfyvn/diffmerge/worldline_graph.py` (timeline graph assembly + fast-forward previews) with dry-run helpers exposed via `preview_worldline_merge`.
- Added feature flag `enable_diffmerge_tools` (default `false`) and mounted `/api/diffmerge/{scene,worldlines/graph,worldlines/merge}` guarded by the flag. Structured logs capture changed-node counts, graph sizes, and merge outcomes; merge previews reuse the existing `merge_worlds` logic without mutating state when `apply=false`.
- Modder hook bus gained `on_worldline_diff` and `on_worldline_merge` so dashboards and CI jobs can track diff/merge activity; payloads include timestamped node deltas, fast-forward flags, and conflict summaries. Docs updated (`README.md`, `architecture.md`, `docs/dev_notes_modder_hooks.md`, new `docs/development/diffmerge_worldline_graph.md`).
- Studio ships a new **Modules → Worldline Graph** dock (`comfyvn/gui/panels/diffmerge_graph_panel.py`) that fetches the graph API, renders 1k-node timelines without freezing, and pipes merge apply/preview buttons into the REST surface while respecting the feature flag.
- Regression coverage added via `tests/test_diffmerge_routes.py` (flag gating, diff payload, graph fast-forward map, conflict refusal) alongside updated worldline merge unit tests.

### 2025-11-13 — Asset Registry Filters & Modder Hook Recipes
- `AssetRegistry.list_assets` now supports hash (`hash_value`), tag (`tags`), and substring (`text`) filters so CLI tools and Studio surfaces can slice registry data without post-processing.
- `/assets` FastAPI route accepts `hash=`, repeated `tags=`/`tag=`, and `q=` query parameters while continuing to return a filtered `total` count for UI consumers.
- Modder hook coverage has been extended: `asset_registered`, `asset_meta_updated`, `asset_sidecar_written`, and `asset_removed` now fan out to `on_asset_registered`, `on_asset_saved`, `on_asset_meta_updated`, `on_asset_sidecar_written`, and `on_asset_removed` with consistent payloads and timestamps.
- Documentation sweep spans README Developer Hooks, `architecture.md`, `architecture_updates.md`, `docs/CHANGEME.md`, `docs/development_notes.md`, `docs/dev_notes_modder_hooks.md`, and the new `docs/development/asset_debug_matrix.md` (curl/WebSocket cookbook for contributors).
- Regression coverage added via `tests/test_asset_registry_filters.py`, which exercises the new filters and verifies modder hook emission when assets are registered, updated, and removed.

### 2025-11-12 — Asset Debug Surfaces & Modder Hooks
- Enriched the Modder Hook Bus with dedicated asset envelopes (`on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, `on_asset_sidecar_written`, plus the legacy `on_asset_saved`) and added `hook_event`/timestamp fields so automation scripts can trace provenance deltas deterministically.
- Added `/assets/debug/{hooks,modder-hooks,history}` alongside `/assets/{uid}/sidecar`, exposing in-process registry listeners, filtered hook specs, recent envelopes, and parsed sidecars without touching the SQLite registry.
- Broadened regression coverage in `tests/test_modder_asset_hooks.py` and `tests/test_assets_provenance_api.py` to confirm hook emission, debug endpoints, and history contents stay stable.
- Documentation sweep: refreshed `README.md`, `architecture.md`, `architecture_updates.md`, `docs/CHANGEME.md`, `docs/dev_notes_asset_registry_hooks.md`, `docs/dev_notes_modder_hooks.md`, `docs/development/modder_asset_debug.md`, `docs/development_notes.md`, and `docs/development/asset_debug_matrix.md` with the new payload fields, curl snippets, and discovery notes.

### 2025-10-21 — Modder Hooks & Debug Integrations (Parts A/B)
- Centralised modder events in `comfyvn/core/modder_hooks.py`, wiring `on_scene_enter`, `on_choice_render`, and `on_asset_saved` into a single bus with plugin host support, WebSocket queues, and persistent history. Scenario Runner and `AssetRegistry` now emit timestamped payloads to the bus with variables/history metadata while keeping asset credentials masked.
- Added FastAPI surface `/api/modder/hooks` (spec + history snapshot), `/api/modder/hooks/webhooks` (signed REST callbacks), `/api/modder/hooks/test`, and the streaming endpoint `ws://<host>/api/modder/hooks/ws`. The server bridge forwards registered events through `comfyvn/server/core/webhooks.py` for outbound POSTs.
- Introduced the Studio **Debug Integrations** panel (`comfyvn/gui/panels/debug_integrations.py`) with System menu entry + auto-refresh, polling `/api/providers/health` and `/api/providers/quota` to render status/usage matrices while displaying masked provider configs and rate limits. Space controller now opens the panel alongside Log Hub when activating the System workspace.
- Documentation sweep: refreshed `README.md`, `architecture.md`, `architecture_updates.md`, `CHANGELOG.md`, `docs/CHANGEME.md`, `docs/dev_notes_modder_hooks.md`, and `docs/development/observability_debug.md`, and logged the work order at `docs/CODEX_STUBS/2025-10-21_MODDER_HOOKS_DEBUG_API_A_B.md`.

### 2025-11-11 — Modder Asset Hook Extensions
- Extended the Modder Hook Bus with `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, and `on_asset_sidecar_written` (alongside the legacy alias `on_asset_saved`) so automation scripts can mirror registry deltas without polling. Payloads now include refreshed sidecar paths, metadata snapshots, and timestamps for easier provenance tracking.
- Asset registry emits the new envelopes whenever metadata is rewritten, sidecars regenerate, or entries are deleted; webhooks, WebSocket subscribers, and dev plugins receive the same payload shape as in-process hooks.
- Added regression test `tests/test_modder_asset_hooks.py` to confirm the new events fire during register/update/remove flows.
- Documentation sweep: refreshed `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, `docs/dev_notes_asset_registry_hooks.md`, `docs/development_notes.md`, and published a dedicated dev note at `docs/development/modder_asset_debug.md`. Checklist links now highlight the log locations (`logs/server.log`) and cURL examples for sampling the REST/WS surfaces.

### 2025-11-12 — Modder Asset Hooks & Prompt Pack Docs
- Asset registry events now emit expanded modder envelopes for metadata updates, removals, and sidecar writes (including asset type + sidecar path) so `/api/modder/hooks` subscribers and `/api/assets/debug/hooks` callers can mirror provenance changes without polling.
- Documentation sweep: refreshed `README.md`, `architecture.md`, `docs/dev_notes_modder_hooks.md`, `docs/dev_notes_asset_registry_hooks.md`, and `docs/development_notes.md` with new WebSocket samples, debug callouts, and feature flag reminders for asset-facing automation.
- Added prompt pack references and source docs under `docs/PROMPT_PACKS/POV_REWRITE.md` and `docs/PROMPT_PACKS/BATTLE_NARRATION.md`, covering system/user templates, guardrails, and router hints for narrative tooling; changelog + docs logs updated for traceability.

### 2025-11-11 — Asset Hooks & Debug Verification Sweep
- Enriched the asset registry hook payloads: `AssetRegistry.ensure_sidecar`, `AssetRegistry._save_asset_meta`, and `AssetRegistry.remove_asset` now emit type, sidecar, metadata, and size snapshots so the Modder Hook Bus forwards `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, and `on_asset_sidecar_written` with consistent context.
- Updated `comfyvn/core/modder_hooks.py` specs (plus REST/WebSocket history) to surface the new fields and keep downstream automation aligned with the asset pipeline.
- Documentation refresh: README (modder hook samples + Debug & Verification checklist), `architecture.md`, `architecture_updates.md`, `docs/dev_notes_asset_registry_hooks.md`, `docs/dev_notes_modder_hooks.md`, and `docs/development_notes.md` now call out the expanded payloads, webhook usage, and PR checklist expectations.

### 2025-11-10 — Asset Registry Filters & Modder Hook Bus
- `AssetRegistry.list_assets` now honours `hash`, `tags`, and substring (`text`) filters, keeping results deterministic and case-insensitive for automation scripts.
- `/assets` FastAPI route accepts `hash=`, repeated `tags=`/`tag=`, and `q=` query parameters; the response continues to return a filtered `total` plus limited items for UI consumers.
- Modder hook bus exposes the full asset lifecycle: `on_asset_registered`, `on_asset_saved` (alias), `on_asset_meta_updated`, `on_asset_sidecar_written`, and `on_asset_removed`, all surfaced through `/api/assets/debug/hooks` and `/api/modder/hooks/ws`.
- Documentation sweep across README, architecture docs, `docs/development_notes.md`, `docs/dev_notes_modder_hooks.md`, and the new `docs/development/asset_debug_matrix.md` ensures modders have curl/WebSocket samples and debugging guidance.
- Regression coverage added via `tests/test_asset_registry_filters.py`, exercising hash/tag/text filters and verifying hook emission for registry events.

### 2025-11-09 — Remote Installer Orchestrator (Parts A/B)
- Shipped `comfyvn/remote/installer.py` with a registry-driven planner, per-host status manifests under `data/remote/install/`, and log writers at `logs/remote/install/`. Module coverage includes ComfyUI, SillyTavern, LM Studio, and Ollama with optional config sync hints so ops can mirror local configs to remote nodes.
- Added FastAPI routes `/api/remote/modules` and `/api/remote/install` (gated by new feature flag `features.enable_remote_installer`, default false) exposing dry-run plans and idempotent install recording. Re-running a completed module returns a noop summary while keeping prior timestamps and notes intact.
- Documentation sweep: refreshed README developer hooks, `architecture.md`, `architecture_updates.md`, `docs/development_notes.md`, and landed codex stub `docs/CODEX_STUBS/2025-10-21_REMOTE_INSTALLER_ORCHESTRATOR_A_B.md` with provisioning guidance and acceptance criteria.
- Regression coverage via `tests/test_remote_installer_api.py` ensures dry-run behaviour, idempotent replays, and flag handling; feature toggle persisted in `config/comfyvn.json` and defaults mirrored in `comfyvn/config/feature_flags.py`.

### 2025-11-09 — Weather Planner & Transition Pipeline (Parts A/B)
- Introduced `comfyvn/weather/engine.py` with canonical presets and deterministic `compile_plan()` outputs (layered backgrounds, light rigs, transitions, particles, SFX) plus `WeatherPlanStore` snapshots (`meta.version`, `meta.updated_at`, stable hash) exposed through `comfyvn/weather/__init__.py` as `WEATHER_PLANNER`.
- Added FastAPI surface `/api/weather/state` (GET/POST) in `comfyvn/server/routes/weather.py`, originally gated by feature flag `enable_weather_planner`; superseded now by `enable_weather_overlays` + `on_weather_changed` but retained for backward compatibility.
- Documentation sweep: refreshed `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, new guide `docs/WEATHER_PROFILES.md`, and codex stub `docs/CODEX_STUBS/2025-10-21_WEATHER_LIGHTING_TRANSITIONS_A_B.md`; feature flag persisted in `config/comfyvn.json`.
- Tests: `tests/test_weather_engine.py` covers presets/aliases/warnings/store versions; `tests/test_weather_routes.py` validates API flow, feature gating, and modder hook emission.

### 2025-11-10 — Public Image & Video APIs (Dry-Run)
- Added dedicated feature flags `enable_public_image_providers` and `enable_public_video_providers`, updated the Settings panel to expose them (keeping `enable_public_image_video` in sync for older tooling), and persisted defaults in `config/comfyvn.json`.
- Implemented dry-run adapters `comfyvn/public_providers/{image_stability,image_fal,video_runway,video_pika,video_luma}.py` plus `/api/providers/{image,video}/{catalog,generate}` in `comfyvn/server/routes/providers_image_video.py`; responses include cost estimates and register lightweight jobs for Studio/CLI debugging.
- Extended provider docs via `docs/dev_notes_public_media_providers.md`, refreshed `README.md` and `architecture.md`, and logged per-request metadata so modders can verify payload shapes without live API keys.

### 2025-11-07 — Public Translation/OCR/Speech Blueprint (Docs)
- Audited the existing translation manager + TM review workflow and documented the upcoming public service adapters (`comfyvn/public_providers/translate_{google,deepl,amazon}.py`, `ocr_{google_vision,aws_rekognition}.py`, `speech_{deepgram,assemblyai}.py`) so teams have a contract before implementation begins.
- Added feature flag guidance (`enable_public_translation_apis`, `enable_public_ocr_apis`, `enable_public_speech_apis`) with defaults set to false in `config/comfyvn.json`, keeping external services opt-in for deployments and automation scripts.
- Specced diagnostics routes `/api/providers/{translate,ocr,speech}/test` including dry-run behaviour, sample responses, and quota metadata expectations; docs emphasise that missing credentials should return informative payloads over hard failures.
- Documentation sweep: refreshed README translation/i18n section, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, `docs/dev_notes_translation_tm_review.md`, and published the dedicated guide `docs/development/public_translation_ocr_speech.md` plus the codex stub `docs/CODEX_STUBS/2025-10-21_PUBLIC_TRANSLATION_OCR_SPEECH_APIS_A_B.md`.

### 2025-11-05 — Theme & World Changer (Parts A/B)
- Introduced `comfyvn/themes/templates.py` with curated presets (Modern, Fantasy, Romantic, Dark, Action) including LUT stacks, ambience assets, music packs, prompt styles, and character role defaults.
- Added `/api/themes/templates` and `/api/themes/apply` FastAPI routes delivering checksum-stable plan deltas (`mutations.assets`, `mutations.luts`, `mutations.music`, `mutations.prompt`, per-character overrides) so Studio previews and automation scripts can diff tone swaps without renders.
- Regression coverage via `tests/test_theme_routes.py` verifies deterministic outputs, override handling, and API wiring; documentation updated across `README.md`, `architecture.md`, `architecture_updates.md`, and new dev note `docs/development/theme_world_changer.md` plus codex stub `docs/CODEX_STUBS/2025-10-21_THEME_WORLD_CHANGER_A_B.md`.

### 2025-11-06 — POV Worldlines & Timeline Tools (Parts A/B)
- Landed `comfyvn/pov/worldlines.py` with a thread-safe worldline registry (id/label/pov/root/notes/metadata) and `comfyvn/pov/timeline_worlds.py` diff/merge helpers so modders can compare or fast-forward POV forks programmatically.
- Added `/api/pov/worlds`, `/api/pov/diff`, and `/api/pov/merge` via `comfyvn/server/routes/pov_worlds.py`; switching worlds updates the shared POV runner, and list/create/switch APIs include metadata + debug payloads for automation.
- `RenPyOrchestrator` now honours `ExportOptions.world_id/world_mode`, embeds the resolved world selection in `export_manifest.json`, and surfaces the data back through CLI/HTTP summaries. `scripts/export_renpy.py` and `/api/export/renpy/preview` expose `--world`/`--world-mode` toggles so exports can pin a canonical world or emit multi-world manifests.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/POV_DESIGN.md`, `docs/dev_notes_modder_hooks.md`, new `docs/development/pov_worldlines.md`, and stub `docs/CODEX_STUBS/2025-10-21_POV_WORLDLINES_TIMELINES_A_B.md`.

### 2025-11-06 — Battle Layer Choice & Simulation (Parts A/B)
- Added `comfyvn/battle/engine.py` with deterministic `resolve()` (stamps `vars.battle_outcome`) and seeded `simulate()` (weighted odds + POV-aware narration) helpers so Studio, CLI, and tests can drive combat branches without editing scenario graphs directly.
- Mounted `comfyvn/server/routes/battle.py` exposing `/api/battle/{resolve,simulate}`; resolve echoes the applied outcome for downstream scripts while simulate returns `{outcome, log[], seed}` payloads that Scenario Runner surfaces in choice overlays before committing to a branch.
- Scenario Runner integrates the new API, showing simulated narration alongside branch odds and persisting deterministic seeds for replay. Debug hooks honour `COMFYVN_LOG_LEVEL=DEBUG` and optional `COMFYVN_BATTLE_SEED` overrides for automation.
- Documentation sweep: updated `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, `docs/development_notes.md`, and published `docs/development/battle_layer_hooks.md` plus CODEX stub `docs/CODEX_STUBS/2025-10-21_BATTLE_LAYER_CHOICE_SIM_A_B.md`.

### 2025-11-08 — Phase 7 Public APIs & Worldlines (Parts A/B)
- Introduced curated public provider catalog endpoints (`/api/providers/{gpu,image-video,translate,llm}/public/catalog`) gated by new feature flags; dry-run RunPod helpers (`/runpod/{health,submit,poll}`) merge secrets from `config/comfyvn.secrets.json` without touching the network.
- Added `comfyvn/public_providers/{catalog,gpu_runpod,video_runway,translate_google}.py` plus `docs/WORKBOARD_PHASE7_POV_APIS.md` to capture pricing anchors, review notes, and modder debug hooks for GPU, image/video, translation/OCR/speech, and LLM services.
- `/api/pov/worlds` now exposes list/create/update/activate verbs so worldline diffs and exports stay scriptable; `/api/battle/plan` returns a deterministic three-phase stub ahead of the full simulator.
- Feature set extended with defaults in `config/comfyvn.json` (`enable_public_gpu|image_video|translate|llm`, `enable_weather`, `enable_battle`, `enable_themes`); `feature_flags.py` reflects the new keys so Studio toggles propagate instantly.
- Documentation sweep: README, architecture.md, POV_DESIGN.md, THEME_TEMPLATES.md, WEATHER_PROFILES.md, BATTLE_DESIGN.md, and LLM_RECOMMENDATIONS.md now include pricing snapshots, review notes, debug/API hooks, and secrets guidance for modders.

### 2025-11-05 — View State Router & Feature Flags (Parts A/B)
- Added `comfyvn/gui/central/center_router.py` and rewired `MainWindow` to use it, persisting the active pane via `session_manager`, defaulting to the VN Viewer whenever a project is open, and surfacing quick actions (Assets/Timeline/Logs) plus an inline narrator overlay when narrator mode is enabled.
- Landed `comfyvn/config/feature_flags.py` and extended the Settings panel’s **Debug & Feature Flags** drawer with switches for `enable_comfy_preview_stream`, `enable_sillytavern_bridge`, and `enable_narrator_mode`; flag changes persist to `config/comfyvn.json` and broadcast through the notifier bus for live consumers.
- Bridge helpers (`world_loader`, `st_sync_manager`, `/st/health`) and `gui/world_ui.py` now gate SillyTavern operations behind the bridge flag, returning `{ "status": "disabled" }` when the connector is off; the VN Viewer honours preview capture toggles immediately.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, and new stub `docs/CODEX_STUBS/2025-10-21_VIEW_STATE_ROUTER_AND_FLAGS_A_B.md` cover the router, flag semantics, and modder-facing debug hooks.

### 2025-11-04 — Viewer Fallbacks, Export Manifests & Golden Suites
- Viewer stack now falls back to web and Mini-VN previews when native embedding fails. `/api/viewer/status` exposes `runtime_mode`, `mini_vn`, and `mini_digest`; helper routes `/api/viewer/web/{token}/{path}` and `/api/viewer/mini/{snapshot,refresh,thumbnail}` expose web bundles and deterministic Mini-VN previews. GUI embeds web fallbacks via Qt WebEngine and renders Mini-VN summaries (scene list + thumbnails). Feature flags `enable_viewer_webmode` and `enable_mini_vn` default to **ON**.
- `MiniVNThumbnailer` emits the new `on_thumbnail_captured` modder hook whenever cached thumbnails regenerate. Documentation refreshed (`docs/VIEWER_README.md`).
- `scripts/export_renpy.py` gained `--bake-weather` (default inherits `enable_export_bake`), emits `on_export_started` / `on_export_completed`, and writes `<out>/label_manifest.json` summarising POV labels plus heuristic battle labels. Dry runs embed the manifest inline. Docs: `docs/EXPORT_RENPY.md`, README notes.
- Golden harness now produces deterministic timestamps and offers `run_per_pov_suite` so every POV records the linear / choice-heavy / battle golden trio. New guide: `docs/GOLDEN_TESTS.md`.

### 2025-11-02 — Ren'Py POV Fork Export (Parts A/B)
- `RenPyOrchestrator` now derives POV routes from timeline + scene metadata, emits per-route labels, and writes manifest `pov` sections with branch listings, switch-menu toggle, and fork references for modders.
- `scripts/export_renpy.py` gained `--pov-mode` and `--no-pov-switch` flags; `publish` now produces per-POV archives alongside the master bundle and surfaces fork manifests/checksums in the JSON summary.
- Documentation sweep: README, architecture.md, architecture_updates.md, and `docs/CODEX_STUBS/2025-10-21_EXPORT_PLAYABLE_POV_FORKS_A_B.md` cover POV fork workflows, debug manifests, and contributor API hooks for branch assets.

### 2025-11-01 — Character Designer Center & Hardened Renders
- Character storage now writes `data/characters/<id>/character.json` plus per-character `lora.json`, keeping legacy flat files mirrored for older tooling; `CharacterManager` normalises tags/avatars/LoRAs and exposes lookup helpers for Studio and automation.
- Added `/api/characters`, `POST /api/characters/save`, and `POST /api/characters/render`; renders run through the hardened ComfyUI bridge, inject saved LoRAs, and auto-register assets (sidecar + thumbnail + provenance) in the `AssetRegistry`.
- Studio main window gained a tabbed center (VN Viewer + Character Designer). The designer surfaces CRUD for name/tags/pose/expression, a LoRA table editor, and one-click portrait/fullbody renders with inline asset feedback.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, and `docs/production_workflows_v0.6.md` now cover the new storage layout, REST contracts, and modder debug hooks.

### 2025-10-30 — Emulation Engine & LLM Registry (chat: Phase 6 Integration)
- Added `comfyvn/emulation/engine.py` with the feature-flagged SillyCompatOffload character emulation runtime, `/api/emulation/*` FastAPI routes, and persisted toggle via `features.silly_compat_offload`.
- Exposed neutral LLM discovery + dry-run routes (`/api/llm/{registry,runtime,test-call}`), populated `comfyvn/models/registry.json` with LM Studio, Ollama, and Anthropic samples, and captured the pending prompt-pack/chat work in `docs/CODEX_STUBS/2025-10-21_PUBLIC_LLM_ROUTER_AND_TOP10_A_B.md`.
- Wired POV + viewer scaffolding: `/api/viewer/status`, `/api/viewer/pane`, and `/api/pov/render/portrait` provide central pane metadata and cached portrait hints for modders.
- Documentation sweep: README Phase 6 wiring, `ARCHITECTURE.md`, `architecture_updates.md`, `docs/LLM_RECOMMENDATIONS.md`, and new `docs/development/emulation_and_llm.md` cover feature flags, prompt packs, adapter tuning, and debug hooks for contributors.

## 2025-10-31 — SillyTavern Compat & Session Sync (Parts A/B)

### 2025-10-22 — Import Processing & Health Debug toggle
- Renamed the Studio “Imports” view, dock, and menu entries to **Import Processing** so the label reflects the broader job aggregator role (VN chat, roleplay, persona runs). Updated Studio docs and user guides accordingly.
- Refined the SillyTavern bridge surface: `/st/import` now responds to `OPTIONS` preflight requests and keeps status polling gated by `features.enable_st_importer`, aligning with the extension’s browser calls.
- Added a `debug_health_checks` feature flag. When enabled, Studio logs every health probe and surfaces verbose details; when disabled (default) the UI still reports failure causes without spamming logs.
- Import Manager, Tools Installer, and Ren'Py Exporter panels inherited a “Load From File…” picker so preset payloads can be populated directly from disk before sending REST requests.
- `comfyvn/bridge/st_bridge/extension_sync.collect_extension_status` now records plugin bundle/destination manifests, reports `plugin_needs_sync`, and retains the historical extension fields so existing automation keeps working. Watch paths now include plugin package files to surface missing installs.
- `comfyvn/bridge/st_bridge/health.probe_health` merges ping status with the new version summaries (`versions.extension`, `versions.plugin`), emits `alerts` on manifest mismatches, and downgrades the overall status to `degraded` when bundle ↔ install versions diverge.
- Added `comfyvn/bridge/st_bridge/session_sync.py` plus the `POST /st/session/sync` API. The endpoint accepts VN scene/P OV/variable context, trims transcripts, forwards the payload to comfyvn-data-exporter, and returns a panel-ready reply (`panel_reply`, `reply_text`) with measured latency. Dry-run mode keeps modder tooling from requiring a live SillyTavern instance.
- Documentation sweep: updated `README.md`, `architecture.md`, `architecture_updates.md`, `docs/dev_notes_modder_hooks.md`, and added `docs/CODEX_STUBS/2025-10-21_SILLY_COMPAT_AND_SESSION_SYNC_A_B.md` outlining payload schemas, alerts, and modder hooks.

### 2025-10-21 — Chat & Narrator Mode (Parts A/B)
- Added `comfyvn/gui/central/chat_panel.py` and wired it into the Studio main window (Modules → **VN Chat**). The dock mirrors SceneStore dialogue, exposes quick narrator autoplay, and posts prompts to the LLM proxy without blocking the viewer workspace.
- The `/api/llm/chat` proxy is still pending; current builds rely on `/api/llm/test-call` for smoke tests while adapters and presets live in the registry.
- `comfyvn/bridge/st_bridge/session_sync.collect_session_context` and `load_scene_dialogue` provide lightweight context payloads for tooling; `SillyTavernBridge.get_active()` wraps the comfyvn-data-exporter `/active` endpoint so prompts can stay in sync with the live SillyTavern session.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, and new stub `docs/CODEX_STUBS/2025-10-21_CHAT_AND_NARRATOR_MODE_A_B.md` outline the chat panel workflow, API response shape, and modder-facing debug hooks.

## 2025-10-21 — Phase 6 stubs (POV & Viewer)
- pov: manager + routes; runner supports perspective filters
- viewer: default center pane with Ren'Py start/status
- designer: character editor + render hook
- chat/llm: VN chat panel + LLM proxy registry (adapters scaffold)
- st-bridge: session sync stub
- export: POV-aware Ren'Py orchestration plan
- docs: POV_DESIGN, VIEWER_README, LLM_RECOMMENDATIONS; workboard

### 2025-10-30 — POV Render Pipeline & LoRA (Parts A/B)
- Landed `comfyvn/pov/render_pipeline.py`, a hardened-bridge orchestrator that fills missing portraits on POV changes, caches renders by `(character, style, pose)`, and mirrors ComfyUI sidecars alongside registered assets.
- `/api/pov/render/switch` now wraps POV state changes, reusing cached renders when available and exposing workflow/LoRA metadata so GUI panels and automation scripts can diff provenance deterministically.
- Asset registry metadata for pipeline renders includes `workflow_id`, `prompt_id`, and applied LoRA payloads; original ComfyUI sidecars are copied as `<pose>.png.bridge.json` next to the asset for modder tooling.
- Added `HardenedComfyBridge.character_loras()` helper plus coverage in `tests/test_pov_render_pipeline.py` to enforce cache hits/misses and force re-render behaviour without a live ComfyUI instance.

### 2025-10-29 — LLM Model Registry & Adapters (chat: LLM Model Registry & Adapters A/B)
- Seeded a provider-neutral registry (`comfyvn/models/registry.json`) with tag-aware model listings, environment overrides, and defaults for `chat`, `translate`, `worldbuild`, `json`, and `long-context` use cases.
- Introduced adapter base classes plus OpenAI-compatible, LM Studio, Ollama, and Anthropic-compatible implementations under `comfyvn/models/adapters/`, exposing consistent `ChatResult` payloads and error handling.
- Added `/api/llm/registry` plus runtime helpers so Studio tooling and modder scripts can enumerate providers or inject temporary adapters while the `/api/llm/chat` proxy remains under development.
- Documentation sweep: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/development_notes.md`, `docs/dev_notes_modder_hooks.md`, and the new `docs/LLM_RECOMMENDATIONS.md` outline adapter wiring, env overrides, debug hooks, and per-module parameter guidance.

### 2025-10-30 — Scenario Debug Deck & Viewer Controls (chat: Docs Hooks Debug Panels A/B)
- Studio `TimelineView` now bundles the node editor, multi-track timeline, and the new Scenario Runner dock. The runner consumes `/api/scenario/run/step`, syncs scenes from the editor, tracks POV/seed/variable state, supports breakpoints, and mirrors the live node focus back into the editor.
- Introduced `comfyvn/pov/` with `POVManager` plus REST endpoints `GET /api/pov/get`, `POST /api/pov/set`, `POST /api/pov/fork`, and `POST /api/pov/candidates`, providing deterministic POV snapshots and save-slot helpers for modders. Reference contract captured in `docs/POV_DESIGN.md`.
- Added viewer service endpoints `POST /api/viewer/start`, `POST /api/viewer/stop`, and `GET /api/viewer/status` to launch Ren’Py (or a Tk stub when no runtime is configured). Env overrides (`COMFYVN_RENPY_PROJECT_DIR`, `COMFYVN_RENPY_EXECUTABLE`, `COMFYVN_RENPY_SDK`) and payload knobs are documented in `docs/VIEWER_README.md`; logs stream to `logs/viewer/renpy_viewer.log`.
- Studio’s **Log Hub** dock tails the primary runtime logs for quick debugging, while **Settings → Debug & Feature Flags** exposes the persisted `enable_comfy_bridge_hardening` switch for the hardened ComfyUI adapter pipeline.
- Documentation sweep: README.md, ARCHITECTURE.md, `architecture_updates.md`, and `docs/CHANGEME.md` now highlight the Scenario Runner deck, POV/viewer routes, environment flags, and contributor guidance for debug tooling.

### 2025-10-29 — Scheduler, Costs, & Telemetry Board (chat: Scheduler Costs Telemetry A/B)
- Added `comfyvn/compute/scheduler.py`, a dual local/remote queue with FIFO ordering, priority pre-emption, sticky-device affinity, and provider-aware cost estimation (`duration_sec`, `bytes_tx/rx`, VRAM minutes).
- `/api/schedule/*` routes expose enqueue/claim/complete/fail/requeue plus health, state, and board snapshots so automation and mod tooling can monitor throughput or drive custom workers.
- Studio ships a dockable **Scheduler Board** (`Panels → Scheduler Board`) rendering the board snapshot as a Gantt chart with live refresh, highlighting queue, device, duration, and cost per job.
- Provider metadata (`cost_per_minute`, `egress_cost_per_gb`, `vram_cost_per_gb_minute`) now influence estimated costs, ensuring modders can model remote spend before dispatching large batches.
- Documentation sweep: README, ARCHITECTURE, and `docs/development_notes.md` outline scheduler APIs, telemetry fields, and debug hooks for contributors instrumenting custom workers or asset pipelines.

### 2025-10-29 — Observability Stack & Scenario Contract (chat: Project Integration)
- Introduced `comfyvn/obs/structlog_adapter.py` and `comfyvn/obs/crash_reporter.py`, wiring the structured logger + crash reporter into FastAPI bootstrap so unexpected exceptions emit JSON dumps under `logs/crash/`.
- Added `tools/doctor_phase4.py` to probe `/health`, simulate crash reports, and confirm structured logging; designed for both local troubleshooting and CI smoke jobs.
- Landed `tests/e2e/test_scenario_flow.py` with golden payloads in `tests/e2e/golden/phase4_payloads.json`, covering `/api/scenario`, `/api/save`, `/api/presentation/plan`, and `/api/export/*`.
- Documentation sweep: README, ARCHITECTURE, `docs/development/observability_debug.md`, and `docs/CHANGEME.md` now reference the observability tooling and modder-facing API hooks.

## [v0.7.0-studio] — 2025-10-27 (release prep)
- Advisory: gate + scan + provenance stamping.
- Legal reminder: policy gate keeps creators in control while requiring an explicit acknowledgement that they accept all liability for exported/imported content.
- Studio shell unified under `gui/main_window` with dockable Scenes, Characters, and Timeline editors backed by registry APIs, live job dashboards, and remote compute telemetry. Menus, bridge wiring, and settings persistence now align with launcher defaults.
- Import infrastructure hardened: roleplay importer jobs, VN package importer, advisory scans, provenance stamping, and Studio dashboards all line up; Manga importer parity remains in-flight and is tracked as a release blocker.
- Audio and advisory systems upgraded: TTS + music remix endpoints share cache + provenance scaffolding, policy gate/filter workflows enforce acknowledgements, and GUI surfaces warnings; ComfyUI linkage + asset inspector integration are the last audio/asset release blockers.
- Extension loader landed: `comfyvn/plugins/loader.py` validates per-extension manifests, auto-mounts REST routes/UI assets, and exposes `/api/extensions/*` management; Studio now renders enabled panels inside the Extensions card, shipping with `extensions/sample_hello` as a reference implementation.
- Runtime/storage + packaging docs updated: runtime paths redirected to OS-specific locations, provider templates curated, Doctor v0.7 script landed, and release coordination lives in `ARCHITECTURE.md`, `CHAT_WORK_ORDERS.md`, and `docs/CHANGEME.md`. Packaging rehearsal (wheel + PyInstaller/AppImage) to run once P0 blockers clear.
- Known gaps before tagging: Studio asset inspector UX, audio provenance hand-off to `AssetRegistry`, Manga importer panel parity, Ren'Py lint integration (log capture + surfacing), and advisory auto-remediation events. These are noted in the release checklist and will remain in the changelog until resolved.

### 2025-10-28 — Asset Gallery & Sidecar Enforcement (chat: Asset Registry Gallery Enforcer)
- Landed the dockable `AssetGalleryPanel` with type/tag/license filters, async thumbnail loading, bulk tag/license editing, and a clipboard-friendly debug JSON exporter for modders (`comfyvn/gui/panels/asset_gallery.py`). The panel auto-refreshes via new registry events and ships in the Panels menu by default.
- `AssetRegistry` now exposes hook registration APIs (`add_hook`, `remove_hook`, `iter_hooks`) and emits events when assets are registered, updated, removed, or sidecars are rewritten. These hooks power live UI refreshes and give modders deterministic attachment points for provenance scripts and automation.
- Registry rebuild CLI (`comfyvn/registry/rebuild.py`) gained `--enforce-sidecars`, `--overwrite-sidecars`, `--fix-metadata`, and `--metadata-report` flags plus the shared `audit_sidecars()` helper. The summary integrates with new docs so teams can track fix-up progress.
- Introduced `tools/assets_enforcer.py` for standalone sidecar audits. It supports dry-run/report modes, JSON output, and optional tag/license backfills sourced from file paths—ideal for CI jobs and contributor tooling.
- Documentation sweep: README, ARCHITECTURE, and new `docs/dev_notes_asset_registry_hooks.md` outline gallery usage, hook semantics, and extension tips. CHANGELOG now references the modder-facing updates.

### 2025-10-27 — Ren'Py Orchestrator & Publish Preset (chat: Export/Packaging)
- Added `comfyvn/exporters/renpy_orchestrator.py`, consolidating scene graph assembly, asset staging, manifest generation, and deterministic publish zips.
- Rebuilt `scripts/export_renpy.py` with dry-run diffs, per-scene module toggles, and optional Ren'Py SDK invocation so pipelines can preview changes before writing to disk.
- Introduced `GET /api/export/renpy/preview` to expose the orchestrator dry-run output to Studio and tooling bots; documentation now points modders to `docs/development_notes.md` for asset APIs and debugging hooks.

### 2025-10-27 — Manga Pipeline Production (chat: Manga Pipeline)
- Replaced the in-memory manga pipeline stub with a production executor that stages jobs under `/data/manga/<job_id>/{raw,ocr,group,scenes,logs}`, tracks state transitions, and persists `manifest.json` snapshots for Studio dashboards.
- Added a provider registry (`comfyvn/manga/providers.py`) with segmentation, OCR/I2T, grouping, and speaker attribution handlers including ComfyUI workflow integration, local Tesseract/EasyOCR, and cloud connectors for Azure Vision, Google Vision, and OpenAI dialogue attribution.
- `/manga/pipeline/start` now accepts source paths, provider overrides, and per-provider settings; `/manga/pipeline/providers` lists available services with paid/open-source tags, and status responses stream stage metadata plus artifact pointers.
- Settings scaffolding surfaces configurable endpoints (base URLs, workflows, API keys) so deployments can wire ComfyUI or cloud OCR providers without code changes.

### 2025-10-27 — Localization Manager & Modding Docs (chat: Translation Manager)
- Landed `comfyvn/translation/manager.py` with shared `t()` helper, config-backed active/fallback languages, and identity batch stub at `/api/translate/batch`.
- Added `/api/i18n/lang` GET/POST routes so Studio and automation tooling can switch locales live and persist selections to `config/comfyvn.json`.
- Published modder-focused notes in `docs/development_notes.md`, covering asset REST hooks, debug toggles, and locale override workflows; README/ARCHITECTURE updated to reference the new subsystem.

### 2025-10-27 — Plugin Loader & Sample Extension (chat: Plugin Runtime)
- Introduced `comfyvn/plugins/loader.py`, a manifest-driven loader that validates extension metadata, mounts safe HTTP routes, registers event hooks, and exposes UI panels for Studio via `/api/extensions/*`.
- Added `comfyvn/server/routes/plugins.py` so administrators can list, enable, disable, and reload extensions without restarts while serving static panel assets with FastAPI.
- Studio now renders enabled panels in the new Extensions card by consuming `/api/extensions/ui/panels`; reference implementation `extensions/sample_hello` demonstrates a global `/hello` endpoint and a module-script panel mounting helper.
- Documentation refreshed (`ARCHITECTURE.md`, `README.md`, `docs/development/plugins_and_assets.md`) to guide modders through manifest schema, debugging, and available REST hooks for asset-centric automation.

### 2025-10-27 — Advisory Scanner Plugins & Studio Gate (chat: Advisory Scanner)
- Refactored `comfyvn/advisory/scanner.py` into a plugin host shipping SPDX, IP keyword, and optional NSFW classifier heuristics; findings now normalise to the `info|warn|block` levels consumed by CLI exports and Studio pre-flight panels.
- Updated the Studio Advisory panel with explicit acknowledgement copy, action-aware filtering (export vs import), and reminder text that creators retain freedom while accepting legal responsibility for their output.
- Added `docs/development/advisory_modding.md` detailing legal expectations, debug knobs, API routes, and plugin extension patterns for contributors building custom scanners or asset automation.

### 2025-10-27 — SillyTavern Bridge Live Sync (chat: Bridge Integration)
- Introduced `comfyvn/bridge/st_bridge/extension_sync.collect_extension_status` to surface manifest parity, plugin bundles, and watch-path resolutions; `/st/health` now reports those diagnostics alongside base plugin pings.
- Added `/st/extension/sync` endpoint supporting `dry_run` preview mode before copying the bundled extension into a detected SillyTavern install. Environment overrides (`COMFYVN_ST_EXTENSIONS_DIR`, `SILLYTAVERN_PATH`) and settings hints now flow through responses for tooling.
- Implemented REST import handling under `/st/import`: `worlds` persist via `WorldLoader.save_world`, `personas` hydrate the asset registry through the new `SillyPersonaImporter`, `characters` upsert into `CharacterManager`, and `chats` convert into SceneStore entries for Studio previews.
- Documentation refresh: README developer hook section references bridge APIs, `architecture.md` highlights the integration, and `docs/dev_notes_modder_hooks.md` provides copy-paste payload examples for contributors.

### 2025-10-26 — Studio Views & Audio Lab Stubs (chat: Project Integration)
- Added read-only Scenes, Characters, and Timeline inspectors under `comfyvn/gui/views/{scenes,characters,timeline}_view.py`, wiring them to `/api/{scenes,characters,timelines}` via `ServerBridge` with graceful mock fallbacks. The Studio navigation now embeds these widgets to avoid panel duplication and enables JSON inspectors for quick payload checks.
- Introduced lightweight audio adapters: `comfyvn/bridge/tts_adapter.py` caches synthetic TTS clips (deterministic WAV + provenance sidecar) and `comfyvn/bridge/music_adapter.py` logs remix intents. FastAPI routes at `/api/tts/speak` and `/api/music/remix` expose the stubs for GUI use.
- Updated `comfyvn.json` with `audio.tts_enabled`, `audio.tts_model`, and `audio.music_enabled` hints so deployments know how to toggle the new lab features.

### 2025-10-25 — Asset & Sprite System (chat: Assets)
- `AssetRegistry` now honours configurable asset roots, writes `<filename>.asset.json` sidecars alongside media files (while mirroring legacy `_meta` paths), and schedules thumbnails or WAV waveform previews during registration.
- Pose tooling (`comfyvn/assets/pose_manager.py`, `playground_manager.py`) now integrates with the registry so newly saved poses write JSON payloads, emit sidecars, and appear in registry queries.
- Added `tools/rebuild_asset_registry.py` to scan `assets/`, dedupe by file hash, regenerate sidecars, and prune stale registry rows; pairs with documentation updates in `docs/studio_assets.md`.

### 2025-10-24 — Roleplay Importer Hardened (chat: Roleplay/World Lore)
- `/roleplay/import` now accepts multipart uploads with filename sanitisation, runs advisory scans for missing content ratings or licenses, and emits preview + status artefacts under `data/roleplay/{raw,converted,preview}`.
- Added `/roleplay/imports/status/{id}` plus richer `/roleplay/preview/{id}` responses so Studio panels can poll job progress, advisory flags, persona hints, and ready-to-display excerpts.
- Persona hints and participant metadata feed new character trait updates; preview assets and status files register in the asset ledger to keep Scenes + Characters synchronised after corrections or LLM samples.

### 2025-10-23 — Audio Remix & Policy Gate (chat: Audio & Policy)
- TTS and music remix pipelines now submit templated workflows to ComfyUI when available, automatically falling back to deterministic synthetic generation if the server or workflow is missing.
- Introduced `comfyvn/core/audio_cache.py` and upgraded the TTS pipeline to emit deterministic WAV voice lines with cache-backed dedupe and structured provenance sidecars.
- Added `/api/music/remix` FastAPI endpoint backed by `comfyvn/core/music_remix.py`, generating cached remix WAVs plus JSON metadata in `exports/music/`.
- Settings panel gained dedicated TTS and Music sections listing open-source, freemium, and paid providers (ComfyUI, Bark, Coqui XTTS, ElevenLabs, Azure Speech, AudioCraft, Suno, Soundraw, AIVA) with editable ComfyUI connection fields.
- Delivered liability gate + filter controls via `/api/policy/{status,ack,evaluate,filters,filter-preview}`, ensuring legal warnings surface while preserving user choice.
- Content filter modes (`sfw|warn|unrestricted`) route through `comfyvn/core/content_filter.py`, log advisory warnings, and expose preview responses for GUI panels.
- Documentation updates: refreshed `docs/studio_phase6_audio.md`, `docs/studio_phase7_advisory.md`, and `architecture.md` with new API hooks and debugging steps.
- GUI: Audio panel now surfaces style/lang/model inputs, cache hits, and music remix requests; Advisory panel provides policy acknowledgement, filter mode controls, and preview tooling.
- Logging: dedicated `logs/audio.log` and `logs/advisory.log` streams capture subsystem diagnostics without overflowing `logs/server.log`.
- Added `docs/comfyui_music_workflow.md` describing recommended ComfyUI module installs and remix workflow configuration for production pipelines.

### 2025-10-23 — Extension Manifest Refresh (chat: Studio Ops)
- Each bundled extension now ships an `extension.json` manifest; the Studio reads these files (or falls back to single-file modules) to surface metadata.
- The Extensions menu auto-discovers packages, grouping official items separately from imported/community add‑ons and exposing an info dialog with hooks and file locations.
- Documentation (`docs/v1_extension_api.md`, `docs/extensions.md`) updated to describe the new manifest workflow for developers.
- Settings panel gained local-backend port controls with an integrated port scanner to help avoid clashes before relaunching the embedded server.

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
- `/vn/tools/*` endpoints register external extractors (e.g., arc_unpacker) with regional legality warnings; importer adapts to `.arc/.xp3` packages and records extractor provenance.
- Extension: `tool_installer` surfaces installer documentation through the modular loader; GUI hook pending via `docs/tool_installers.md`.
- Documentation: Added `docs/importer_engine_matrix.md` and `docs/remote_gpu_services.md` to share engine signatures and remote GPU onboarding guidance with other chats.
- Introduced importer scaffolding (`comfyvn/importers/*`, `core/normalizer.py`, `bin/comfyvn_import.py`) with detection heuristics for major VN engines and comfyvn-pack normalization.
- `/vn/tools/install` now ships a catalog of 20 popular extractors (Light.vnTools mirrors, GARbro, KrkrExtract, XP3 tools, CatSystem2/BGI/RealLive utilities, Unity asset rippers) with explicit license warnings and auto-registration.
- Compute advisor now emits recommendations via `/api/gpu/advise`, weighing local VRAM against curated remote providers (RunPod, Vast.ai, Lambda, AWS, Azure, Paperspace, unRAID).
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
- Studio `RoleplayImportView` upgraded into a live job dashboard with auto-refresh + log viewer, wired to the new endpoints.
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
### 2025-11-14 — Remote Installer SSH Runtime & Vault Hardening
- Remote installer now runs idempotent SSH commands via `InstallRuntime`, probes sentinel files before execution, and records `installed/skipped/failed` states in `data/remote/install/<host>.json`. Config sync uploads skip existing destinations to avoid clobbering remote tweaks.
- `/api/remote/install` accepts `secrets` + `ssh` blocks, merging encrypted credentials from `config/comfyvn.secrets.json`; new `/api/remote/status` endpoint streams per-host manifests or an index of known hosts.
- Added module detection metadata (`detect_steps`) so replays register as `noop` once remote sentinels exist, even if local status was purged.
- Hardened the secrets vault: key and payload files default to `0600` permissions, audit logging stayed value-free, and documentation now covers bootstrap, overrides, and remote installer payload schemas.
- Documentation sweep: updated `README.md`, `CHANGELOG.md`, published `docs/REMOTE_INSTALLER.md` and `docs/SECURITY_SECRETS.md` with curl flows, supported OS notes, rollback steps, and secrets layout guidance.
### 2025-12-11 — Marketplace Manifest & Router Hardening
- Manifest schema (`comfyvn/market/manifest.py`) now normalises singular `author` fields, enriches contribution summaries (permissions, routes, events, UI panels, hooks, diagnostics), and records optional `trust.signature` digests/algorithms. New permission scopes cover asset events/debug and lifecycle subscriptions so catalog entries accurately declare intent.
- Packaging (`comfyvn/market/packaging.py`) writes fully deterministic `.cvnext` archives (fixed timestamps/permissions) and verifies manifest SHA-256 digests when `trust.signature` is supplied, surfacing both package + manifest hashes in the build result.
- FastAPI router `comfyvn/server/routes/market.py` replaces the legacy catalog/installed surfaces with `/api/market/list` (catalog + installed state, permission glossary, modder hook catalogue) and `/api/market/health` (trust breakdown + last error) while keeping install/uninstall flows consistent and feature-gated via `enable_marketplace`.
- Documentation sweep: fresh `docs/MARKETPLACE.md` walks manifest fields, trust levels, signature policy, sandbox rules, debug hooks, and curl examples; `README.md`, `architecture.md`, and `docs/dev_notes_marketplace.md` reference the new endpoints, flags, and verification checklist.

### 2025-10-22 — Live Sweep: docks/menu/import/ST
- Fix `QMainWindow::saveState()` warnings by assigning `objectName` to all docks before save/restore.
- Docks now closable/movable/floatable with right-click "Close / Move to Dock X".
- Quick Access toolbar disabled by default (feature flag `enable_quick_toolbar`).
- Tools → Import submenu (From File, SillyTavern Chat, Persona JSON, Lore JSON, FA upload, Roleplay txt/json).
- Settings exposes SillyTavern host/port/base; bridge honors these.
- Help menu opens Import Guide, ST Bridge, Legal & Liability, Docking & Layout.
