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

Docs channel overview
---------------------

The `docs/` tree is split by delivery lane so every chat knows where to drop status notes and modder guidance:

- `docs/development/` — contributor-facing “how to extend” references (`plugins_and_assets.md`, `advisory_modding.md`, the new `observability_debug.md`).
- `docs/ADVISORY_EXPORT.md` — P5 advisory/export workflow (feature flags, policy gate API, CLI JSON contract) with a companion dev log in `docs/dev_notes_advisory_export.md`.
- `docs/production_workflows_v0.7.md` — release/operator runbooks maintained by Project Integration.
- `docs/CODEX_STUBS/` — work orders mirrored from the tooling chat; treat these as immutable.
- `docs/CHANGEME.md` — rolling log of shipped items with pointers back to owning chats and related docs.
- `docs/LLM_RECOMMENDATIONS.md` — provider tags, adapter defaults, and module-specific LLM tuning notes for Studio tooling and automation scripts.
- `docs/POV_DESIGN.md` — canonical POV manager contract (`/api/pov/*`, save-slot naming, runner integration).
- `docs/development/pov_worldlines.md` — worldline registry API (`/api/pov/worlds`, diff/merge helpers) plus export hooks for canonical vs multi-world builds.
- `docs/VIEWER_README.md` — viewer launch checklist with `/api/viewer/{start,stop,status}` payloads and environment overrides.
- `docs/development/emulation_and_llm.md` — SillyCompatOffload feature flag, emulation engine payloads, LLM proxy usage, and prompt pack locations.
- `docs/EDITOR_UX_ADVANCED.md` — blocking assistant + snapshot sheet API contracts, feature flags, hook payloads, and verification checklist (`p6_editor_ux`).
- `docs/development/dev_notes_editor_blocking.md` — CLI drills, determinism notes, and hook payload reference for the editor blocking assistant and snapshot sheet compositor.
- `docs/VN_VIEWER_GUIDE.md` — Phase 9 VN Loader and Mini-VN integration guide (GUI workflows, REST hooks, modder debug affordances).
- `docs/development/dev_notes_cloud_sync.md` — S3/GDrive sync API, secrets vault rotation, manifest layout, provider SDK setup, and modder hook payloads.
- `docs/dev_notes_playtest_harness.md` — deterministic playtest harness guide (feature flag, API payloads, golden diffs, modder hooks, and debug checklist).
- `docs/AUDIO_LAB.md` — feature-flagged Audio Lab contracts (voice catalog, TTS cache, alignment JSON, mixer metadata) with hook payloads and filesystem layout.
- `docs/ASSET_INGEST.md` — staged asset ingest pipeline (queue API, dedup cache, provenance, rate limits) with companion debug log `docs/dev_notes_asset_ingest.md`.
- `docs/DUNGEON_API.md` — dungeon runtime contract (`/api/dungeon/*`), snapshot payloads, determinism checklist, and modder hook catalogue; see companion dev note `docs/dev_notes_dungeon_api.md` for REPL helpers and curl drills.
- `docs/ANIM_25D.md` — auto-rig + motion graph architecture, REST payloads, determinism/performance guidelines, preset storage, and hook catalogue for the 2.5D animation pipeline.
- `docs/dev_notes_anim_25d.md` — debugging cookbook covering anchor tagging, preview sequencing, preset management, and hook emission verification.
- `docs/PROMPT_PACKS/` — reusable prompt templates (POV rewrite, battle narration) with strict JSON schemas for narrative tooling.
- `docs/development/theme_world_changer.md` — Theme & World Changer REST contracts, checksum guarantees, debug flows, and modder automation tips.
- `docs/PORTS_ROLLOVER.md` — launcher host/port rollover design, runtime authority resolution, REST probes, and CLI drills teams can script against when deploying Studio alongside modded servers.
- `docs/ST_IMPORTER_GUIDE.md` — SillyTavern chat importer workflow (export steps, importer API, run artefacts, persona heuristics, modder hooks) with companion development log in `docs/dev_notes_st_importer.md`.

Community connectors (F-List & FurAffinity)
-------------------------------------------

- `comfyvn/connectors/flist.py` parses F-List markdown/BBCode exports into persona payloads, mapping kink taxonomies into NSFW tags (trimmed unless the global flag + consent allow them) and recording debug metrics (`sections`, `kink_counts`) for modder automation.
- `comfyvn/connectors/furaffinity.py` stores user-supplied image uploads only (strict base64 decode, no scraping), hashes files under `data/persona/imports/<persona_id>/`, writes provenance sidecars with optional credits, and records trimmed NSFW tag lists when gating removes them.
- `comfyvn/server/routes/connectors_persona.py` exposes `/api/connect/flist/consent|import_text`, `/api/connect/furaffinity/upload`, and `/api/connect/persona/map`. All routes require `features.enable_persona_importers`, reuse the shared consent JSON, apply `build_persona_record`, and persist persona/provenance JSON before firing `on_connector_persona_mapped` + `on_persona_imported`.
- Consent JSON (`data/persona/consent.json`) now gains `connectors.flist` metadata, storing per-connector NSFW allowances, profile URLs, agents, and notes. The checker profile `p7_connectors_flist_fa` validates the routes, flags, and required docs.
- Modder hooks `on_flist_profile_parsed` and `on_furaffinity_asset_uploaded` broadcast parsed persona payloads and stored asset metadata (hash/path/sidecar) so dashboards or plugins can react without polling REST endpoints.

SillyTavern chat importer
-------------------------

- `comfyvn/importers/st_chat/parser.py` reads SillyTavern chat exports (`.json` or roleplay `.txt`) and normalises each turn into `{speaker, text, ts, meta}` records. Timestamp heuristics cover ISO strings, epoch seconds, and embedded SillyTavern metadata.
- `comfyvn/importers/st_chat/mapper.py` segments transcripts by conversation title or long pauses, infers `line`/`choice`/`end` nodes, resolves persona IDs through `PersonaManager`, extracts expressions from `[emote]`, emoji, and `*stage*` cues, and records unresolved speaker warnings in scene metadata.
- `comfyvn/server/routes/import_st.py` exposes `/api/import/st/start` and `/api/import/st/status/{runId}` behind `features.enable_st_importer`. Runs persist artefacts under `imports/<runId>/`, write generated scenes to `data/scenes/`, append history to `data/projects/<projectId>.json`, and emit the modder hooks `on_st_import_started`, `on_st_import_scene_ready`, `on_st_import_completed`, and `on_st_import_failed`.
- `comfyvn/server/modules/st_import_api.py` mounts the router via the module auto-loader so the importer routes are available once the flag is enabled.
- Docs: `docs/ST_IMPORTER_GUIDE.md` (export workflow, API payloads, scene heuristics, run artefacts, troubleshooting) with a companion development log in `docs/dev_notes_st_importer.md`. Checker profile `p9_st_import_pipeline` validates flag defaults, routes, and required docs/tests.

Cloud sync & secrets vault summary
---------------------------------

- `comfyvn/sync/cloud/manifest.py` owns the canonical manifest model (`ManifestEntry.path/size/mtime/sha256`), default include/exclude sets, checksum helpers, and deterministic scanning routines that skip cache/log/tmp directories.
- Provider adapters live beside it: `s3.py` (Amazon S3 via `boto3`) and `gdrive.py` (Drive v3 service account). Both implement dry-run summaries, resumable plan application, and aggregate per-file failures so reruns can pick up where they left off. Manifests are uploaded to the provider only when all operations succeed.
- Secrets are loaded through `comfyvn/sync/cloud/secrets.py`. `SecretsVault` keeps `config/comfyvn.secrets.json` encrypted with AES-GCM (PBKDF2-HMAC-SHA256); inline backups retain the last five ciphertext envelopes. Unlock via `COMFYVN_SECRETS_KEY` or an explicit passphrase argument.
- Cloud sync FastAPI routes live in `comfyvn/server/routes/sync_cloud.py` and expose `/api/sync/manifest`, `/api/sync/dry_run`, `/api/sync/run`, plus `/api/backup/{create,restore}` for local ZIP archives under `backups/cloud/`. Feature flags: `enable_cloud_sync`, `enable_cloud_sync_s3`, `enable_cloud_sync_gdrive`.
- Automation/debug flows rely on modder hooks `on_cloud_sync_plan` (dry-run telemetry) and `on_cloud_sync_complete` (run summaries with status + counts). Structured logs (`sync.dry_run`, `sync.run`, `backup.create`, `backup.restore`) land in `logs/server.log`; secrets never appear in log payloads.
- Reference material: `docs/CLOUD_SYNC.md`, `docs/BACKUPS.md`, and the refreshed dev note `docs/development/dev_notes_cloud_sync.md` cover IAM scopes, curl drills, hook payloads, and recovery checklists. The checker profile `p4_cloud_sync` validates flag defaults, routes, and documentation presence.
- `docs/development/public_translation_ocr_speech.md` — public MT/OCR/Speech adapter contracts, feature flag wiring, dry-run diagnostics, and modder integration notes.
- `comfyvn/public_providers/{translate_*,ocr_*,speech_*}.py` and `comfyvn/server/routes/providers_translate_ocr_speech.py` expose dry-run translation/OCR/speech metadata behind `enable_public_translate`. `/api/providers/translate/health` fuses pricing links, credential diagnostics, and docs references for the Studio debug panels.
- `comfyvn/public_providers/llm_{openai,anthropic,gemini,openrouter}.py` and `comfyvn/server/routes/providers_llm.py` implement the public LLM router. `/api/providers/llm/registry` surfaces model tags + pricing anchors, while `POST /api/providers/llm/chat` returns HTTP dispatch plans so routing logic can be inspected without hitting upstream APIs.
- `docs/PROVIDERS_LANG_SPEECH_LLM.md` covers environment keys, pricing links, curl snippets, and dry-run behaviour. `docs/LLM_RECOMMENDATIONS.md` tracks module presets (Translate, VN Chat, Narrator, Worldbuild, Battle narration) so UI dropdowns stay aligned with backend defaults.
- `docs/development/battle_layer_hooks.md` — battle choice vs sim APIs, seeding helpers, narration payload schemas, and SFX/VFX hand-off tips for modders.
- `docs/development/observability_debug.md` — crash triage, log tooling, Debug Integrations panel usage, and `/api/modder/hooks/*` history/WebSocket examples for automation scripts.
- `docs/development/perf_budgets_profiler.md` — CPU/VRAM budgets, lazy asset eviction flows, profiler mark/dashboard endpoints, feature flags, modder hook payloads, and curl recipes for contributors.
- `docs/dev_notes_asset_registry_hooks.md` — asset registry filter matrix, curl/WebSocket snippets, dry-run guidance, and tips for wiring automation into the expanded modder hook bus.
- `docs/IMAGE2PERSONA.md` — P6 Image→Persona analyzer pipeline (appearance tags, palette, pose anchors, expression prototypes, style/LoRA suggestions) plus deterministic/hash guidance.
- `docs/dev_notes_image2persona.md` — hook catalog for palette/appearance overrides, anchor/expressions injections, style registry extensions, and QA playbooks.
- `docs/PERSONA_IMPORTERS.md` — consent-driven persona importer flow covering `/api/persona/{consent,import,preview,map}`, provenance layout, curl recipes, and modder hook payloads.
- `docs/NSFW_GATING.md` — NSFW gate matrix (feature flag + consent) describing how persona fields are trimmed or persisted and how QA should validate the toggle.
- `docs/dev_notes_persona_importers.md` — debug checklist for consent recording, importer flows, NSFW verification, hook subscriptions, and storage layout audits.
- `docs/COMMUNITY_CONNECTORS.md` — consent, provenance, and route contracts for `/api/connect/flist/*`, `/api/connect/furaffinity/upload`, and `/api/connect/persona/map`, including curl drills and checker references.
- `docs/dev_notes_community_connectors.md` — deep dive on parser heuristics, NSFW trimming, hook verification, consent JSON layout, and troubleshooting tips for contributors.
- `docs/THEME_TEMPLATES.md` — canonical presets, override semantics, and REST payloads for theme application plus GUI hook annotations.
- `docs/WEATHER_PROFILES.md` — weather planner inputs/outputs, transition presets, and modder debug flows for `/api/weather/state`.
- `docs/BATTLE_DESIGN.md` — battle UX & simulation v0 guide (formula, resolve/simulate payloads, prompt pack alignment, roadmap).
- `docs/WORKBOARD_PHASE7_POV_APIS.md` — Phase 7 task board capturing public provider catalog work, pricing anchors, review notes, and documentation checklist.
- `README.md → Debug & Verification Checklist` — copy/paste block required in every PR description so reviewers can confirm docs, hooks, logs, and dry-run coverage before merge.

When adding development notes, prefer creating or updating a page under `docs/development/` and cross-link it from both this architecture doc and the README so modders can discover API/CLI hooks quickly.

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
  emulation/
    engine.py
  models/
    registry.py
    prompt_packs/
      persona.md
      translate.md
      worldbuild.md
  battle/
    __init__.py
    engine.py
  pov/
    perspective.py
    worldlines.py
    timeline_worlds.py
    render_pipeline.py
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
    routes/
      emulation.py
      llm.py
      battle.py
      pov.py
      pov_render.py
      viewer.py
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

Studio v0.7 release coordination (target window: 2025-10-27)

Highlights:
- Unified Studio shell under `gui/main_window/*` with scenes, characters, and timeline inspectors now mirrored in `gui/views/{scenes,characters,timeline}_view.py`. These views fetch from `/api/{scenes,characters,timelines}` via `ServerBridge` and fall back to mock payloads when the server is offline. ✅ GUI Code Production
- Playground tiers land behind `features.enable_playground` + `features.enable_stage3d`: `comfyvn/gui/central/playground_view.py` adds a **Playground** tab to the center router when the flag flips on, Tier-0 parallax draws via `comfyvn/playground/parallax.py`, and Tier-1 Stage 3D embeds `comfyvn/playground/stage3d/viewport.html` (Three.js/VRM modules vendored under `stage3d/vendor/` for offline builds). Snapshots persist to `exports/playground/render_config.json` with hooks for Codex A ingestion. ✅ GUI Code Production + Tooling
- Import infrastructure (roleplay + VN) hardened with job dashboards, provenance stamping, and asset registry parity; docs live under `docs/import_roleplay.md` and `docs/importer_engine_matrix.md`. ✅ Importer + Roleplay Chats
- Remote compute path delivers `/jobs/ws`, GPU manager policies, and provider registry with curated templates; packaging + runtime storage docs aligned. ✅ System/Server Core + Remote Compute Chats
- Scheduler telemetry landed: `comfyvn/compute/scheduler.py` tracks local/remote queues with priority pre-emption, sticky-device affinity, and provider-cost estimation. `/api/schedule/*` exposes queue health, Gantt-friendly board data, and lifecycle verbs (enqueue/claim/complete/fail/requeue), while Studio's Scheduler Board dock visualises jobs with duration/cost overlays. ✅ Scheduler & Telemetry Chat
- Policy gate, advisory scans, and audio lab tooling landed: cached `/api/tts/speak` synthesis now writes deterministic WAV + phoneme alignment/lipsync sidecars, `/api/audio/mix` provides scene-aware ducking with cached renders, and `/api/music/remix` job plans remain the hand-off until ComfyUI wiring is complete. GUI surfacing wired for acknowledgements and previews. ✅ Audio & Policy Chats
- SillyTavern bridge alignment: `/st/health` exposes ping status along with bundled vs installed versions for both the browser extension and comfyvn-data-exporter plugin, `/st/extension/sync` supports dry-run/write modes with manifest comparison, `/st/import` maps `worlds`, `personas`, `characters`, and `chats` payloads into `WorldLoader`, `PersonaManager`, and `SceneStore`, and `/st/session/sync` pushes VN state (scene, POV, variables, history) to SillyTavern while pulling back a reply ready for the VN Chat panel. Lightweight helpers (`collect_session_context`, `load_scene_dialogue`) and `SillyTavernBridge.get_active()` expose active-world/persona snapshots to any prompt surface without performing a full sync. Docs: `README.md`, `docs/dev_notes_modder_hooks.md`.
- Asset gallery dock completed: `AssetGalleryPanel` exposes tag/license filters, bulk edits, live refresh via registry hooks, and clipboard debug exports for modders. Registry changes mirror to the Modder Hook Bus via `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, and `on_asset_sidecar_written`, each carrying the refreshed asset type, sidecar path, and metadata snapshot so automation scripts can subscribe without polling. Hook contracts live in `docs/dev_notes_asset_registry_hooks.md`, with WebSocket/REST usage captured in `docs/dev_notes_modder_hooks.md`. `/assets/debug/{hooks,modder-hooks,history}` plus `/assets/{uid}/sidecar` keep CLI/bot workflows in sync without touching the database. ✅ Assets Chat
- Scenario workshop view merged: `TimelineView` pairs the node editor, track-based timeline, and the Scenario Runner. The runner consumes `/api/scenario/run/step` + `/api/pov/*`, tracks seeds/variables, and exposes breakpoints so designers can pause on node IDs when validating branches. Debug/workflow guidance lives in `docs/POV_DESIGN.md` and `docs/development_notes.md`. ✅ Narrative Systems Chat
- POV worldline registry landed: `comfyvn/pov/worldlines.py` tracks named forks (id/label/pov/root/notes/metadata), `comfyvn/pov/timeline_worlds.py` provides diff/merge helpers, `/api/pov/worlds` lists & activates worlds, and `/api/pov/{diff,merge}` expose branch comparisons for modders. Ren'Py exports accept `--world`/`--world-mode` and embed the active set in `export_manifest.json`. Docs: `README.md`, `docs/POV_DESIGN.md`, `docs/development/pov_worldlines.md`. ✅ Narrative Systems & Export Chats
  - Diff/Merge tooling expands the stack: `comfyvn/diffmerge/scene_diff.py` produces POV-masked node/choice/assets deltas, `comfyvn/diffmerge/worldline_graph.py` compiles a graph-friendly timeline with fast-forward previews, and `/api/diffmerge/{scene,worldlines/graph,worldlines/merge}` ships behind feature flag `enable_diffmerge_tools`. GUI parity lives under **Modules → Worldline Graph** via `comfyvn/gui/panels/diffmerge_graph_panel.py`, keeping 1k-node renders smooth and wiring preview/apply buttons into the new REST surface. Modder hooks `on_worldline_diff` / `on_worldline_merge` mirror REST activity for automation.
  - Timeline overlay lanes: `comfyvn/gui/overlay/timeline_overlay.py` compiles OFFICIAL⭐/VN Branch🔵/Scratch⚪ tracks with diff badges, scrub helpers, and thumbnail metadata pulled from `Worldline.metadata["snapshots"]` (cache keys blend `{scene,node,worldline,pov,vars,seed,theme,weather}`). The registry persists `_wl_delta` payloads for delta-over-base storage, exposing the merged view plus parent deltas to GUI panels and hooks. `/api/pov/{worlds,worlds/switch,confirm_switch,auto_bio_suggest}` sit behind `enable_worldlines` + `enable_timeline_overlay`, supporting fork-on-confirm, POV-masked bios, and emitting enriched modder hooks (`on_worldline_created`, `on_snapshot`) that now carry `delta`, `workflow_hash`, and `sidecar` metadata for dashboards. Docs captured in `docs/TIMELINE_OVERLAY.md`.
  - Depth-from-2D manager: `comfyvn/visual/depth2d.py` resolves auto planes (3–6 slices) and honours manual scene masks (`data/depth_masks/<scene>.json`) when authors toggle per-scene mode. Feature flag `enable_depth2d` guards the stack; preferences persist under `cache/depth2d_state.json` so manual overrides survive restarts.
- Character emulation & LLM registry: `comfyvn/emulation/engine.py` introduces the feature-flagged SillyCompatOffload engine, `/api/emulation/*` manages persona memory + adapter calls, and `/api/llm/{registry,runtime,test-call}` expose the JSON-backed provider list, runtime overrides, and a stubbed chat echo. The production `/api/llm/chat` proxy and prompt-pack endpoints remain on the roadmap; module prompt packs ship with docs under `docs/PROMPT_PACKS/` while templates live in `comfyvn/models/prompt_packs/`. Docs: `docs/LLM_RECOMMENDATIONS.md`, `docs/development/emulation_and_llm.md`. ✅ LLM Systems Chat (discovery only)
- VN chat dock & narrator rails: `comfyvn/gui/central/chat_panel.py` (Modules → VN Chat) now binds to the offline-first narrator queue under `/api/narrator/{status,mode,propose,apply,stop,rollback,chat}`. `comfyvn/server/routes/narrator.py` enforces Observe → Propose → Apply with a three-turn cap, deterministic proposal ids, and rollback snapshots, while `comfyvn/llm/orchestrator.py` maps Narrator/MC/Antagonist/Extras roles to adapters/devices with dry-run planning and budgets (feature flag `enable_llm_role_mapping`). Hooks (`on_narrator_proposal`, `on_narrator_apply`) emit queue/apply events for dashboards; spec + curl samples live in `docs/NARRATOR_SPEC.md`, `docs/LLM_ORCHESTRATION.md`, and the refreshed README.
- Viewer control routes landed: `/api/viewer/start` launches Ren’Py (native embed) and now falls back to web (`/api/viewer/web/{token}/{path}`) or deterministic Mini-VN previews (`/api/viewer/mini/{snapshot,refresh,thumbnail}`) when binaries are missing. `/api/viewer/status` reports process/window metadata plus the fallback payloads (`runtime_mode`, `mini_digest`). Feature flags `enable_viewer_webmode` / `enable_mini_vn` gate the fallbacks. Reference: `docs/VIEWER_README.md`. ✅ Export/Preview Chat

Blockers (release-critical):
- Asset inspector follow-ups: baseline gallery is live, but we still owe provenance drill-down, open-in-finder actions, and richer previews before calling the inspector complete. Owner: Asset & Sprite System Chat.
- Audio remix + TTS ComfyUI hand-off must write asset registry sidecars and telemetry before we can call audio automation done. Stub endpoints/cache are live under `comfyvn/server/routes/audio.py`; next iteration needs real synthesis plumbing. Owner: Audio & Policy Chat.
- Manga importer parity (panel segmentation → VN timeline) is still flagged 🚧; release requires at least the preview flow and asset registration parity. Owner: Importer Chat.
- Extension loader + Studio slots: Plugin manifests under `extensions/*/manifest.json` now flow through `comfyvn/plugins/loader.py`, exposing safe REST hooks, UI panels, and event subscriptions. `/api/extensions/*` surfaces enable/disable controls, panel descriptors, and static asset delivery. Studio renders enabled panels inside the new Extensions card (see `comfyvn/studio/app.js`). Owner: Plugin Runtime Chat; sample shipped as `extensions/sample_hello`. Reference: `docs/development/plugins_and_assets.md`.
- Marketplace & packaging service: `comfyvn/market/{manifest,packaging,service}.py` defines the shared manifest schema (metadata, permissions, diagnostics, trust envelopes, optional signature digests), builds deterministic `.cvnext` archives, and manages install/uninstall flows guarded by trust-level allowlists (unverified bundles are sandboxed under `/api/extensions/<id>`, verified bundles may expose allowlisted `/api/modder/*` routes). FastAPI mounts `/api/market/{list,install,uninstall,health}` behind feature flags `enable_marketplace` (primary) and `enable_extension_market_uploads` (uploads opt-in). Installations land under `/extensions/<id>` with `.market.json` sidecars capturing package + manifest SHA-256 digests, trust metadata, and timestamps; structured logs write `event=market.install|market.uninstall` to `logs/server.log`. CLI entrypoint: `bin/comfyvn_market_package.py`.

Cross-chat dependencies:
- Asset inspector relies on registry consistency and provenance stamping from Asset Registry + Advisory teams; GUI needs API contract finalised before implementation.
- Manga importer outputs feed GUI timeline + advisory scans; coordinate API schema locks with Roleplay/World Lore and Advisory Chats.
- Export orchestrator (Phase 9) consumes registry + provenance outputs; ensure Export/Packaging Chat participates in validation once inspector + audio provenance land.

Observability & diagnostics
---------------------------

- Crash Reporter: `comfyvn/obs/crash_reporter.py` exposes `capture_exception` for tool scripts and installs a repo-wide `sys.excepthook` via `install_sys_hook()`. FastAPI calls it on startup so unexpected exceptions create JSON crash dumps under `logs/crash/` with stack traces, PID, working directory, and optional context payloads. Helpers return the written path so CLI/GUI surfaces can link users directly to the dump.
- Collaboration service: `comfyvn/collab/{crdt,room}.py` implements a Lamport-clock CRDT covering scene fields, nodes, and script lines while maintaining request-control locks and presence (cursor, selection, typing, capability sets). `CollabRoom.register_headless_client()` lets HTTP tooling join without a WebSocket, marking those entries as `headless` for overlays. `comfyvn/server/core/collab.py` boots the hub with async persistence through `scene_save`, gated by `features.enable_collaboration` (alias `enable_collab`, default `true`). FastAPI exposes `/api/collab/ws` plus REST helpers in `server/routes/collab.py` (`room/{create,join,leave,apply}`, `room/cache`, `health`, `presence/<scene>`, `snapshot/<scene>`, `history/<scene>?since=n`, `flush`), emits structured log lines (`collab.op applied ...`), and publishes `on_collab_operation` on the modder bus. Studio wires the overlay via `comfyvn/gui/services/collab_client.py`/`SceneCollabAdapter`, diffing node-editor edits into CRDT ops and replaying remote snapshots with <200 ms LAN latency.
- Telemetry & anonymisation: `comfyvn/obs/telemetry.py` hosts the `TelemetryStore` singleton that records opt-in feature counters, anonymised custom events, and hashed crash digests in `logs/telemetry/usage.json`. Hashing and payload scrubbing flow through `comfyvn/obs/anonymize.py`, which uses a per-installation BLAKE2s key so identifiers stay consistent locally without leaking raw IDs.
- Consent + routing: Feature flags `enable_observability` (legacy alias `enable_privacy_telemetry`) and `enable_crash_uploader` default to `false` under `config/comfyvn.json → features`. User intent persists in the adjacent `telemetry` section (`telemetry_opt_in`, `crash_opt_in`, `diagnostics_opt_in`, `dry_run`). FastAPI mounts `/api/telemetry/{summary,settings,events,features,hooks,crashes,diagnostics,health,opt_in}`; callers receive hashed `anonymous_id` values, per-feature counters, recent hook samples, health snapshots, and zipped diagnostics bundles (manifest + telemetry snapshot + crash summaries + consent metadata) once diagnostics opt-in is granted.
- Modder hook sampling: `comfyvn/core/modder_hooks.py` taps `TelemetryStore.record_hook_event`, storing the last five anonymised payload samples for each hook alongside counters. Observability dashboards and custom tooling can now introspect hook activity without ingesting raw asset IDs or file paths.
- Structured Logging: `comfyvn/obs/structlog_adapter.py` implements `get_logger(name, **context)` and a `LoggerAdapter`-style `bind`/`unbind` API that emits deterministically sorted JSON lines, keeping log ingestion simple without depending on `structlog`.
- Health doctor: `tools/doctor_phase4.py` probes `/health`, simulates a crash, and verifies structured logging. The script prints a JSON report and exits non-zero when any probe fails, making it safe for desktop troubleshooters and CI smoke jobs.
- Golden contracts: `tests/e2e/test_scenario_flow.py` drives `/api/scenario/*`, `/api/save/*`, `/api/presentation/plan`, and `/api/export/*` against the recorded payloads in `tests/e2e/golden/phase4_payloads.json`. Updating the golden file must be intentional and accompanied by a changelog note for downstream tool authors.
- Docs: `docs/development/observability_debug.md` walks modders through crash triage, structured log capture, doctor usage, and asset registry hook registration for provenance automation.

Theme & World Changer
---------------------

- Templates live in `comfyvn/themes/templates.py`, defining LUT stacks, ambience assets, prompt styles, music sets, and character role defaults for `Modern`, `Fantasy`, `Romantic`, `Dark`, and `Action`.
- `/api/themes/templates` enumerates presets for Studio pickers; `/api/themes/apply` composes deterministic `plan_delta` payloads with `mutations` covering assets, LUTs, music, prompts, and per-character adjustments so previews can diff tone swaps without triggering renders.
- Plan checksums remain stable across identical payloads—use them as cache keys for ambience mixes, generated thumbnails, or queued render batches. Overrides under `overrides.characters.<id>` merge last so leads retain bespoke looks.
- Debug & tooling guidance lives in `docs/development/theme_world_changer.md`, including curl examples and tips on chaining deltas with presentation directives or asset registry automation for modders.

Weather Planner & Transition Pipeline
-------------------------------------

- `comfyvn/weather/engine.py` keeps canonical presets for time-of-day, weather, and ambience, compiling layered backgrounds, light rigs, transitions, particles, and SFX with a stable hash per state. Warnings surface when payloads include unknown values (alias fallbacks are applied automatically).
- `WeatherPlanStore` (see `comfyvn/weather/__init__.py → WEATHER_PLANNER`) tracks the latest plan with incrementing versions and UTC timestamps so exporters can diff state changes without recomputing.
- `/api/weather/state` is mounted via `comfyvn/server/routes/weather.py`, supporting GET (snapshot) and POST (partial updates). Feature flag `enable_weather_overlays` (default **OFF**) lives in `config/comfyvn.json`; toggle it on when deployments want dynamic overlays/LUTs while keeping legacy static backgrounds opt-in.
- Updates log through `comfyvn.server.routes.weather` (structured JSON includes hash, exposure shift, LUT path, particle type) and emit `on_weather_changed` over the modder hook bus with `{state, summary, transition, particles, sfx, lut, bake_ready, flags, meta, trigger}` payloads so contributors can enqueue renders, bake backgrounds, or swap ambience overlays.
- Reference: `docs/WEATHER_PROFILES.md` for preset tables, curl samples, hook payloads, and exporter integration tips.

Prop Manager & Visual Anchors
-----------------------------

- `comfyvn/props/manager.py` defines anchor presets (`root`, `left`, `center`, `right`, `upper`, `lower`, `foreground`, `background`), tween defaults, ensure sidecar dedupe, and condition grammar used across Studio previews and exporters.
- `/api/props/{anchors,ensure,apply}` (gated by feature flag `enable_props`, default **OFF**) share anchor metadata, persist prop sidecars/thumbnails, and evaluate visibility/tween payloads against scenario state.
- `on_prop_applied` hook mirrors the apply response so overlays, automation scripts, or exporters can react without polling. Documentation lives in `docs/PROPS_SPEC.md` with styling tie-ins to `docs/VISUAL_STYLE_MAPPER.md`.

Documentation & packaging:
- Update `README.md`, `docs/UPGRADE_v0.7.md`, and `docs/production_workflows_v0.6.md` (rename/extend to v0.7) to match Studio workflows. Owner: Project Integration (Chat P).
- Cut CHANGELOG entry + docs/CHANGEME for v0.7 tag and circulate release checklist (smoke tests, doctor script, packaging guide) ahead of tagging. Owner: Project Integration.
- Verify runtime storage + installer docs reference the new version; keep `docs/packaging_plan.md` and extension manifest guide in sync post-release.

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
2025-10-24 — Base URL authority (`comfyvn/config/baseurl_authority.py`) now owns host/port resolution for the launcher, GUI, and helper tools. Precedence: explicit `COMFYVN_BASE_URL` → runtime state file → persisted settings (`settings/config.json`) → `comfyvn.json` → default `http://127.0.0.1:8001`. The launcher refreshes the authority after binding and writes the resolved values to `config/runtime_state.json`, keeping parallel launchers and detached helpers in sync.
2025-12-03 — Router inclusion now guards against duplicate mounts: `comfyvn.server.app._include_router_module` collects existing path/method signatures and skips legacy routers that would shadow the new `/api/*` stack, while `/health` and `/status` definitions only register when missing. Companion script `python tools/doctor_phase8.py` instantiates `create_app()` headless, asserts the route catalogue (battle/props/weather/viewer/modder/pov/narrator), validates feature defaults, and fails fast when any surface drifts—embed it in CI checks.

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
- ✅ 2025-10-27 — Scenario graph foundation landed: canonical scene schema (`comfyvn/schema/scenario_schema.json`), deterministic runner (`comfyvn/runner/scenario_runner.py` + seeded RNG), and `/api/scenario/{validate,run/step}` endpoints unblock branching playback tests; authoring GUI + callbacks remain on the backlog.

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
- ✅ 2025-10-21 — Modder hook bus centralised (`comfyvn/core/modder_hooks.py`) with `/api/modder/hooks{,/webhooks,/history}` + WebSocket fanout, scenario runner and asset registry emitters, and the Studio **Debug Integrations** panel surfacing provider health/quota telemetry with masked credentials.
- ✅ 2025-10-28 — Documented `/assets` API, registry helpers, and debug workflows for modders (see `docs/studio_assets.md` + new dev notes) so contributors can script imports, inspect provenance, and extend asset tooling safely.
- ✅ 2025-11-10 — `/assets` listing supports `hash`, `tag(s)`, and `q` filters; modder hook specs now include `on_asset_registered`, `on_asset_meta_updated`, `on_asset_sidecar_written`, and `on_asset_removed`. New debug surfaces (`/assets/debug/{hooks,modder-hooks,history}`, `/assets/{uid}/sidecar`) keep automation in sync, with curl/WebSocket recipes captured in `docs/dev_notes_asset_registry_hooks.md` and `docs/dev_notes_modder_hooks.md`.

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

Status:
- ✅ 2025-10-27 — `/manga/pipeline/start` now provisions production jobs under `data/manga/<job_id>`, executes staged segmentation → OCR → grouping → speaker attribution with configurable providers, and publishes `manifest.json` + log artifacts for Studio dashboards.
- ✅ 2025-10-27 — Provider registry (`comfyvn/manga/providers.py`) lists open-source (Basic/Whitespace segmenter, Tesseract, EasyOCR), ComfyUI I2T workflow, and paid connectors (Azure Vision, Google Vision, OpenAI dialogue attribution). `/manga/pipeline/providers` exposes metadata (paid flags, config schema) for UI wiring.
- ✅ 2025-10-27 — Provider settings accept ComfyUI base URLs/workflows, cloud API keys, and language hints; manifests capture chosen providers per stage for auditing. Jobs continue to run even if a provider falls back, with warnings surfaced in `manifest.json`.

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
- ✅ 2025-10-28 — Scenes inspector now calls `/api/presentation/plan` to render a directive plan preview alongside the JSON, driven by the non-blocking presentation bridge.

Part B — Characters view (lab)

Owner: Persona & Group Chat

Outputs:

Traits editor, portrait/expression linker; LoRA preview hooks

Links to scenes containing this character

Acceptance: Changing portrait/expression reflects in preview and persisted model.

Progress:
- ✅ 2025-10-22 — Trait editor now supports inline edits, portrait swaps, and expression preview syncing; changes persist via `/api/characters/save` and cross-link scenes refresh on save.
- ✅ 2025-11-01 — Character Designer tab (Studio center) surfaces CRUD for name/tags/pose/expression, writes `data/characters/<id>/character.json`, mirrors LoRA attachments to `lora.json`, and triggers hardened renders via `POST /api/characters/render` that auto-register assets (sidecar + thumbnail) in the registry.
- ✅ 2025-11-05 — Center router now persists the active pane via `session_manager`, defaults to the VN Viewer whenever a project is active, and exposes quick action shortcuts (Assets, Timeline, Logs). The Debug & Feature Flags drawer persists `enable_comfy_preview_stream`, `enable_sillytavern_bridge`, and `enable_narrator_mode` to `config/comfyvn.json`, with `MainWindow`, SillyTavern bridges, and the VN Chat overlay honouring the toggles live.
- ✅ 2025-10-30 — POV render pipeline (`/api/pov/render/switch`) backfills missing portraits on perspective changes, caches renders by `(character, style, pose)`, and records ComfyUI sidecars + LoRA payloads directly in the asset registry for modder tooling.

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
- ✅ 2025-12-18 — Advisor debug telemetry, `/api/compute/costs` cost previews, and provider registry stats landed. Docs refreshed (`docs/COMPUTE_ADVISOR.md`, `docs/dev_notes_compute_advisor.md`), and the compute feature flag defaults to false so remote offload stays opt-in.
- Populate curated provider profiles (RunPod, Vast.ai, Lambda Labs, AWS EC2, Azure NV, Paperspace, unRAID, on-prem SSH/NFS) including authentication fields, cost/V RAM metadata, and policy hints for importer workloads (e.g., voice synthesis vs. large CG batch).
- Extend `/compute/advise` to consider importer asset sizes, translation pipeline demands, and cached ComfyUI workflow requirements. Surface recommended provider + cost estimate back into importer job summary.
- Document remote GPU onboarding flows in `docs/remote_gpu_services.md`, including legal caveats around content processing and data residency.
- ✅ 2025-10-22 — `/api/providers/{create,import,export}` support template-based provisioning, sharing, and backups; reference docs in `docs/compute_advisor_integration.md`.
- ✅ 2025-10-21 — `/api/gpu/advise` exposes compute advisor recommendations (local vs remote choice, cost hints, rationale) to importer pipelines and GUI scheduling.
- ✅ 2025-11-09 — Remote installer orchestrator introduced (`comfyvn/remote/installer.py`, `/api/remote/{modules,install}`) with feature flag guard `features.enable_remote_installer` (default off). Planner emits SSH-friendly command lists plus config sync metadata for ComfyUI, SillyTavern, LM Studio, and Ollama, writing status snapshots to `data/remote/install/<host>.json` and timestamped logs to `logs/remote/install/<host>.log`. Dry-run mode returns the plan without mutating state so dispatch tooling can diff steps before executing on remote nodes.

Phase 6 — POV & viewer (center router)

Owner: Studio Shell & Narrative POV Chat

Outputs:
- Center router widget that defaults to the VN Viewer and exposes quick actions for assets/timeline/logs.
- Character Designer stub wired to the shared character registry with refresh hooks for automation.
- `/api/pov/{get,set,fork,candidates}` routes and `POVRunner` filter scaffolding for future LoRA-aware caching.
- Viewer status REST contract so Ren'Py stubs and desktop embeds share the same state payload.

Acceptance:
- Launching Studio shows the VN Viewer center by default with “waiting for project” status.
- Character Designer appears in the center router and refreshes when switching views.
- `/api/pov/candidates` returns filter traces when `debug=true`.
- Config defaults expose new feature flags in `config/comfyvn.json` with all external services disabled.

Docs: `docs/WORKBOARD_PHASE6_POV.md`, `docs/POV_DESIGN.md`, `docs/VIEWER_README.md`, `docs/LLM_RECOMMENDATIONS.md`.

Phase 6 — Battle layer (choice vs sim)

Owner: Project Integration & Narrative Systems Chat

Outputs:
- `comfyvn/battle/engine.py` implements the v0 deterministic formula (`base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)`), reusable breakdown helpers, provenance builders, and resolve narration support with `rounds`/`narrate` controls.
- `/api/battle/{resolve,sim}` FastAPI router (battle resolve always on; sim gated by `enable_battle_sim`, legacy `/simulate` alias) returns enriched payloads including breakdowns, weights, RNG state, provenance, editor prompt, predicted outcome, and optional narration while broadcasting modder hooks (`on_battle_resolved`, `on_battle_simulated`).
- Scenario Runner plugs the new breakdown/log payloads into overlays when battle nodes are flagged, preserving RNG state so designers can share deterministic roll sheets with collaborators.

Acceptance:
- `POST /api/battle/resolve` with `{winner, stats?, seed?, pov?, rounds?, narrate?}` updates the runner state, persists `vars.battle_outcome`, returns `editor_prompt`, deterministic breakdown/provenance, predicted outcome, and optional narration log before emitting `on_battle_resolved`.
- `POST /api/battle/sim` with structured stats returns `{outcome, seed, rng, weights, breakdown[], formula, provenance}` plus narration only when requested; when `seed` is omitted the engine seeds deterministically and exposes the generated value and RNG state in the response/hook.
- `comfyvn.battle.engine` honours `COMFYVN_BATTLE_SEED`, logs breakdowns at DEBUG level, and keeps roll sheets reproducible across runs.

Docs: `docs/BATTLE_DESIGN.md`, `docs/development/battle_layer_hooks.md`, `docs/PROMPT_PACKS/BATTLE_NARRATION.md` (formula-aligned beats), `docs/VISUAL_STYLE_MAPPER.md` (styling tie-ins).

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

Phase 6 — Animation 2.5D

Owner: Animation Systems & Playground Bridge Chats

Outputs:
- `comfyvn/anim/rig/autorig.py` converts layered anchors into a bone hierarchy, infers roles, applies deterministic constraints, and seeds viseme targets (`A/I/U/E/O`) plus idle cycles (breath, blink, micro-mouth motion).
- `comfyvn/anim/rig/mograph.py` composes idle→turn→emote→idle preview loops with guard rails so transitions only run when constraints allow it. Idle cycles fall back when the rig lacks the necessary bones.
- FastAPI routes `comfyvn/server/routes/anim.py` expose `/api/anim/{rig,preview,save}`, register modder hooks (`on_anim_rig_generated`, `on_anim_preview_generated`, `on_anim_preset_saved`), and persist presets to `cache/anim_25d_presets.json`. Feature flag: `features.enable_anim_25d` (default false).

Acceptance:
- `POST /api/anim/rig` returns the rig payload (`bones`, `constraints`, `mouth_shapes`, `idle_cycle`, checksum) with deterministic stats; rejects duplicate anchor IDs.
- `POST /api/anim/preview` emits an idle loop + motion graph preview (≤5 s, ≤24 fps) with state ordering, falling back to idle when guards fail; modder hook includes checksum, frame count, duration, states.
- `POST /api/anim/save` persists named presets, supports overwrite mode, and writes to the preset catalog; hook payload lists preset name, checksum, and filesystem path.

Docs: `docs/ANIM_25D.md`, `docs/dev_notes_anim_25d.md`. Checker profile `p6_anim_25d` enforces feature flag defaults, route presence, and documentation coverage.

Status:
- ✅ 2025-10-21 — `AudioCacheManager` loads/persists JSON entries, keyed by the documented tuple and shared via `audio_cache` singleton for the TTS API.
- ✅ 2025-10-21 — Cache path now resolved through `comfyvn/config/runtime_paths.audio_cache_file`, aligning with the runtime storage overhaul.
- ⚠ Pending: eviction policy, size limits, and instrumentation (hit/miss counters to metrics/logs) before wider rollout.

Part D — Asset dedup cache

Owner: Asset & Sprite System Chat

Outputs:

Hash-indexed asset cache with refcounts + pin/unpin + LRU eviction; rebuild CLI.

Acceptance: Duplicate asset files collapse to one record; pins are preserved after a rebuild.
Debugging: `python scripts/rebuild_dedup_cache.py --assets ./assets` prints processed/duplicate counts and writes the JSON index to the runtime cache directory.
Notes: Cache manager lives in `comfyvn/cache/cache_manager.py`; JSON index defaults to `cache/dedup/dedup_cache.json` via `runtime_paths.cache_dir`.

Status:
- ✅ 2025-10-22 — `CacheManager` stores content hashes, refcounts, and pin state with LRU eviction safeguards for non-pinned blobs.
- ✅ 2025-10-22 — `scripts/rebuild_dedup_cache.py` rebuilds the index from disk while preserving pinned entries and reporting duplicates.
- ✅ 2025-12-22 — Asset ingest queue (`comfyvn/ingest/queue.py`) stages assets through `CacheManager`, pins queued blobs, normalises provider metadata, and releases entries after registry apply. API + modder hook contracts captured in `docs/ASSET_INGEST.md`.
- ⚠ TODO: extend cache integration to legacy import paths that still bypass the queue.

Phase 7 — Advisory, policy, SFW/NSFW

Part A — Liability gate & settings

Owner: Advisory/Policy Chat

Outputs:

First-run & risky-flow gates; setting ack_legal_vN stored

Acceptance: Exports/imports blocked until acknowledged; recorded in settings.
Debugging: `GET /api/policy/status`, `POST /api/policy/ack`, then `POST /api/policy/evaluate` (ensure warnings surface but allow remains true).
Notes: Gate state persisted via `comfyvn/core/policy_gate.py`; the system advises creators while keeping final editorial control in their hands. Exports/imports only hard-stop on unacknowledged legal terms or scanner “block” findings, ensuring users explicitly accept responsibility before distributing builds.

Status:
- ✅ 2025-10-21 — `PolicyGate` persists acknowledgements via `SettingsManager`, tracks `ack_timestamp`, and surfaces overrides for audit.
- ✅ 2025-10-21 — FastAPI router (`comfyvn/server/modules/policy_api.py`) implements `/api/policy/{status,ack,evaluate}` with logging + error paths.
- ✅ 2025-12-22 — License snapshot gate stores normalised hub EULAs via `comfyvn/advisory/license_snapshot.py`, persists per-user acknowledgements, emits `on_asset_meta_updated`, and exposes `/api/advisory/license/{snapshot,ack,require}` so connectors block downloads until the current hash is acknowledged.
- ⚠ Outstanding: studio UX for multi-user acknowledgement history and automated reminder surfaces.

Part B — Advisory scans

Owner: Advisory/Policy Chat

Outputs:

/api/advisory/scan (target id, license_scan=1)

Findings logged to advisory_logs; quick fixes (replace, remove, request waiver)
Debugging: POST `/api/advisory/scan`, list via `/api/advisory/logs`, resolve with `/api/advisory/resolve`; WARN entries in `logs/server.log` confirm new issues.
Notes: See docs/studio_phase7_advisory.md for scan heuristics, resolution flow, and logging. Plugin registration (licence/IP/optional NSFW classifier) is documented in `docs/development/advisory_modding.md`, including debug hooks for modders and automation contributors.

Acceptance: Import of non-open assets flagged; UI shows resolution flow.

Status:
- ✅ 2025-10-21 — `/api/advisory/scan` appends issues through `comfyvn/core/advisory.log_issue`, persisted to advisory logs for GUI consumption.
- ✅ 2025-10-27 — Scanner facade loads SPDX/IP/NSFW plugins via `comfyvn/advisory/scanner.py`, normalises severities to `info|warn|block`, and exposes optional classifier registration hooks for downstream tooling.
- ✅ 2025-10-21 — `/api/policy/filter-preview` and `content_filter.filter_items` emit WARN entries and integrate with advisory logs, satisfying filter preview tooling.
- ✅ 2025-10-22 — Policy enforcer (`comfyvn/policy/enforcer.py`) runs before import/export flows, persists JSONL audits under `logs/policy/enforcer.jsonl`, and blocks when scanners emit `block`-level findings.
- ✅ 2025-10-22 — Audit router (`GET /api/policy/audit`) surfaces chronological enforcement events, exportable reports, and feeds the new `on_policy_enforced` modder hook for contributor dashboards.
- ⚠ TODO: auto-remediation hooks (replace/remove/waiver) must emit structured events and surface in Studio dashboards.

Part C — SFW/NSFW filters

Owner: Advisory/Policy + Server Core

Outputs:

Server-side filtering on content queries by meta flags

UI toggle & per-export mode

Acceptance: Toggling filters affects queries/preview/export as expected.
Debugging: `POST /api/policy/filter-preview` with sample metadata, confirm warnings surface and `content_mode` matches `GET /api/policy/filters`.
Notes: Filter modes (`sfw|warn|unrestricted`) stored in `data/settings/config.json`; overrides keep items accessible while logging advisory warnings. Rating gate issues ack tokens when SFW blocks high-risk content; callers record the acknowledgement via `/api/rating/ack` and replay requests with the confirmed token.

Status:
- ✅ 2025-10-21 — `comfyvn/core/content_filter.ContentFilter` reads/writes `filters.content_mode` and classifies assets, logging advisory warnings.
- ✅ 2025-10-21 — `/api/policy/filters` exposes GET/POST plus preview, enabling GUI toggles and importer checks.
- ✅ 2025-11-12 — Rating matrix + SFW gate: `comfyvn/rating/classifier_stub.py`, `/api/rating/{matrix,classify,overrides,ack,acks}`, LLM/export gating with ack tokens, manifest embeddeds, modder hook events (`on_rating_*`). Feature flags `enable_rating_api|enable_rating_modder_stream` guard routes/emitters.
- ⚠ Planned: extend classification with ML/heuristic scores and integrate per-export overrides.

Part D — POV + Public APIs router

Owner: Phase 7 Integration (POV + Providers Chat)

Outputs:

Public provider catalog endpoints (GPU, image/video, translation/OCR/speech, LLM)
POV worldline CRUD routes and battle sim endpoints
Documentation refresh covering pricing anchors, debug hooks, and modder guidance

Acceptance: Feature-flagged public routes return curated pricing + review notes; dry-run adapters log deterministic payloads without firing network traffic; README/architecture/LLM/POV docs updated with pricing anchors and debug hooks.
Debugging: Hit `/api/providers/gpu/public/catalog` (should echo `feature.enabled=false` until toggled). POST `/api/providers/gpu/public/runpod/health` with `{ "config": {"token": "dummy"} }` to confirm dry-run responses. `/api/pov/worlds` should list + activate worlds; `/api/battle/resolve` echoes `editor_prompt: "Pick winner"` with breakdown/provenance and `/api/battle/sim` returns deterministic roll sheets when `enable_battle_sim` is enabled. Secrets merged from `config/comfyvn.secrets.json`.
Notes: Routes depend on feature flags (`enable_public_gpu`, `enable_public_image_providers`, `enable_public_video_providers`, `enable_public_translate`, `enable_public_llm`, `enable_battle`, `enable_battle_sim`, `enable_props`, `enable_themes`, `enable_weather_overlays`). Settings → Debug & Feature Flags now exposes dedicated toggles for public image/video providers; UI changes keep the legacy `enable_public_image_video` flag in sync for automation. Catalog + dry-run adapters live in `comfyvn/public_providers/{image_stability,image_fal,video_runway,video_pika,video_luma}.py`, and `comfyvn/server/routes/providers_image_video.py` registers `/api/providers/{image,video}/{catalog,generate}` with task-registry logging for modders. Docs/stubs live under `docs/WORKBOARD_PHASE7_POV_APIS.md` with pricing tables sourced 2025-11; live API calls remain disabled until credentials + compliance sign-off.

Status:
- ✅ 2025-11-08 — Added `comfyvn/public_providers/{catalog,gpu_runpod,video_runway,translate_google}.py` plus `/api/providers/*/public` FastAPI routers with feature flag guards and deterministic dry-run helpers.
- ✅ 2025-11-10 — Split image/video feature flags (`enable_public_image_providers`, `enable_public_video_providers`), wired new adapters `comfyvn/public_providers/{image_stability,image_fal,video_pika,video_luma}.py`, mounted `/api/providers/{image,video}/{catalog,generate}` in `comfyvn/server/routes/providers_image_video.py`, and surfaced toggles in the Settings panel. Dry-run calls now register jobs with cost estimates for modder debugging, and docs (`README.md`, `architecture_updates.md`, `docs/dev_notes_public_media_providers.md`) cover payloads, pricing anchors, and secrets guidance.
- ✅ 2025-12-14 — Accessibility stack v2: introduced `comfyvn/accessibility/ui_scale.py` and extended `accessibility_manager` to persist global UI scale (100–200 %) plus per-view overrides. VN Viewer registers with the scale manager while the Settings panel exposes presets, viewer-only overrides, filters, high-contrast toggle, and subtitles. Input defaults now cover numeric choices, narrator/overlay toggles, and editor pick-winner bindings; `InputMapManager` gained export/import helpers with `reason` metadata for modder hooks. Feature flag `enable_accessibility` joins the existing controls/api/controller toggles. FastAPI now serves `/api/accessibility/{state,set,filters,subtitle,export,import,input-map,input/event}` and `/api/input/{map,reset}`; structured logs stream to `logs/accessibility.log`. Docs refreshed (`README.md`, `architecture.md`, `architecture_updates.md`, `CHANGELOG.md`, `docs/ACCESSIBILITY.md`, `docs/INPUT_SCHEMES.md`, `docs/development/accessibility_input_profiles.md`).
- ✅ 2025-12-01 — `/api/pov/worlds` exposes list/create/update/activate endpoints for worldline management; `/api/battle/{resolve,sim}` surface the v0 formula, editor prompt, roll breakdowns, provenance, and optional narration (simulation gated by `enable_battle_sim`).
- ✅ 2025-11-08 — README, architecture, CHANGELOG, `docs/POV_DESIGN.md`, `docs/THEME_TEMPLATES.md`, `docs/WEATHER_PROFILES.md`, `docs/BATTLE_DESIGN.md`, and `docs/LLM_RECOMMENDATIONS.md` now include pricing anchors, provider review notes, debug hooks, and secrets/feature flag guidance.
- ⚠ TODO: expand battle formula (DEF/LCK/traits), add WebSocket streaming for roll breakdowns, and wire provider-backed SFX/VFX triggers once asset pipelines are approved.

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
- ✅ 2025-10-27 — `comfyvn/exporters/renpy_orchestrator.py` orchestrates multi-scene exports, asset staging, dry-run diffs, and publish zips; CLI + `/api/export/renpy/preview` share the implementation.

Next:
- Wire Ren’Py lint/dry-run execution (`renpy.sh launcher lint`) into the publish preset and persist logs under `exports/renpy/validation.log`.
- Surface job progress (per-scene events) via `/jobs/*` and enrich provenance metadata for later audits.
- Extend the orchestrator to stream progress events to Studio once the job queue integration lands.

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

Extension sync (copy/update); health check; session context sync; persona import

Acceptance: Personas/world lore can be pulled and linked into Scenes; session sync returns a reply payload in ≤2 s on the mock transport.

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

Status:
- ✅ 2025-10-26 — Introduced `comfyvn/translation/manager.py`, GET/POST `/api/i18n/lang`, and stubbed POST `/api/translate/batch`; active/fallback language persisted to `config/comfyvn.json` with runtime fallback helper `translation.t`.
- 📚 Developer notes captured in `docs/development_notes.md` (asset hooks, debug toggles, localisation overrides).
- 🛠️ Blueprint 2025-11-07 — Public Translation/OCR/Speech adapters documented (`docs/development/public_translation_ocr_speech.md`), feature flags planned (`enable_public_translation_apis`, `enable_public_ocr_apis`, `enable_public_speech_apis` default false), and diagnostics routes specced at `/api/providers/{translate,ocr,speech}/test` with dry-run behaviour until adapters ship.

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

- QA playtest harness (`comfyvn/qa/playtest/headless_runner.py`) persisting deterministic `.trace.json` + `.log` pairs under `logs/playtest/`, surfaced via `/api/playtest/run` (feature flag `enable_playtest_harness`).
- Golden diff helper (`comfyvn/qa/playtest/golden_diff.py`) and pytest coverage (`tests/test_playtest_headless.py`, `tests/test_playtest_api.py`) to guard seeded branch behaviour.
- Modder hook extensions: `on_playtest_start`, `on_playtest_step`, `on_playtest_finished` emit run metadata (seed, digest, persist flags) for dashboards and webhook relays.

Acceptance:
- CI badge green; minimal flakiness.
- `/api/playtest/run` returns deterministic digests for identical `{scene, seed, pov, variables}` payloads and honours `dry_run` (no trace/log on disk).
- Persisted runs emit `.trace.json` + `.log` files with matching digest prefixes under `logs/playtest/` and broadcast the new modder hook envelopes.

4) Ownership map (chats → modules)

Server Core Production: app.py, /server/modules/*, runtime APIs, streaming, variables/choices, export orchestrator

GUI Code Production (Studio): studio_window.py, views/*, ServerBridge, graphs, inspectors

v0.5 Scaffold & DB: migrations, db_manager.py, schema/versioning

Asset & Sprite System: registry, thumbnails, sidecars, asset browser

Roleplay/World Lore: roleplay import, world indexing, persona linking

Importer: VN/manga importers, file ingestion pipeline

Remote Compute & GPU Access: gpu_manager, providers registry, compute advisor
- Advisor now emits optional debug payloads (pixels, VRAM demand, queue thresholds) so Studio can explain why jobs stayed local.
- `JobScheduler.preview_cost()` powers `/api/compute/costs`, returning numeric breakdowns plus human readable hints without touching providers.
- Provider registry exposes `stats()` for dashboards (`/api/providers?debug=1`) and compute REST responses always echo the `enable_compute` feature flag so remote offload stays explicitly opt-in.

Audio & Effects: TTS, remix, audio cache

Advisory/Policy: liability gate, scans, SFW/NSFW filters, provenance policy

Export/Packaging: Ren’Py exporter, bundle exporter, Steam/itch packagers, manifests

SillyTavern Bridge: extension sync, persona/world import

Code Updates: patchers, repair scripts, version bumps

Project Integration: docs, changelogs, roadmap, release notes

Steam/itch publish pipeline:
- `comfyvn/exporters/publish_common.py` provides deterministic ZIP builders, license manifest extraction, slug helpers, and provenance log appenders shared by the platform-specific packagers.
- `comfyvn/exporters/steam_packager.py` and `comfyvn/exporters/itch_packager.py` wrap Ren'Py exports into reproducible archives with `publish_manifest.json`, `license_manifest.json`, provenance sidecars, optional debug hook listings, and per-platform build folders.
- Feature flags `enable_export_publish`, `enable_export_publish_steam`, and `enable_export_publish_itch` (all default `false`) gate `POST /api/export/publish`. When enabled, the route rebuilds the Ren'Py project, writes Steam/itch packages, and records structured entries to `logs/export/publish.log`.
- `comfyvn/exporters/web_packager.py` emits deterministic Mini-VN web bundles containing hashed assets, `index.html`, `content_map.json`, `preview/health.json`, and optional modder hook catalogues. Feature flag `enable_publish_web` gates `/api/publish/web/{build,redact,preview}`. Redaction options (`strip_nsfw`, `remove_provenance`, `watermark_text`, `exclude_paths`) only affect the redacted assets, keeping safe artefacts byte-identical for diffability. Preview responses surface health status plus pointers to the generated manifest/redaction sidecars.
- Dry-run callers receive diff payloads without touching disk, while completed runs emit modder hooks `on_export_publish_preview` / `on_export_publish_complete` so automation can mirror release notes and checksums. See `docs/development/export_publish_pipeline.md` for curl samples and expected JSON contracts.

Rule: Don’t modify modules outside your ownership without coordinating via Code Updates and Project Integration.

5) Data contracts (concise)

Scene JSON: { id, title, nodes:[ {id,type("text"|"choice"|"action"),content,directives{},conditions[],next[],meta} ], meta }

Character JSON lives at `data/characters/<id>/character.json` and tracks `{ id, name, tags[], pose?, expression?, avatars[], loras[], meta{}, notes? }`. Per-character LoRA attachments are mirrored to `data/characters/<id>/lora.json` for hardened bridge loading, while legacy flat files remain for backwards-compatible tooling.

Timeline JSON: { id, name, scene_order[], meta }
World JSON: { id, name, summary, tone, rules{}, locations{}, factions{}, lore{}, prompt_templates{} }

Ren'Py export manifest (`export_manifest.json`): {
  project{},
  timeline{},
  generated_at,
  output_dir,
  script{path,labels[]},
  assets{backgrounds[], portraits[]},
  missing_assets{},
  gate{},
  pov{
    mode("disabled"|"single"|"master"|"forks"|"both"),
    menu_enabled(bool),
    active|null,
    default|null,
    routes:[ { id, name, slug, entry_label, scene_labels[], scenes[] } ],
    forks:[ { id, name, slug, manifest, script, game_dir } ]
  }
}

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
