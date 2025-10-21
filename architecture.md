ComfyVN — ARCHITECTURE.md

Studio Architecture & Delivery Plan (Phased)
Document version: 0.7-architecture • Scope: repo-wide guidance for all chats/teams

0) Purpose

This document is the single source of truth for how ComfyVN is structured and delivered. It divides work into Phases and Parts (e.g., “Phase 3, Part B”), so each chat/team can execute independently without stepping on others. Each Part includes Owner, Inputs, Outputs, Acceptance, and Notes/Risks.

1) Guiding principles

Studio-first: A single, integrated desktop “studio” with views for Scenes, Characters, Assets, Imports, Compute, Audio, Advisory, Export, and Logs.

Remixable by design: Anything imported (chats, VN packs, manga) is editable, remixable, and exportable.

Safety & provenance: Liability gate, licensing/advisory scans, and embedded provenance by default.

Scalable compute: Local CPU/GPU plus optional remote GPU providers, with a compute advisor and policy.

Determinism where it matters: Seeded RNG for branching playback and test replays.

SQLite first, Postgres later: Local-first development with clean migrations.

2) Baseline repo layout (target)
comfyvn/
  app.py
  logging_config.py
  core/
    db_manager.py
    gpu_manager.py
    file_importer.py
    translation_manager.py
    rng.py
    settings_manager.py
    system_monitor.py
  server/
    modules/
      system_api.py
      scenes_api.py
      characters_api.py
      timelines_api.py
      vars_api.py
      templates_api.py
      assets_api.py
      advisory_api.py
      import_api.py
      gpu_api.py
      translation_api.py
      roleplay/
        roleplay_api.py
  gui/
    main_window/  (primary shell for v0.8)
      main_window.py
      menu_bar.py
      ...
    studio_window.py  (prototype shell; secondary)
    server_bridge.py
    views/
      home_view.py
      scenes_view.py
      characters_view.py
      timeline_view.py
      assets_view.py
      imports_view.py
      compute_view.py
      audio_view.py
      advisory_view.py
      export_view.py
      logs_view.py
scripts/
  install_manager.py
  run_comfyvn.py
setup/
  apply_phase06_rebuild.py
data/
  templates/
  worlds/
  imported_vn/
  imported_manga/
assets/
logs/
exports/
renpy_project/

Important: Only templates and example assets belong in Git. User data (imports, generated assets, cache, logs) must be git-ignored.  
`renpy_project/` is a reference-only Ren'Py sample used for renderer/export validation; keep it pristine (copy assets out before editing, never write saves/build artefacts back into the repo).

3) Phase plan (Studio-style delivery)
Phase 1 — Core stabilization

Part A — Server health & bootstrap

Owner: Server Core Production Chat

Inputs: comfyvn/app.py, logging_config.py

Outputs:

~~create_app() factory with ordered router includes~~ ✅ 2025-10-20

~~Endpoints: GET /health, GET /status~~ ✅ 2025-10-20

~~CORS enabled; logs to ./logs/server.log~~ ✅ 2025-10-20

Acceptance: ~~curl /health returns {status:"ok"}; /status lists routes and version.~~ ✅ Verified 2025-10-20

Notes: Ensure python-multipart in requirements.  
2025-10-21 — Launcher (`run_comfyvn.py`) derives the default port from `COMFYVN_SERVER_PORT` or the shared settings file (`data/settings/config.json`) and writes the resolved value back to the environment so the GUI and backend stay aligned across restarts.

Part B — GUI shell & metrics

Owner: GUI Code Production (Studio)

Inputs: gui/studio_window.py (or main_window.py if transitional)

Outputs:

~~Menubar build guard (no duplication on reload)~~ ✅ 2025-10-20

~~ServerBridge: set_host(), save_settings()~~ ✅ 2025-10-20

~~Metrics polling from /system/metrics (CPU/RAM/GPU)~~ ✅ 2025-10-20

Acceptance: ~~Health indicator green, graphs update 2–5s, no duplicate menus.~~ ✅ Verified 2025-10-20

Notes: Disable embedded server until single-instance guard is verified. For v0.8, the primary Studio shell remains `gui/main_window/*`; `gui/studio_window.py` is a prototype using `/api/studio/*` and may be merged later.

Part C — Logging & config normalization

Owner: Project Integration Chat

Outputs: ~~All logs under ./logs/ (gui.log, server.log, launcher.log).~~ ✅ 2025-10-20

Acceptance: ~~Re-run writes to the same files; log rotation policy documented.~~ ✅ Logging normalized 2025-10-20

Phase 1 — Stability follow-ups (next)
- ~~Silence the Pydantic field warning by renaming `RegisterAssetRequest.copy`.~~ ✅ 2025-10-23 — Boolean renamed to `copy_file` (alias `copy`) inside `comfyvn/server/modules/assets_api.py`, removing the Pydantic shadow warning without breaking the API.
- ~~Add regression coverage for `/settings/save` to confirm deep-merge semantics on the shared settings file.~~ ✅ 2025-10-23 — `tests/test_settings_api.py::test_settings_save_deep_merge` patches the settings manager and verifies nested keys survive incremental saves.
- ~~Track launcher/settings alignment via a smoke test that exercises `run_comfyvn.py --server-only` and probes `/health` + `/status`.~~ ✅ 2025-10-23 — `tests/test_launcher_smoke.py` parses launcher arguments, applies the environment, boots uvicorn, and polls both endpoints.
- Document the port-resolution pathway and environment overrides in public-facing docs (owner: Project Integration) — README updated 2025-10-21; keep parity in future release notes.

Phase 2 — Data layer & registries (v0.6 baseline)

Part A — DB migrations v0.6

Owner: v0.5 Scaffold & DB Chat

Outputs (tables):

~~scenes, characters, timelines, variables, templates~~ ✅ 2025-10-20

~~assets_registry, provenance, thumbnails~~ ✅ 2025-10-20

~~imports, jobs, providers, translations, settings~~ ✅ 2025-10-20

Acceptance: ~~Migration script creates/updates schema idempotently; apply_phase06_rebuild.py passes.~~ ✅ Verified 2025-10-20

Notes: Store large assets on disk with JSON sidecars; registry row contains hash + pointers.

Part B — Asset registry & sidecars

Owner: Asset & Sprite System

Outputs:

data/assets/{characters,backgrounds,music,voices}/

Sidecars: asset.json per heavy asset; thumbnails to cache/thumbs.

Registry routines: add/list/get by hash/uid; provenance hooks.

Acceptance: Importing any asset yields a registry row + thumbnail + sidecar.

Status:
- ~~Registry copy/hash/sidecar helpers available via `AssetRegistry.register_file`.~~ ✅ 2025-10-20
- ✅ 2025-10-21 — Thumbnail generation now runs on a background worker, keeping large image imports from blocking the registration path while still updating the registry once the thumb is ready.
- ✅ 2025-10-21 — `/assets` router now fronts the registry (list/detail/upload/register/delete), ensuring metadata sidecars + thumbnails stay in sync and logging uploads to aid debugging.
- ✅ 2025-10-21 — Provenance ledger + PNG metadata stamp in place; asset sidecars include provenance id/source/workflow hash.

Part C — Provenance & licensing

Owner: Advisory/Policy Chat

Outputs:

Provenance stamps in EXIF (images/audio) + DB ledger row

License tagging in assets_registry.meta

Acceptance: Exported asset carries minimal embedded stamp; provenance manifest available per asset.

Status:
- ✅ 2025-10-21 — AssetRegistry records provenance rows, embeds `comfyvn_provenance` markers in PNGs, and preserves license tags in metadata/sidecars.
- ✅ 2025-10-21 — Audio/voice assets embed provenance markers via optional Mutagen support (MP3/OGG/FLAC/WAV); when tagging libraries are unavailable the system falls back gracefully with a debug notice.

Phase 3 — Import infrastructure

Part A — Roleplay importer (hardened)

Owner: Roleplay/World Lore Chat

Outputs:

~~API: POST /roleplay/import (txt/json), GET /imports/status/:id~~ ✅ 2025-10-20

~~Parser → Scene JSON with speaker attribution; preview files~~ ✅ 2025-10-20

Acceptance: ~~Small sample produces Scenes + Characters linked; job logs visible in GUI.~~ ✅ Verified via importer log + DB entries

Progress:
- ✅ 2025-10-21 — `/roleplay/import` persists scenes + characters via registries, writes importer logs to `logs/imports/`, and registers source transcripts as assets.
- ✅ 2025-10-21 — `/roleplay/imports/{job_id}` aggregates job + import metadata for GUI status polling.
- ✅ 2025-10-21 — `/roleplay/imports` list + `/roleplay/imports/{job_id}/log` enable Studio shell dashboards and log viewers; docs outline curl + sqlite inspection steps.
- ✅ 2025-10-21 — Studio `RoleplayImportView` upgraded to live job dashboard with auto-refresh and inline log viewer, consuming the new API hooks.
- ✅ 2025-10-22 — Roleplay imports now offload to background threads with optional blocking mode exposed to the API; multi-scene splitting remains on the backlog.

Part B — VN “pak/zip” importer

Owner: Importer Chat

Outputs:

API: POST /vn/import → background job

Adapters: Ren’Py archive/zip, Generic VN JSON

Extraction: assets → registry; characters/scenes/timeline mapping; licensing flags

Acceptance: Import a known VN pack → Scenes, Characters, Assets populated and browsable.

Status:
- ✅ 2025-10-20 — `/vn/import` API available; `import_vn_package` unpacks `.cvnpack/.zip` bundles, writes scenes/characters/assets, persists manifest + license flags, and logs summaries to support debugging.
- ✅ 2025-10-20 — TaskRegistry-backed job flow enqueues imports (`jobs/status/:id`), GUI VN importer polls completion, and per-job metadata captures importer summary + warnings for traceability.
- ✅ 2025-10-21 — `/vn/import/{job_id}` exposes job meta + cached summary JSON; backend writes `summary_path` + log artifacts for downstream UI.
- ✅ 2025-10-21 — External extractor manager (`/vn/tools/*`) lets users register binaries like arc_unpacker with regional warnings; importer auto-detects `.arc`/`.xp3` via adapters and records extractor provenance.
- ✅ 2025-10-21 — `/vn/tools/install` downloads curated extractors from GitHub with explicit license warnings and auto-registers them; `tool_installer` extension exposes installer docs.
- ✅ 2025-10-22 — Engine adapters wired: stage extraction feeds the importer registry, auto-detecting Ren'Py, KiriKiri, NScripter, Yu-RIS, CatSystem2, BGI/Ethornell, RealLive/Siglus, Unity VN, TyranoScript, and LiveMaker to emit `comfyvn-pack@1` manifests with per-engine metadata.
- ✅ 2025-10-22 — Normalizer upgraded (`core/normalizer.py`) to emit deterministic asset IDs, thumbnail placeholders, provenance-rich sidecars for large binaries, and manifest side-channel bookkeeping for audits.
- ✅ 2025-10-22 — Translation/remix pipeline delivered: segmenters generate translation bundles with TM hints, remix planning emits ComfyUI task manifests plus music stubs, and export plans cover Ren'Py loose/RPA, KiriKiri overlay, and Tyrano data outputs.
- 🚧 Manga importer parity — Mirror VN importer behaviour for Manga → VN conversion; ensure branchable scenes, voice synthesis hooks, and asset registries align.
- ⚠ Adapter selection (Ren’Py vs. generic), overwrite policy UX, and queued job cancellation still pending.

Part C — Manga → VN importer

Owner: Importer Chat

Outputs:

API: POST /manga/import (zip/cbz/pdf)

Pipeline: panel segmentation → OCR → bubble grouping → speaker heuristics → Scene synthesis

Optional translation pass (target: user base language)

Acceptance: Manga archive becomes a basic VN timeline with panels as backgrounds and lines as dialogue; fix-up UI available.

Phase 4 — Studio views

Recent Phase 4 updates (2025-10-22):
- ✅ Unified the Studio shell under `gui/main_window` with the legacy `studio_window` gating development toggles only; ServerBridge wiring, layout persistence, and menu flows now live in a single entrypoint.
- ✅ Scenes and Characters panels gained in-place editors backed by `/api/scenes/*` and `/api/characters/*`, keeping registry refreshes in-sync without regressing polling performance.
- ✅ Persisted server port selector now issues a relaunch reminder, writes through `ServerBridge.save_settings()`, and verifies the handshake against the backend before accepting the value.
- ✅ Backend warnings (provenance/import/advisory) flow through the toast + toast log system; warning toasts provide `View details` deep links and persist the latest 20 events.
- ✅ Extension manifests now enforce semantic-version compatibility (`requires.comfyvn`, optional API versions, explicit entrypoints). Incompatible plugins are skipped with surfaced diagnostics instead of hard failures.
- ✅ Runtime data (logs, settings, workspaces, caches) moved to OS-specific user directories via `comfyvn.config.runtime_paths`, with optional overrides (`COMFYVN_RUNTIME_ROOT`, `COMFYVN_LOG_DIR`, etc.) and legacy-friendly symlinks for existing scripts.
- ✅ Packaging roadmap documented in `docs/packaging_plan.md`, aligning wheel + PyInstaller/AppImage deliverables and signing/notarisation requirements.
- ✅ Sprite & pose panel exposes persona sprite controls, pose assignment, and previews hooked into ComfyUI workflows.

Part A — Scenes view (designer)

Owner: GUI Code Production

Outputs:

Node-based editor: nodes (text/choice/action), edges (next), inspectors

Inline play/preview

Acceptance: Create/edit scenes, persist changes; valid JSON schema; undo/redo.

Progress:
- ✅ 2025-10-22 — Node editor enables create/edit/delete for text, choice, and action nodes; inspector commits to `/api/scenes/save`, performs schema validation before merge, and tracks undo/redo history per session.

Part B — Characters view (lab)

Owner: Persona & Group Chat

Outputs:

Traits editor, portrait/expression linker; LoRA preview hooks

Links to scenes containing this character

Acceptance: Changing portrait/expression reflects in preview and persisted model.

Progress:
- ✅ 2025-10-22 — Trait editor now supports inline edits, portrait swaps, and expression preview syncing; changes persist via `/api/characters/update` and cross-link scenes refresh on save.

Part C — Timeline builder

Owner: GUI Code Production

Outputs:

Drag/drop scene order; branch grouping; seed control

Acceptance: Timeline can be saved/loaded; seeded replay consistent.

Progress:
- ✅ 2025-10-22 — Timeline panel enables creating, duplicating, and reordering scene sequences; entries persist via the timeline registry with per-step notes.

Part D — Assets library

Owner: Asset & Sprite System

Outputs:

Grid/list with thumbnails, tags, provenance; quick open in finder

Acceptance: Clicking any asset opens inspector; provenance “Show lineage” works.

Progress:
- ✅ 2025-10-21 — Imports, Audio, and Advisory panels wired to backend `/jobs`, `/api/tts`, and `/api/advisory` endpoints for live monitoring; asset inspector remains TODO.

Phase 5 — Compute & scheduling

Part A — Metrics panel & job queue

Owner: System/Server Core + GUI

Outputs:

~~/system/metrics stabilized; GUI charts; Job queue stream (WS)~~ ✅ 2025-10-20 — GUI Jobs panel now consumes `/jobs/ws` with reconnecting QWebSocket client.

Acceptance: ~~Live updates under load; backpressure won’t freeze GUI.~~ ✅ Verified 2025-10-20 (job metadata streamed + HTTP fallback; logging covers throttled queue events).

Part B — Local GPU manager

Owner: Remote Compute & GPU Access Chat

Outputs:

~~gpu_manager.py + API /api/gpu/list, /api/gpu/policy/{mode}~~ ✅ 2025-10-20

~~Policies: auto | manual | sticky; per-task overrides (hints)~~ ✅ 2025-10-20 — local & remote devices surfaced with persisted selection state.

Acceptance: ~~GPU presence detected (or absent gracefully); policy persisted; jobs annotated with device.~~ ✅ Verified 2025-10-20 (device selection recorded in task metadata).

Part C — Remote providers registry

Owner: Remote Compute & GPU Access Chat

Outputs:

~~providers table + API /api/providers/{list,register,health}~~ ✅ 2025-10-20

~~Providers: RunPod/Vast.ai/Unraid/Custom (adapters)~~ ✅ 2025-10-20 — templates exposed via registry presets with slugged IDs.

~~Compute advisor /compute/advise recommends CPU/GPU/Remote~~ ✅ 2025-10-20

Acceptance: ~~Register at least one provider; successful health check; advisor produces rationale.~~ ✅ Verified 2025-10-20 (health status persisted with timestamp; advisor returns rationale string).

Next wave (Importer alignment):
- Populate curated provider profiles (RunPod, Vast.ai, Lambda Labs, AWS EC2, Azure NV, Paperspace, unRAID, on-prem SSH/NFS) including authentication fields, cost/V RAM metadata, and policy hints for importer workloads (e.g., voice synthesis vs. large CG batch).
- Extend `/compute/advise` to consider importer asset sizes, translation pipeline demands, and cached ComfyUI workflow requirements. Surface recommended provider + cost estimate back into importer job summary.
- Document remote GPU onboarding flows in `docs/remote_gpu_services.md`, including legal caveats around content processing and data residency.
- ✅ 2025-10-22 — `/api/providers/{create,import,export}` support template-based provisioning, sharing, and backups; reference docs in `docs/compute_advisor_integration.md`.
- ✅ 2025-10-21 — `/api/gpu/advise` exposes compute advisor recommendations (local vs remote choice, cost hints, rationale) to importer pipelines and GUI scheduling.

Phase 6 — Audio & music

Part A — TTS pipeline (character-aware)

Owner: Audio & Effects Chat

Outputs:

API: /api/tts/synthesize (scene_id/character_id/text/lang)

Backend: ComfyUI node pipeline (workflow templating) with synthetic fallback; cache to assets_registry via audio cache manager

Acceptance: Generating a line creates a voice asset with sidecar + provenance.
Debugging: POST `/api/tts/synthesize` with curl, inspect `exports/tts/<voice>_<hash>.wav/.json`, confirm `logs/server.log` shows cached toggle on repeat call and `provider` metadata when ComfyUI is active.
Notes: See docs/studio_phase6_audio.md for API contracts, ComfyUI settings, cache expectations, and logging checklist.

Status:
- ✅ 2025-10-21 — `/api/tts/synthesize` implemented in `comfyvn/server/modules/tts_api.py`, delegating to `comfyvn/core/audio_stub.synth_voice` and persisting cache entries.
- ✅ 2025-10-21 — GUI audio panel wired to the new endpoint (stub playback) with cached toggles surfaced in logs.
- ⚠ Pending integration with ComfyUI runner and asset registry provenance so synthesized clips register as managed assets.

Part B — Music remix

Owner: Audio & Effects Chat

Outputs:

API: /api/music/remix (scene_id, target_style)

Looping/intro/outro helpers; asset linkage

Acceptance: Scene playback swaps to remixed track without glitch; asset registered.
Debugging: POST `/api/music/remix` with scene/style, inspect `exports/music/<scene>_<style>_*.wav/.json`, confirm INFO log in `logs/server.log` and ComfyUI provenance details when enabled.
Notes: `comfyvn/core/music_remix.py` submits MusicGen workflows to ComfyUI when configured and falls back to deterministic synth; `(artifact, sidecar)` contract unchanged.

Status:
- ✅ 2025-10-21 — `comfyvn/server/modules/music_api.py` exposes `/api/music/remix`, calling `comfyvn/core/music_remix.py::remix_track` with deterministic fallback generation and JSON sidecars.
- ✅ 2025-10-21 — Music cache entries persist to `cache/music_cache.json` via `MusicCacheManager`, enabling idempotent GUI previews.
- ⚠ ComfyUI workflow execution + asset registry linkage remain to be wired, including provenance entries and long-running job telemetry.

Part C — Audio cache manager

Owner: Asset & Sprite System + Audio Chat

Outputs:

Cache policy and dedupe by (character, text, style, model hash)

Acceptance: Repeated synth of identical inputs hits cache.
Debugging: Compare successive `/api/tts/synthesize` calls; verify `cached=true` and cache entry appears in `cache/audio_cache.json`.
Notes: Cache manager lives in `comfyvn/core/audio_cache.py` with key format `{voice|text_hash|lang|character|style|model_hash}`.

Status:
- ✅ 2025-10-21 — `AudioCacheManager` loads/persists JSON entries, keyed by the documented tuple and shared via `audio_cache` singleton for the TTS API.
- ✅ 2025-10-21 — Cache path now resolved through `comfyvn/config/runtime_paths.audio_cache_file`, aligning with the runtime storage overhaul.
- ⚠ Pending: eviction policy, size limits, and instrumentation (hit/miss counters to metrics/logs) before wider rollout.

Phase 7 — Advisory, policy, SFW/NSFW

Part A — Liability gate & settings

Owner: Advisory/Policy Chat

Outputs:

First-run & risky-flow gates; setting ack_legal_vN stored

Acceptance: Exports/imports blocked until acknowledged; recorded in settings.
Debugging: `GET /api/policy/status`, `POST /api/policy/ack`, then `POST /api/policy/evaluate` (ensure warnings surface but allow remains true).
Notes: Gate state persisted via `comfyvn/core/policy_gate.py`; honour user choice by warning without hard blocks.

Status:
- ✅ 2025-10-21 — `PolicyGate` persists acknowledgements via `SettingsManager`, tracks `ack_timestamp`, and surfaces overrides for audit.
- ✅ 2025-10-21 — FastAPI router (`comfyvn/server/modules/policy_api.py`) implements `/api/policy/{status,ack,evaluate}` with logging + error paths.
- ⚠ Outstanding: studio UX for multi-user acknowledgement history and automated reminder surfaces.

Part B — Advisory scans

Owner: Advisory/Policy Chat

Outputs:

/api/advisory/scan (target id, license_scan=1)

Findings logged to advisory_logs; quick fixes (replace, remove, request waiver)
Debugging: POST `/api/advisory/scan`, list via `/api/advisory/logs`, resolve with `/api/advisory/resolve`; WARN entries in `logs/server.log` confirm new issues.
Notes: See docs/studio_phase7_advisory.md for scan heuristics, resolution flow, and logging.

Acceptance: Import of non-open assets flagged; UI shows resolution flow.

Status:
- ✅ 2025-10-21 — `/api/advisory/scan` appends issues through `comfyvn/core/advisory.log_issue`, persisted to advisory logs for GUI consumption.
- ✅ 2025-10-21 — `/api/policy/filter-preview` and `content_filter.filter_items` emit WARN entries and integrate with advisory logs, satisfying filter preview tooling.
- ⚠ TODO: auto-remediation hooks (replace/remove/waiver) must emit structured events and surface in Studio dashboards.

Part C — SFW/NSFW filters

Owner: Advisory/Policy + Server Core

Outputs:

Server-side filtering on content queries by meta flags

UI toggle & per-export mode

Acceptance: Toggling filters affects queries/preview/export as expected.
Debugging: `POST /api/policy/filter-preview` with sample metadata, confirm warnings surface and `content_mode` matches `GET /api/policy/filters`.
Notes: Filter modes (`sfw|warn|unrestricted`) stored in `data/settings/config.json`; overrides keep items accessible while logging advisory warnings.

Status:
- ✅ 2025-10-21 — `comfyvn/core/content_filter.ContentFilter` reads/writes `filters.content_mode` and classifies assets, logging advisory warnings.
- ✅ 2025-10-21 — `/api/policy/filters` exposes GET/POST plus preview, enabling GUI toggles and importer checks.
- ⚠ Planned: extend classification with ML/heuristic scores and integrate per-export overrides.

Phase 8 — Runtime & playthrough

Part A — Variables/flags & API

Owner: Server Core + GUI

Outputs:

- REST API `/api/vars/{list,get,set,reset}` bridging GUI requests to the SQLite-backed registry.
- Scope support: global (project), session, scene. Reset clears corresponding caches and notifies listeners.
- GUI inspector for live variables with override + revert controls.

Acceptance: Scene logic can read/write variables, reset clears scoped state, and automated tests cover concurrency + persistence.

Status:
- ✅ 2025-10-20 — Phase 2 migrations created the `variables` table; `comfyvn/studio/core/variable_registry.py` supports list/get access.
- ✅ 2025-10-21 — Session persistence helpers in `comfyvn/core/state_manager.py` and `session_manager.py` provide baseline state IO (single scope).
- ⚠ API router + scope-aware runtime storage still pending; need event emission via `event_bus.emit("vars/changed", ...)` and GUI wiring.

Next:
- Formalise schema (global/session/scene columns) with migration script + tests.
- Implement FastAPI router (`comfyvn/server/modules/vars_api.py`) enforcing scope validation and audit logging.
- Extend session/state managers for multi-scope caches and notify the GUI variable dock.

Part B — Choices & deterministic seed

Owner: Server Core

Outputs:

Engine resolves conditional + weighted choices; seeded RNG

Acceptance: Replay with same seed yields same path; tests pass.

Status:
- ✅ 2025-10-20 — `comfyvn/core/replay_memory.ReplayMemory` appends/readbacks JSONL event streams for QA.
- ✅ 2025-10-20 — `/replay/auto` FastAPI endpoint exists with deterministic index selection stub in `comfyvn/core/replay.autoplay`.
- ⚠ Need full branching runner: weighted choice resolver, integration with scene execution engine, and seed propagation through sessions/jobs.

Next:
- Replace `autoplay` stub with RNG wrapper capturing branch metadata + variable diffs, persisting to `ReplayMemory`.
- Thread session seed management through orchestrator/state managers and expose `/replay/{start,step,status}` control APIs.
- Add pytest coverage to replay stored sessions twice and confirm identical paths, including failure-mode fixtures.

Part C — Streaming & typewriter

Owner: Server Core + GUI

Outputs:

- WebSocket delta stream for dialogue lines (with finalisation marker) plus Server-Sent Event fallback.
- GUI typewriter effect consumes streaming payloads, honours speed settings, and reconciles final chunk with authoritative text.

Acceptance: Smooth incremental rendering; no gaps; final chunk matches stored dialogue; tests cover reconnect & slow-consumer scenarios.

Status:
- ✅ 2025-10-20 — `/events/ws` + `/events/sse` routers deliver broadcast payloads using the current `event_hub` shim and keepalive pings.
- ✅ 2025-10-20 — GUI toast/log infrastructure consumes advisory + job events via the shared hub, validating transport plumbing.
- ⚠ Dialogue streaming not yet implemented; need async publisher for scene playback, buffering, and GUI typewriter integration.

Next:
- Upgrade `comfyvn/core/event_hub` to native async pub/sub with backpressure and topic filters.
- Implement streaming emitters in `scene_api.play_scene` (or dedicated runtime service) that send token deltas + final chunk events.
- Teach GUI dialogue renderer to animate incremental payloads and fall back to batch mode when streaming disabled.

Phase 9 — Export & packaging

Part A — Ren’Py export orchestrator

Owner: Export/Packaging Chat

Outputs:

- Orchestrator aggregates project scenes into `.rpy` scripts, copies assets, and stages output under `renpy_project/`.
- Validates scene graphs (labels, jumps), emits warnings for missing assets, and supports dry-run.
- Hooks into pipeline jobs so GUI can queue exports with progress and telemetry.

Acceptance: Minimal playable project runs; dry-run validation passes; export job writes provenance + validation logs.

Status:
- ✅ 2025-10-20 — `comfyvn/server/modules/export_scene_api.py` writes per-scene `.rpy` stubs; `/bundle/renpy` bundles staged files.
- ✅ 2025-10-20 — `comfyvn/scene_bundle.py` + `docs/scene_bundle.md` define scene bundle schema and conversions.
- ⚠ Full orchestrator pending: need multi-scene graph assembly, asset copying, and integration with job/orchestrator services.

Next:
- Build orchestrator service that walks scenes, resolves assets via registry, and materialises `script.rpy` + config.
- Validate exports with Ren’Py lint/dry-run, capturing logs under `exports/renpy/validation.log`.
- Surface job progress (per-scene events) via `/jobs/*` and enrich provenance metadata for later audits.

Part B — Studio export bundle

Owner: Export/Packaging Chat

Outputs:

ZIP with scenes, assets, provenance manifest, readme/license

Acceptance: Bundle re-importable; provenance intact.

Status:
- ✅ 2025-10-20 — Bundle scaffolding exists through `/bundle/renpy` (zip) and scene bundle converters.
- ⚠ Need unified export bundle (studio-focused) combining scene bundles, assets, provenance json, and README/license copy.

Next:
- Define bundle manifest schema (v1) covering variables, seeds, advisory status, and included assets.
- Extend CLI/GUI commands to trigger bundle build and store artefacts under `exports/bundles/`.
- Add tests ensuring bundles re-import cleanly via importer pipeline.

Part C — Provenance manifest

Owner: Advisory/Policy + Export

Outputs:

provenance.json describing pipeline, seeds, hashes, timestamps

Acceptance: Manifest resolves back to DB entries and sidecars.

Status:
- ✅ 2025-10-21 — Asset-level provenance captured during registry writes (hashes, licenses, source workflow).
- ⚠ Export-level manifest not yet authored; need to aggregate seeds, variable snapshots, advisory findings, and compute traces.

Next:
- Design manifest format referencing scene IDs, variable baselines, replay seeds, and export timestamps.
- Implement writer invoked by both Ren’Py orchestrator and studio bundle builder.
- Cross-link manifest entries to advisory logs and compute provider metadata for auditability.

Phase 10 — Integrations & extensions

Part A — SillyTavern bridge (extension sync)

Owner: Persona & Group + ST Bridge Chat

Outputs:

Extension sync (copy/update); health check; persona import

Acceptance: Personas/world lore can be pulled and linked into Scenes.

Part B — Plugin loader (future)

Owner: Server Core + GUI

Outputs:

/extensions/ folder; plugin API hooks; UI panel injection

Acceptance: Example plugin adds a panel and route safely.

Part C — Localization/i18n

Owner: Translation Chat

Outputs:

translations table; UI language toggle; fallback rules

Acceptance: Switching language updates text, falls back cleanly.

Phase 11 — Ops & CI

Part A — Installers (Windows-first)

Owner: Scripts/Install Chat

Outputs:

install_setup_comfyvn.ps1 (venv, deps, health check)

run_comfyvn.py (CLI launcher with `--server-only`, `--server-url`, `--server-reload`, etc.)

Acceptance: Fresh machine can install + launch studio reliably.

Part B — Docker & dev parity (later)

Owner: Ops/CI Chat

Outputs:

docker-compose with server/UI/Redis (if needed)

Acceptance: Local and CI environments run builds deterministically.

Part C — Tests & QA harness

Owner: Code Updates + QA

Outputs:

Integration tests (supertest-like via FastAPI TestClient)

Seeded replay tests for branching correctness

Acceptance: CI badge green; minimal flakiness.

4) Ownership map (chats → modules)

Server Core Production: app.py, /server/modules/*, runtime APIs, streaming, variables/choices, export orchestrator

GUI Code Production (Studio): studio_window.py, views/*, ServerBridge, graphs, inspectors

v0.5 Scaffold & DB: migrations, db_manager.py, schema/versioning

Asset & Sprite System: registry, thumbnails, sidecars, asset browser

Roleplay/World Lore: roleplay import, world indexing, persona linking

Importer: VN/manga importers, file ingestion pipeline

Remote Compute & GPU Access: gpu_manager, providers registry, compute advisor

Audio & Effects: TTS, remix, audio cache

Advisory/Policy: liability gate, scans, SFW/NSFW filters, provenance policy

Export/Packaging: Ren’Py exporter, bundle exporter, manifests

SillyTavern Bridge: extension sync, persona/world import

Code Updates: patchers, repair scripts, version bumps

Project Integration: docs, changelogs, roadmap, release notes

Rule: Don’t modify modules outside your ownership without coordinating via Code Updates and Project Integration.

5) Data contracts (concise)

Scene JSON: { id, title, nodes:[ {id,type("text"|"choice"|"action"),content,directives{},conditions[],next[],meta} ], meta }

Character JSON: { id, name, traits{}, portrait_asset_id, linked_scene_ids[] }

Timeline JSON: { id, name, scene_order[], meta }
World JSON: { id, name, summary, tone, rules{}, locations{}, factions{}, lore{}, prompt_templates{} }

Asset registry row: { id, uid, type, path_full, path_thumb, hash, bytes, meta{license,nsfw,origin}, created_at }

Provenance row: { asset_id, source, workflow_hash, commit, inputs_json, c2pa_like, user_id }

Job row: { id, type, status, progress, logs_path, input_json, output_json }

Provider row: { id, name, kind("local"|"remote"), config_json, status }

6) Acceptance summary (global “done”)

Server health & metrics up; GUI shows live graphs; no menu duplication.

DB migrations create all tables; asset registry + thumbnails + sidecars working.

Roleplay/VN/Manga importers produce Scenes/Characters/Assets with advisory findings where needed.

Studio views (Scenes, Characters, Timeline, Assets, Imports, Compute, Audio, Advisory, Export, Logs) switch cleanly and persist.

Compute advisor and GPU policy annotate jobs; remote provider can be registered and health-checked.

TTS pipeline caches voice lines with provenance; music remix swappable at runtime.

Liability gate prevents risky actions without acknowledgement; SFW/NSFW & licensing filters respected.

Runtime supports variables/flags, conditional & weighted choices, seeded deterministic replay.

Exporters: Ren’Py project compiles; bundle export includes provenance manifest.

Installers/scripts work on a fresh Windows environment.

7) Risks & mitigations

Library drift (FastAPI/Starlette/Pydantic): pin versions and add constraints.txt.

OCR quality (manga): include fix-up UI; don’t promise one-shot accuracy.

Remote GPU costs: compute advisor defaults to local; explicit user opt-in for offload.

Data privacy: user data folders are git-ignored; logs do not include secrets.

8) How to use this doc

Each chat/team picks the current Phase and Part(s) assigned to them.

When a Part is finished, post the Outputs and show Acceptance checks.

If a Part needs changes in another module, coordinate through Code Updates with a mini‑patch plan referencing this doc.

End of ARCHITECTURE.md
