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
- Added FastAPI surface `/api/weather/state` (GET/POST) in `comfyvn/server/routes/weather.py`, gated by feature flag `enable_weather_planner`, logging structured updates (`hash`, `exposure_shift`, `particle`) and emitting `on_weather_plan` over the modder hook bus so automation scripts can enqueue renders.
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
