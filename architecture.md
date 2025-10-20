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
- ⚠ Thumbnail worker still inline; background worker deferred while Pillow-powered path handles PNGs.
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
- ⚠ Audio/voice stamping pending ID3 integration; current implementation logs a warning for unsupported formats.

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
- ⚠ Background job offload + multi-scene splitting still pending; current implementation runs synchronously per request.

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
- 🚧 Engine adapters pending — Build per-engine importers (Ren’Py, KiriKiri/KAG, NScripter family, Yu-RIS, CatSystem2, BGI/Ethornell, RealLive/Siglus, Unity VN, TyranoScript, LiveMaker) using detection heuristics documented in `docs/importer_engine_matrix.md`. Preserve voice/text mapping, convert proprietary formats via user-supplied hooks, and emit `comfyvn-pack@1` manifests.
- 🚧 Normalizer/manifest writer — Implement `core/normalizer.py` to create deterministic asset IDs, manage thumbnails, and store large binaries on disk with JSON sidecars; persist provenance metadata for audits.
- 🚧 Translation + remix pipeline — Integrate segmenters, TM/glossary, ComfyUI remix workflows (sprite recolor, CG upscale, UI theme), and export targets (Ren’Py loose/RPA via hook, KiriKiri overlay patch, Tyrano data/). See Section 6 design notes.
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

Part A — Scenes view (designer)

Owner: GUI Code Production

Outputs:

Node-based editor: nodes (text/choice/action), edges (next), inspectors

Inline play/preview

Acceptance: Create/edit scenes, persist changes; valid JSON schema; undo/redo.

Progress:
- ✅ 2025-10-21 — Dockable Scenes panel lists registry scenes and refreshes when projects change (baseline browser, no editor yet).

Part B — Characters view (lab)

Owner: Persona & Group Chat

Outputs:

Traits editor, portrait/expression linker; LoRA preview hooks

Links to scenes containing this character

Acceptance: Changing portrait/expression reflects in preview and persisted model.

Progress:
- ✅ 2025-10-21 — Characters dock lists registry entries and displays origin metadata; updates automatically on project switch (editing still pending).

Part C — Timeline builder

Owner: GUI Code Production

Outputs:

Drag/drop scene order; branch grouping; seed control

Acceptance: Timeline can be saved/loaded; seeded replay consistent.

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
- ✅ 2025-10-21 — `/api/gpu/advise` exposes compute advisor recommendations (local vs remote choice, cost hints, rationale) to importer pipelines and GUI scheduling.

Phase 6 — Audio & music

Part A — TTS pipeline (character-aware)

Owner: Audio & Effects Chat

Outputs:

API: /api/tts/synthesize (scene_id/character_id/text/lang)

Backend: ComfyUI node pipeline or local adapter; cache to assets_registry

Acceptance: Generating a line creates a voice asset with sidecar + provenance.
Debugging: POST `/api/tts/synthesize` with curl, inspect `exports/tts/<voice>_<hash>.txt/.json`, confirm `logs/server.log` shows cached toggle on repeat call.
Notes: See docs/studio_phase6_audio.md for API contracts, cache expectations, and logging checklist.

Part B — Music remix

Owner: Audio & Effects Chat

Outputs:

API: /api/music/remix (scene_id, target_style)

Looping/intro/outro helpers; asset linkage

Acceptance: Scene playback swaps to remixed track without glitch; asset registered.
Debugging: POST `/api/music/remix` with scene/style, inspect `exports/music/<scene>_<style>_*.txt/.json`, confirm INFO log in `logs/server.log`.
Notes: Stub implementation in `comfyvn/core/music_remix.py`; replace with real pipeline while preserving `(artifact, sidecar)` contract.

Part C — Audio cache manager

Owner: Asset & Sprite System + Audio Chat

Outputs:

Cache policy and dedupe by (character, text, style, model hash)

Acceptance: Repeated synth of identical inputs hits cache.
Debugging: Compare successive `/api/tts/synthesize` calls; verify `cached=true` and cache entry appears in `cache/audio_cache.json`.
Notes: Cache manager lives in `comfyvn/core/audio_cache.py` with key format `{voice|text_hash|lang|character|style|model_hash}`.

Phase 7 — Advisory, policy, SFW/NSFW

Part A — Liability gate & settings

Owner: Advisory/Policy Chat

Outputs:

First-run & risky-flow gates; setting ack_legal_vN stored

Acceptance: Exports/imports blocked until acknowledged; recorded in settings.
Debugging: `GET /api/policy/status`, `POST /api/policy/ack`, then `POST /api/policy/evaluate` (ensure warnings surface but allow remains true).
Notes: Gate state persisted via `comfyvn/core/policy_gate.py`; honour user choice by warning without hard blocks.

Part B — Advisory scans

Owner: Advisory/Policy Chat

Outputs:

/api/advisory/scan (target id, license_scan=1)

Findings logged to advisory_logs; quick fixes (replace, remove, request waiver)
Debugging: POST `/api/advisory/scan`, list via `/api/advisory/logs`, resolve with `/api/advisory/resolve`; WARN entries in `logs/server.log` confirm new issues.
Notes: See docs/studio_phase7_advisory.md for scan heuristics, resolution flow, and logging.

Acceptance: Import of non-open assets flagged; UI shows resolution flow.

Part C — SFW/NSFW filters

Owner: Advisory/Policy + Server Core

Outputs:

Server-side filtering on content queries by meta flags

UI toggle & per-export mode

Acceptance: Toggling filters affects queries/preview/export as expected.
Debugging: `POST /api/policy/filter-preview` with sample metadata, confirm warnings surface and `content_mode` matches `GET /api/policy/filters`.
Notes: Filter modes (`sfw|warn|unrestricted`) stored in `data/settings/config.json`; overrides keep items accessible while logging advisory warnings.

Phase 8 — Runtime & playthrough

Part A — Variables/flags & API

Owner: Server Core + GUI

Outputs:

/api/vars/{get,set,list,reset}; scopes: global/session/scene

Acceptance: Scene logic can read/write variables; reset works.

Part B — Choices & deterministic seed

Owner: Server Core

Outputs:

Engine resolves conditional + weighted choices; seeded RNG

Acceptance: Replay with same seed yields same path; tests pass.

Part C — Streaming & typewriter

Owner: Server Core + GUI

Outputs:

WS delta stream for lines; finalization marker; typewriter effect

Acceptance: Smooth incremental rendering; no gaps; final chunk consistent.

Phase 9 — Export & packaging

Part A — Ren’Py export orchestrator

Owner: Export/Packaging Chat

Outputs:

Scenes → rpy scripts; assets copied; build into renpy_project/

Acceptance: Minimal playable project runs; dry-run validation passes.

Part B — Studio export bundle

Owner: Export/Packaging Chat

Outputs:

ZIP with scenes, assets, provenance manifest, readme/license

Acceptance: Bundle re-importable; provenance intact.

Part C — Provenance manifest

Owner: Advisory/Policy + Export

Outputs:

provenance.json describing pipeline, seeds, hashes, timestamps

Acceptance: Manifest resolves back to DB entries and sidecars.

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
