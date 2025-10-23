🚀 Overview

This update transforms ComfyVN from a static scene exporter into a multi-layer, interactive VN engine that merges SillyTavern-style roleplay logs, ComfyUI rendering, and Ren’Py exports under one adaptive framework.

**Base URL** defaults to first free in `[8001, 8000]` (auto-discovered by tools).

Studio highlights for this drop:

- Detached server launches now shell out to `python -m uvicorn comfyvn.app:app`, inheriting the unified base authority (`config/baseurl_authority.py`) so Windows launches stop failing with `ModuleNotFoundError: comfyvn`.
- Panel catalogue gains a **VN Loader** dock (`comfyvn/gui/panels/vn_loader_panel.py`) that pulls `/api/vn/projects`, rebuilds compiled story bundles, surfaces scene metadata, and pipes the payload into the Mini-VN fallback or a full Ren'Py launch without leaving Studio.
- Tools menu now exposes an **Import Processing** submenu with an OS file picker, SillyTavern presets, and the existing Import Manager panels (`comfyvn/gui/panels/json_endpoint_panel.py`). Quick presets cover persona/lore/chat payloads, FurAffinity drops, roleplay archives, and now link directly to the External Tool Installer dock for remote module plans.
- Dock widgets now expose a shared context menu (Close / Move to Dock Area) and stable workspace save-state naming; see `docs/DOCKING_AND_LAYOUT.md` for workflow tips.
- Settings is available as a modal dialog (Tools → Settings Window) while the legacy dock stays for advanced workflows.
- SillyTavern bridge settings now expose host, port, and plugin base controls in Studio Basics; `/st/health` and import flows honour the configured base URL, and `/st/import` responds to browser preflights so the bundled extension can post payloads without extra configuration.
- CLI helpers (`tools/check_current_system.py`, `tools/doctor_phase_all.py`) reuse the new `discover_base()` helper so scripted diagnostics honour the same rollover order (CLI override → env → public base → configured ports → fallback).

### Included Worlds (Base)
- **Grayshore** — CC0. Coastal sandbox; fog lanes and drowned forts.
- **The Veiled Age** — Public Domain contributions. Masks, oracles, city-states.
- **Throne of Echoes** — CC0 original. Summoned legends in a modern city.

**Licensing note:** Original files are CC0. If you add CC-BY images/audio, keep attribution in the asset sidecar and in the Credits.
- ComfyUI jobs that include `metadata.asset_pipeline` now save PNGs + JSON sidecars straight into `exports/assets/worlds/<world_id>/<type>/...` and keep `meta/assets_index.json` up to date for that world.
- World Manager auto-loads the seeded JSON summaries under `defaults/worlds/`, character modules pull starter rosters from `defaults/characters/`, and the Timeline view bootstraps `* Openers` sequences from the scene samples in `data/worlds/`.

Highlights:

🛡️ Legal & Creative Responsibility
- You retain full creative freedom over the stories, assets, and exports you craft with ComfyVN. The platform provides guardrails—like the advisory scanner and liability gate—to surface risks, not to dictate content.
- Before distributing builds, acknowledge the legal terms once per installation (Studio: **Settings → Advisory**, CLI: `scripts/export_bundle.py` prompts on block-level findings). This acknowledgement records that you accept all downstream responsibility for compliance with licences, ratings, and local regulations.
- Flat → Layers pipeline (`docs/FLAT_TO_LAYERS.md`) documents the rembg/SAM/MiDaS workflow, provenance sidecars, `tools/depth_planes.py` helper, and Playground hooks for interactive mask refinement.
- Block-level advisory findings halt exports; warnings flag items for manual review while keeping your workflow unblocked. See `docs/development/advisory_modding.md` for plugin hooks, troubleshooting, and override workflows.
- Contributors shipping mods or automation scripts should reference the debug/API matrix in the same doc to understand available hooks, expected audit trails, and how to publish their own scanners without restricting user choice.
- Studio bundle flow now surfaces `GET /api/export/bundle/status` (feature flag + gate probe) and `POST /api/advisory/scan` (deterministic findings: info/warn/block). `scripts/export_bundle.py` returns exit `3` when `enable_export_bundle=false` and prints the enforcement log path on success. See `docs/ADVISORY_EXPORT.md` for full workflow, CLI JSON contract, and modder hooks.

🔒 Rating Matrix & SFW Gate
- `comfyvn/rating/classifier_stub.py` ships a conservative ESRB-style matrix (`E/T/M/Adult`) that scores prompts, metadata, and tags. Reviewer overrides persist to `config/settings/rating/overrides.json`, ensuring manual calls stay sticky across restarts.
- `/api/rating/{matrix,classify,overrides,ack,acks}` exposes review workflows. Classification returns `{rating, confidence, nsfw, ack_token}` so Studio and automation scripts can present warnings or request acknowledgement before continuing. Feature flag: `features.enable_rating_api`.
- SFW mode now gates high-risk prompts and exports by default. `/api/llm/test-call` and the Ren'Py orchestrator raise HTTP 423 with the issued `ack_token` until `/api/rating/ack` records the reviewer acknowledgement. CLI parity: `scripts/export_renpy.py --rating-ack-token <token> --rating-acknowledged`.
- Export manifests embed the resolved rating (`manifest.rating`) plus gate status, letting downstream pipelines enforce distribution policies or surface the info alongside provenance metadata.
- Modder hook bus gained `on_rating_decision`, `on_rating_override`, and `on_rating_acknowledged` (feature flag `enable_rating_modder_stream`). Subscribing via `/api/modder/hooks` or the WS stream lets tooling react to rating changes without polling the new API.

🧩 New Roleplay Import System

🌐 Community Connectors (F-List & FurAffinity)
- `/api/connect/flist/consent` captures opt-in rights + NSFW allowances before any import; all connector routes hard-stop with 403 until this record exists. Feature flag `enable_persona_importers` stays **false** by default so teams can stage the flow safely.
- `POST /api/connect/flist/import_text` normalises F-List markdown/exports into persona schemas (species, pronouns, preferences, kink taxonomy). Responses surface `debug.sections`, `warnings`, `nsfw.trimmed`, and emit `on_flist_profile_parsed` for dashboards or modder tooling.
- `POST /api/connect/furaffinity/upload` accepts user-supplied images only (base64 blobs, optional credits). Uploads hash assets, emit provenance sidecars, trim NSFW tags unless the global NSFW flag + consent allow them, and fire `on_furaffinity_asset_uploaded`.
- `POST /api/connect/persona/map` merges parsed text + optional Phase-6 image traits, persists persona/provenance JSON, and double-emits `on_connector_persona_mapped` + `on_persona_imported` so existing automations stay in sync.
- Docs: `docs/COMMUNITY_CONNECTORS.md`, `docs/NSFW_GATING.md`, and `docs/dev_notes_community_connectors.md` cover API contracts, curl recipes, debug hooks, and consent storage details. Verification: `python tools/check_current_system.py --profile p7_connectors_flist_fa --base http://127.0.0.1:8001`.

💬 SillyTavern Chat Import Pipeline
- Feature flag `enable_st_importer` (default **false**) unlocks the new importer endpoints so projects opt in deliberately. Toggle it via **Settings → Debug & Feature Flags** or by editing `config/comfyvn.json`.
- `POST /api/import/st/start` accepts SillyTavern `.json` or `.txt` exports (upload, inline text, or HTTP(S) URL), normalises the transcript (`imports/<runId>/turns.json`), maps it into scenario graphs (`imports/<runId>/scenes.json` + `data/scenes/<id>.json`), and links the resulting scenes to `data/projects/<projectId>.json`.
- `GET /api/import/st/status/{runId}` reports `{phase, progress, scenes, warnings, preview}` so dashboards can track ingest runs without peeking at filesystem artefacts. Status records update as the importer advances from `initializing` → `parsed` → `mapped` → `completed` (or `failed`).
- Modder hook bus emits `on_st_import_started`, `on_st_import_scene_ready`, `on_st_import_completed`, and `on_st_import_failed`, carrying run metadata, scene IDs, participant lists, and warnings for automation. Subscribe via `/api/modder/hooks/ws` to stream progress into CI or dashboards.
- Docs: `docs/ST_IMPORTER_GUIDE.md` details export steps, API payloads, warnings, and debugging tips. Development notes live in `docs/dev_notes_st_importer.md`. Checker: `python tools/check_current_system.py --profile p9_st_import_pipeline --base http://127.0.0.1:8001`.

📥 Asset Ingest Queue & Dedup
- `comfyvn/ingest/{queue,mappers}.py` stages community assets under `data/ingest/staging/`, hashes them through the shared cache manager, and normalises provider metadata before hitting the registry. Feature flag `enable_asset_ingest` ships **false** so teams opt in intentionally.
- FastAPI router `/api/ingest/{queue,status,apply}` handles staging, dedup inspection, and registry apply. Status calls surface queue summaries plus optional cache snapshots for dashboards or smoke tests.
- Remote pulls are rate-limited (~1 request every 3 s) and restricted to Civitai/Hugging Face domains when `terms_acknowledged=true`; FurAffinity remains upload-only to stay ToS compliant.
- Modder hooks `on_asset_ingest_enqueued`, `on_asset_ingest_applied`, and `on_asset_ingest_failed` broadcast queue outcomes so automation can react without scraping state files.
- Docs: `docs/ASSET_INGEST.md` (API + workflow) and `docs/dev_notes_asset_ingest.md` (debug cookbook). Checker: `python tools/check_current_system.py --profile p7_asset_ingest_cache --base http://127.0.0.1:8001`.

🧭 Dungeon Runtime & Snapshot Hooks
- `/api/dungeon/{enter,step,encounter_start,resolve,leave}` exposes a seeded grid crawler and DOOM-lite stage bridge so designers can wander a dungeon, trigger hazards, and mint Snapshot→Node/Fork payloads. Feature flag `enable_dungeon_api` defaults **false**; flip it in `config/comfyvn.json` when playtesting.
- Responses surface `room_state` (`{desc, exits, hazards, loot}`), deterministic `snapshot` payloads, and `vn_snapshot` envelopes with traversal history + encounter logs so Storyboard nodes inherit the correct event anchors.
- Modder hooks `on_dungeon_enter`, `on_dungeon_snapshot`, and `on_dungeon_leave` mirror every step/snapshot for dashboards or automated exporters. Hook payloads include the supplied VN context (`scene`, `node`, `pov`, `worldline`, `vars`) so listeners can align snapshots with timeline beats.
- Docs: `docs/DUNGEON_API.md` (contracts, curl recipes, diagrams) and `docs/dev_notes_dungeon_api.md` (debug + hook cookbook). Verification: `python tools/check_current_system.py --profile p3_dungeon --base http://127.0.0.1:8001`.

🎭 2.5D Animation Rig (Auto-Rig, Motion Graph, Visemes)
- `/api/anim/{rig,preview,save}` converts layered anchors to a deterministic bone tree, emits idle breath/blink loops, sequences turn/emote states, and persists named presets reusable in Designer/Playground. Feature flag `enable_anim_25d` defaults **false**.
- `comfyvn/anim/rig/autorig.py` infers bone roles, clamps transforms to ≤90 % of permitted travel, and seeds mouth shapes `A/I/U/E/O` for lightweight lip-sync. `comfyvn/anim/rig/mograph.py` guards transitions so turn/emote passes only execute when constraints allow it.
- Hooks: `on_anim_rig_generated`, `on_anim_preview_generated`, `on_anim_preset_saved` (REST + WS) give modders deterministic payloads for dashboards or automation.
- Presets live in `cache/anim_25d_presets.json`; share them between machines or commit to a content repo. Docs + debug recipes: `docs/ANIM_25D.md`, `docs/dev_notes_anim_25d.md`.

🌐 Live WebSocket JobManager

🪟 Expanded GUI with Tray Notifications

🌐 Web Publish & Redaction Preview
- Build deterministic Mini-VN web bundles via `/api/publish/web/{build,redact,preview}` with asset hash cache-busting, NSFW redaction toggles, provenance scrubbing, and QA health snapshots. Documentation: `docs/PUBLISH_WEB.md`.

📦 Importing Existing VNs
- On-demand installer: `python tools/install_third_party.py --list` to review licences/hashes, then `--tool <name>` or `--all --yes` to fetch binaries into `third_party/` (no repo commits, acknowledgement required).
- Health check: `python tools/doctor_extractors.py --table` prints installed versions, shim status, and warns when Wine/.NET are missing.
- Extraction wrapper: `python tools/vn_extract.py /path/to/game --plan-only` to preview, `--dry-run` to capture logs/licence snapshots without running the extractor, and full runs emit `imports/<game>/raw_assets/` plus `extract_log.json`.
- Debug hooks: both installer (`--info <tool>`) and wrapper (`--engine`, `--tool`, `--clean`) expose CLI overrides for automation; see `docs/EXTRACTORS.md` for end-to-end instructions and ToS notes.

🌍 Enhanced World + Audio + Persona sync

⚙️ Unified Logging, Config, and Async Safety

🧱 Fully modular directory structure

🎨 Theme Kits & Swap Wizard
- Fourteen legal-clean kits (`ModernSchool`, `UrbanNoir`, `Gothic`, `Cosmic`, `Cyberpunk`, `Space`, `PostApoc`, `HighFantasy`, `Historical`, `Steampunk`, `Pirate`, `Superhero`, `Mecha`, `Cozy`) coordinate LUT stacks, ambience assets, music packs, camera defaults, prompt flavors, props, and tag remaps in `comfyvn/themes/templates.py`.
- Feature flag `enable_themes` defaults **false**; flip it in `config/comfyvn.json` to expose `/api/themes/{templates,preview,apply}`. Preview composes checksum-stable deltas (no writes), while apply forks or updates a VN Branch worldline so OFFICIAL⭐ stays untouched.
- Responses surface `mutations`, palette/camera previews, anchor preservation, and style tags—perfect for diff viewers, automation queues, or cache keys. Checksums let you skip redundant renders or advisory scans.
- Modder hooks `on_theme_preview` and `on_theme_apply` broadcast plan payloads plus branch metadata for dashboards or OBS overlays. Full payload docs, curl recipes, and debug tips live in `docs/THEME_SWAP_WIZARD.md`; flavor notes and palettes live in `docs/THEME_KITS.md` with shared vocabulary in `docs/STYLE_TAGS_REGISTRY.md`.

🌦️ Weather, Lighting & Transitions
- `comfyvn/weather/engine.py` compiles world state (`time_of_day`, `weather`, `ambience`) into deterministic background-layer stacks, light rigs, LUT metadata, transition envelopes, particle payloads, and ambience SFX. `WeatherPlanStore` exposes versioned snapshots with timestamps, hashes, and bake flags so exporters can diff quickly.
- `/api/weather/state` (GET/POST) updates or reads the shared planner without blocking the GUI. Feature flag `enable_weather_overlays` (default `false`) lives under `config/comfyvn.json → features`; Studio surfaces the switch under **Settings → Debug & Feature Flags**.
- Every plan update emits `on_weather_changed` over the modder hook bus with `{state, summary, transition, particles, sfx, lut, bake_ready, flags, meta}` so automation scripts can queue renders, swap LUTs, or bake overlays. Watch `logs/server.log` (logger name `comfyvn.server.routes.weather`) for structured updates that include hash, exposure shift, particle type, and LUT path.
- Quick curl sample:
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/weather/state \
    -H 'Content-Type: application/json' \
    -d '{"weather": "rain", "time_of_day": "dusk"}' | jq '.scene.summary'
  ```
- Docs: `docs/WEATHER_PROFILES.md` captures presets, payload schema, feature flag setup, and modder automation tips; changelog coverage keeps exporters aligned with hash/version expectations.

🎭 Props & Visual Anchors
- `comfyvn/props/manager.py` centralises prop ensures, anchor presets, tween defaults, and condition grammar so Studio previews and exporters can reuse the same placement logic.
- `/api/props/ensure` (feature gated by `enable_props`, default `false`) writes deterministic sidecars + thumbnails while deduping repeated ensures. `/api/props/apply` evaluates anchors against scenario state and returns `{visible, tween, evaluations, thumbnail, applied_at}`.
- `GET /api/props/anchors` shares normalised anchor definitions (`root`, `left`, `center`, `right`, `upper`, `lower`, `foreground`, `background`) and default tween payloads for UI drop-downs.
- Hook `on_prop_applied` mirrors the apply response so OBS overlays, automation scripts, or exporters can react in real time. Docs: `docs/PROPS_SPEC.md` (API schema, anchors) and `docs/VISUAL_STYLE_MAPPER.md` (style tags shared with battle outcomes).

📊 Performance Budgets & Profiler
- `comfyvn/perf/budgets.py` gates CPU/VRAM consumption with queue caps and lazy asset eviction, while `comfyvn/perf/profiler.py` tracks spans + peak deltas for dashboard reporting. Both ship as shared singletons exposed via `from comfyvn.perf import budget_manager, perf_profiler`.
- Feature flags live under `config/comfyvn.json → features`: `enable_perf_budgets` and `enable_perf_profiler_dashboard` remain **OFF** by default so production builds opt-in deliberately. Call `feature_flags.refresh_cache()` after toggling in long-lived processes.
- New REST surface `/api/perf/*` covers `GET /api/perf/budgets`, `POST /api/perf/budgets/apply`, job lifecycle helpers (`/api/perf/budgets/jobs/{register,start,finish,refresh}`), and lazy asset controls (`/api/perf/budgets/assets/{register,touch,evict}`) alongside profiler marks (`POST /api/perf/profiler/mark`) and dashboards (`GET /api/perf/profiler/dashboard?limit=5`). cURL cookbook and payload schema live in `docs/development/perf_budgets_profiler.md`.
- `/jobs/submit` now annotates responses with `status=delayed` when the budget manager defers work; poll `/jobs/poll` (or `/api/perf/budgets/jobs/refresh`) to watch transitions back to `queued` before dispatching heavy workloads.
- Modder hooks `on_perf_budget_state` and `on_perf_profiler_snapshot` broadcast limit updates, queue transitions, lazy asset unloads, spans, and dashboard snapshots. Subscribe via `/api/modder/hooks` or `ws://…/api/modder/hooks/ws` to drive external dashboards.
- Logs: structured budget decisions flow through `comfyvn.perf.budgets` and `comfyvn.server.routes.perf`, while profiler marks hit `comfyvn.perf.profiler`. Watch `logs/server.log` when validating deployments.

🧩 Extension Loader & Studio Panels
- Plugin manifests discovered under `extensions/*/manifest.json` are validated by `comfyvn/plugins/loader.py`, enabling safe REST hooks (`routes`, `events`) and Studio panel registrations (`ui.panels`). Invalid manifests are rejected with detailed errors surfaced via `/api/extensions`.
- Server routes are mounted automatically: extension-scoped endpoints land under `/api/extensions/{id}` while global routes honor absolute paths (e.g. `/hello`). Studio surfaces enabled panels in the **Extensions** card by fetching `/api/extensions/ui/panels` and injecting module scripts returned by `/api/extensions/{id}/ui/...`.
- Modders can toggle plugins without restarts (`POST /api/extensions/{id}/{enable|disable}`) and inspect mounted assets via `/api/extensions`. A sample implementation ships in `extensions/sample_hello/` showcasing a `/hello` route and a Studio “Hello Panel” UI slot.
- Extended documentation: `docs/development/plugins_and_assets.md` covers manifest schema, panel helpers, asset registry endpoints, and debugging techniques for contributors.

🛒 Extension Marketplace & Packaging
- The marketplace toolkit lives under `comfyvn/market/{manifest,packaging,service}.py`. The manifest schema now normalises author lists, surfaces contribution summaries (routes, events, UI panels, hooks, diagnostics), and records optional `trust.signature` digests so verified bundles prove provenance. The packaging helper emits deterministic `.cvnext` archives (stable timestamps & permissions) and rejects mismatched signatures before writing the package.
- Feature flag `enable_marketplace` gates the FastAPI surface (legacy `enable_extension_market` remains a fallback) while `enable_extension_market_uploads` keeps install/uninstall opt-in. Both default **OFF** inside `config/comfyvn.json`; toggle via Settings → Debug & Feature Flags or edit the JSON then call `feature_flags.refresh_cache()` for long-lived workers.
- REST surfaces mount under `/api/market/*`: `GET /api/market/list` (catalog metadata + installed state, permission glossary, modder hook catalogue), `POST /api/market/install` (zip path payload, optional `trust` override), `POST /api/market/uninstall` (extension id), and `GET /api/market/health` (trust breakdown, last error). Install/uninstall continue to emit structured logs (`event=market.install|market.uninstall`) with package digests for audit trails.
- Pack extensions with `bin/comfyvn_market_package.py <extension-root>` (or `python -m comfyvn.market.packaging`). The CLI normalises manifests, enforces sandbox allowlists (unverified bundles remain scoped to `/api/extensions/<id>`), verifies `trust.signature` digests when present, and prints both package + manifest SHA-256 values so reproducible builds are easy to track.
- Manifests declare permissions via known scopes (`assets.read`, `hooks.listen`, `ui.panels`, `api.global`, etc.) and list expected modder hooks (`hooks: [...]`) so contributors can wire dashboards or automation against `docs/dev_notes_modder_hooks.md`. Verified packages may expose allowlisted global routes (`/api/modder/*`, `/api/hooks/*`); unverified packages are sandboxed under `/api/extensions/{id}`.

🛠️ Modder Hook Bus & Debug Integrations
- `comfyvn/core/modder_hooks.py` fans out scenario (`on_scene_enter`, `on_choice_render`), asset (`on_asset_registered`, legacy alias `on_asset_saved`, `on_asset_meta_updated`, `on_asset_removed`, `on_asset_sidecar_written`), props (`on_prop_applied`), and planner (`on_weather_changed`) envelopes to in-process listeners, optional dev plugins (`COMFYVN_DEV_MODE=1`), REST webhooks, and the shared WebSocket stream.
- REST + WS surfaces: `GET /api/modder/hooks` exposes specs, history, and plugin host state; `POST /api/modder/hooks/webhooks` registers signed callbacks; `ws://<host>/api/modder/hooks/ws` streams `modder.on_*` topics with timestamps so automation dashboards can react without polling.
- Asset registry writes now broadcast the refreshed asset type, sidecar path, and metadata snapshot across `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, and `on_asset_sidecar_written`; run `/api/assets/enforce` after large imports to guarantee sidecar coverage and tail `logs/server.log` (`comfyvn.studio.core.asset_registry`) for provenance audits.
- Registry maintenance lives under `comfyvn/server/routes/assets.py`: `GET /api/assets/search` (type/tag/license/text filters plus optional `include_debug` hook snapshots), `POST /api/assets/enforce` (sidecar repair report), and `POST /api/assets/rebuild` (full disk scan + thumbnail refresh). `docs/ASSET_REGISTRY.md` bundles curl recipes, flag defaults, and hook guidance for modders.
- Quick history peek (new fields highlighted):  
  ```bash
  curl -s http://127.0.0.1:8000/api/modder/hooks/history | jq '.items[0]'
  # {
  #   "event": "on_asset_meta_updated",
  #   "payload": {
  #     "uid": "9f1b…",
  #     "type": "character.portrait",
  #     "path": "characters/alice/portrait.png",
  #     "sidecar": "characters/alice/portrait.png.asset.json",
  #     "meta": {"tags": ["hero"], "license": "CC-BY-4.0"},
  #     "hook_event": "asset_meta_updated",
  #     "timestamp": 1731345600.123456
  #   }
  # }
  ```
- Studio ships a **Debug Integrations** panel (System → Debug Integrations) that inspects provider health, webhook registrations, and recent failures; pair it with `docs/development/observability_debug.md` to trace JSON log output and crash dumps when experimenting with hooks.
- Reference docs: `docs/dev_notes_modder_hooks.md`, `docs/dev_notes_asset_registry_hooks.md`, and `docs/PROMPT_PACKS` (POV rewrite & battle narration prompt packs) capture payload schemas, WS snippets, and LLM scaffolding modders can drop into their pipelines.

♿ Accessibility & Input Profiles
- `comfyvn/accessibility/__init__.py` introduces the accessibility manager: font scaling, high-contrast palettes, colorblind overlays (`comfyvn/accessibility/filters.py`), and viewer subtitle overlays (`comfyvn/accessibility/subtitles.py`). Changes persist through `config/settings/accessibility.json` and log structured entries to `logs/accessibility.log`.
- Settings → **Accessibility** now bundles UI scale presets (100–200 %), optional viewer-only overrides, font multiplier, filters, high-contrast toggle, and subtitles; Settings → **Input & Controllers** captures hotkeys via the shared `ShortcutCapture`, maps controller buttons (QtGamepad when available), and exposes numeric choice bindings with reset/import helpers. Feature flags (`enable_accessibility`, `enable_accessibility_controls`, `enable_controller_profiles`, `enable_accessibility_api`) live in `config/comfyvn.json` and surface in the Debug drawer. Reference docs: `docs/ACCESSIBILITY.md`, `docs/INPUT_SCHEMES.md`.
- The input map manager (`comfyvn/accessibility/input_map.py`) centralises keyboard/controller profiles, replays bindings to registered widgets (VN Viewer today), and broadcasts `on_accessibility_input_map` / `on_accessibility_input` modder hooks so automation can respond without polling.
- FastAPI routes `/api/accessibility/{state,set,filters,subtitle,export,import,input-map,input/event}` and `/api/input/{map,reset}` provide REST control. See `comfyvn/server/routes/accessibility.py` for request/response models and sample logging extras.
- VN Viewer now subscribes to both systems: color filters/subtitles update live without re-rendering, and remapped inputs (keyboard or controller) trigger overlay feedback, post structured events, and respect API-triggered actions.

🗓️ Scheduler & Cost Telemetry
- `comfyvn/compute/scheduler.py` maintains local and remote queues with FIFO ordering, priority pre-emption, and sticky-device affinity. Provider metadata (`cost_per_minute`, ingress/egress rates, VRAM minutes) feeds automatic `{cost_estimate, duration_sec, bytes_tx, bytes_rx}` telemetry recorded on completion.
- FastAPI routes under `/api/schedule/*` expose lifecycle verbs (`enqueue`, `claim`, `complete`, `fail`, `requeue`) plus `/health`, `/state`, and `/board` snapshots. Automation scripts can pull `/board` to render Gantt views or inspect cost burn-up before dispatching remote workloads.
- The Studio shell now ships a dockable **Scheduler Board** (Panels → Scheduler Board) that polls `/api/schedule/board` every three seconds, rendering queue, device, duration, and cost overlays so teams can monitor throughput at a glance.
- Debug hooks: poll `/api/schedule/state` for raw queue payloads, inspect `/api/schedule/board` diffs over time to trace duration and cost drift, and tweak provider cost metadata via `config/compute_providers.json` (or `/api/providers`) to model remote spend locally without touching production configs.
- Modders extending asset workflows can pair scheduler telemetry with the asset registry hooks in `docs/development_notes.md` to enqueue thumbnail renders or remote baking jobs while preserving cost estimates for their packs.

🖼️ Public Image & Video APIs (Dry-Run)
- Settings → Debug & Feature Flags exposes `enable_public_image_providers` and `enable_public_video_providers`; toggles mirror the legacy `enable_public_image_video` flag so existing automation scripts stay compatible.
- `/api/providers/image/{catalog,generate}` and `/api/providers/video/{catalog,generate}` surface curated pricing metadata and return dry-run payloads with cost estimates; adapters live under `comfyvn/public_providers/{image_stability,image_fal,video_runway,video_pika,video_luma}.py`.
- Requests register lightweight jobs in the task registry, letting Studio toasts and CLI tooling inspect payload shapes, credit burn heuristics, and execution flags without hitting external services.
- Credentials resolve from environment variables (e.g. `STABILITY_API_KEY`, `FAL_KEY`, `RUNWAY_API_KEY`, `PIKA_API_KEY`, `LUMA_API_KEY`) or `config/comfyvn.secrets.json`. `docs/dev_notes_public_media_providers.md` includes curl snippets, payload schemas, and logging guidance for contributors.

🤗 Hugging Face Hub Connector (Dry-Run)
- Feature flag `enable_public_model_hubs` keeps `/api/providers/hf/{health,search,metadata,pull}` disabled until contributors opt in. All responses include connector metadata (`docs_url`, `last_checked`), feature context, and `dry_run: true` envelopes.
- PATs resolve from environment variables (`HF_TOKEN`, `HF_API_TOKEN`, `HUGGINGFACEHUB_API_TOKEN`, `HUGGINGFACEHUB_TOKEN`) or `config/comfyvn.secrets.json` under the `hf_hub` provider (`token`, `api_token`, or `hf_token`). `/health` surfaces `token_present` so Studio panels can prompt for credentials.
- `/search` and `/metadata` return normalised card data (tags, license hints, summary fields), file inventories with `is_large` flags (`>= 1 GiB`), and gated/private markers. `/pull` performs a dry-run plan only when the caller supplies a PAT plus `ack_license: true`, returning resolved revisions and download plans without fetching assets.
- Docs: `docs/PROVIDERS_HF_HUB.md` captures setup, curl drills, and modder/dev notes; run `python tools/check_current_system.py --profile p7_connectors_huggingface --base http://127.0.0.1:8001` to validate flag defaults, routes, and documentation coverage.

📜 License Snapshot & Ack Gate
- `comfyvn/advisory/license_snapshot.py` captures licence/EULA text, writes `license_snapshot.json` alongside hub assets (fallback: `data/license_snapshots/<slug>/`), records SHA-256 hash + metadata, and persists per-user acknowledgements (with optional provenance) in settings so exports can embed the state later. Snapshots and ack changes fire `on_asset_meta_updated` to keep dashboards in sync.
- FastAPI routes `/api/advisory/license/snapshot`, `/api/advisory/license/ack`, `/api/advisory/license/require`, and `GET /api/advisory/license/{asset_id}` keep risky pulls blocked until a current-hash acknowledgement exists. Responses surface red/green state plus the normalised text (`?include_text=true`) for UI prompts.
- Hub connectors (Civitai, Hugging Face) should trigger the snapshot route before planning downloads, prompt users with the returned text, record the ack, then call `/require` prior to streaming binaries. Checker profile `p7_license_eula_enforcer` validates flag defaults, route wiring, and doc coverage.
- Reference docs: `docs/ADVISORY_LICENSE_SNAPSHOT.md` (API + workflow) and `docs/dev_notes_license_snapshot.md` (data model, hooks, follow-ups).

🗣️ Public Language & LLM Router (Dry-Run)
- Feature flags `enable_public_translate` and `enable_public_llm` (Settings → Debug & Feature Flags) keep `/api/providers/{translate,llm}/*` endpoints OFF by default. Toggle them only after secrets land in `config/comfyvn.secrets.json` or the relevant environment variables.
- `/api/providers/translate/health` unifies translation (Google, DeepL, Amazon), OCR (Google Vision, AWS Rekognition), and speech (Deepgram, AssemblyAI) adapters with pricing links, last-checked timestamps, and credential diagnostics.
- `/api/providers/llm/registry` exposes model metadata (tags, pricing heuristics, context) for OpenAI, Anthropic, Google Gemini, and OpenRouter. `POST /api/providers/llm/chat` returns the HTTP dispatch plan without touching the network so modders can verify headers/bodies before flipping a flag.
- `/api/providers/translate/public` and `/api/providers/llm/chat` both return `{"dry_run": true}` payloads; clients can diff them against live responses later without changing schemas. See `docs/PROVIDERS_LANG_SPEECH_LLM.md` and `docs/LLM_RECOMMENDATIONS.md` for env vars, pricing anchors, and module presets.

🔐 Security & Secrets Hardening
- The encrypted secrets vault persists to `config/comfyvn.secrets.json`; bootstrap a key with `python - <<'PY'` → `from comfyvn.security.secrets_store import SecretStore; store = SecretStore(); print(store.rotate_key())` or drop a base64 Fernet key in `config/comfyvn.secrets.key`. Runtime overrides follow `COMFYVN_SECRET_<PROVIDER>_<FIELD>` (`COMFYVN_SECRET_RUNPOD_API_KEY`, etc.) and merge without touching disk.
- Structured audit lines land in `${COMFYVN_SECURITY_LOG_FILE:-logs/security.log}` capturing `secrets.read`, `secrets.write`, `secrets.key.rotated`, and sandbox denials. Tail with `jq '.["event","provider","host"]'` for dashboards or archive runs alongside provenance bundles.
- Feature flag `enable_security_api` (Settings → Debug & Feature Flags) unlocks `/api/security/*`: `GET /api/security/secrets/providers` summarises stored + override keys, `POST /api/security/secrets/rotate` re-encrypts with a fresh key, `GET /api/security/audit?limit=50` streams JSON audit lines, and `POST /api/security/sandbox/check` validates host:port allowlists. Example: `curl -s http://127.0.0.1:8000/api/security/secrets/providers | jq`.
- Plugin sandboxing now enforces deny-by-default networking even when jobs request `network: true`; allow traffic by listing hosts under `network_allow` or exporting `SANDBOX_NETWORK_ALLOW=localhost:8080`. The guard is gated by `enable_security_sandbox_guard` and publishes `security.sandbox_blocked` hook envelopes when a connection is refused.
- Modder hook bus adds `security.secret_read` and `security.key_rotated` topics (REST + WS) so teams can watch credential usage without revealing values. See `docs/dev_notes_security.md` for payload schemas, curl samples, and audit workflows.

🕵️ Scenario Debug Deck & Viewer Hooks
- **Timeline Workshop** stitches the node editor, multi-track timeline, and a dockable Scenario Runner. The runner surfaces live node focus, active POV, deterministic seed, and tracked variables, supports explicit choice overrides, and provides breakpoint controls so designers can pause on specific node IDs.
- Runner sessions pull from `/api/scenario/run/step` and `/api/pov/*`, keeping the POV manager and variable history in sync. See `docs/POV_DESIGN.md` for branching rules, worldline storage, and persistence models modders can lean on when scripting their own tooling.
- **POV Worldlines** live under `/api/pov/worlds`. The new route exposes list/create/update/activate verbs so exporters and external tools can diff worlds, merge forks, or switch active POVs without touching internal registries. `docs/POV_DESIGN.md` captures payload shapes and merge rules. Toggle the companion `enable_diffmerge_tools` flag (default `false`) to surface `/api/diffmerge/scene`, `/api/diffmerge/worldlines/{graph,merge}` for masked diffs, fast-forward checks, and dry-run merges. Curl example:
  ```bash
  curl -s http://127.0.0.1:8000/api/diffmerge/scene \
    -H 'Content-Type: application/json' \
    -d '{"source": "branch_a", "target": "canon", "mask_pov": true}' | jq '.node_changes'
  ```
  Successful calls emit `on_worldline_diff` / `on_worldline_merge` events so modder dashboards or CI bots can subscribe via `/api/modder/hooks/ws`. Studio exposes a **Modules → Worldline Graph** dock (feature flag respected) that renders 1k+ node timelines without freezing and lets you preview/apply merges directly from the GUI.
- **Worldline Lanes & Timeline Overlay** ship behind `enable_worldlines` + `enable_timeline_overlay` (both default `false`). When toggled on, `/api/pov/worlds`, `/api/pov/worlds/switch`, `/api/pov/confirm_switch`, and `/api/pov/auto_bio_suggest` coordinate OFFICIAL⭐/VN Branch🔵/Scratch⚪ lanes, Ctrl/⌘-K snapshots, delta-over-base metadata, and fork-on-confirm workflows. The registry now stores `_wl_delta` payloads so forks persist only the differences from their parent, while overlay lanes stream deterministic thumbnails (cache keys include `{scene,node,worldline,pov,vars,seed,theme,weather}`), POV badges, and diff badges computed via masked worldline deltas. Snapshot sidecars capture `{tool,version,workflow_hash,seed,worldline,pov,theme,weather}` and the modder hooks `on_worldline_created` / `on_snapshot` expose `delta`, `workflow_hash`, and `sidecar` fields for automation. Quick provenance suggestions land at:
  ```bash
  curl -s http://127.0.0.1:8000/api/pov/auto_bio_suggest \
    -H 'Content-Type: application/json' \
    -d '{"world": "official", "mask_pov": true}' | jq '.suggestions'
  ```
  `docs/TIMELINE_OVERLAY.md` collects payload/GUI notes for contributors.
- **Depth-from-2D Planes** toggle with `enable_depth2d` (default `false`). Auto mode heuristically carves 3–6 planes per scene; manual masks (`data/depth_masks/<scene>.json`) override when authors flip the per-scene mode via the manager or REST helpers, and the preference persists to `cache/depth2d_state.json` so scene toggles survive restarts. `comfyvn/visual/depth2d.py` exposes `resolve_depth_planes` for renderers, while docs highlight preview tooling + JSON mask format.
- **Feature Flags** panel persists toggles (including `enable_public_image_providers` and `enable_public_video_providers`, which keep the legacy `enable_public_image_video` flag in sync for automation) to `config/comfyvn.json`; changes broadcast through the notifier bus so Studio panels react instantly. Secrets for public providers live in `config/comfyvn.secrets.json` and are merged automatically when the backend builds dry-run payloads.
- Panels → **Log Hub** tails runtime logs (`gui.log`, `server.log`, `render.log`, `advisory.log`, `combined.log`) without leaving Studio. Inline Scenario Runner notes help designers correlate UI actions with backend events; modders can fetch `/api/modder/hooks/history` or subscribe to `ws://<host>/api/modder/hooks/ws` for deeper inspection.
- Viewer control routes now auto-fallback native → web → Mini-VN when the native process exits or fails to embed; status polling triggers the switch and the Mini-VN thumbnailer emits deterministic 16:9 captures via the `on_thumbnail_captured` hook. `docs/VIEWER_README.md` captures the decision tree plus `/api/viewer/{web|mini}/*` helpers.
- Narrative automation can lean on the POV Rewrite prompt pack documented in `docs/PROMPT_PACKS/POV_REWRITE.md`, which mirrors the `on_scene_enter`/`on_choice_render` payloads so LLM tooling can restyle narration without diverging from canonical choices.

🎬 Editor Blocking Assistant & Snapshot Sheets
- `POST /api/editor/blocking` (feature flag `enable_blocking_assistant`) returns deterministic shot plans + beat summaries from scene/node context. Responses include `{shots[], beats[], determinism{seed,digest}, narrator_plan}` and emit the `on_blocking_suggested` hook so dashboards can hydrate storyboards without polling REST.
- `POST /api/editor/snapshot_sheet` (`enable_snapshot_sheets`) assembles cached thumbnails or explicit images into contact sheets saved under `exports/snapshot_sheets/<sheet_id>.{png,pdf}`. Layout is controlled via `{columns, cell_width/height, margin, padding, captions}` and every run emits `on_snapshot_sheet_rendered` with sheet ids, outputs, and project/timeline metadata.
- Docs: `docs/EDITOR_UX_ADVANCED.md` (API contract, hook payloads, checker usage) and `docs/development/dev_notes_editor_blocking.md` (CLI drills, determinism reference). Modders can subscribe to `/api/modder/hooks/ws` for the two new events or inspect deterministic seeds/hashes when automating blocking reviews.

⚔️ Battle UX & Simulation v0
- `comfyvn/battle/engine.py` now owns both authoring and simulation flows. Editor picks call `POST /api/battle/resolve` and always receive `editor_prompt: "Pick winner"` plus deterministic breakdowns, RNG state, provenance, and a predicted outcome; optional `stats`, `seed`, `rounds`, and `narrate` flags let designers preview seeded narration or keep the response silent.
- `POST /api/battle/sim` (feature gated by `enable_battle_sim`, default `false`; legacy `/simulate` aliases remain) applies the v0 formula `base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)` and returns `{outcome, seed, rng, weights, breakdown[], formula, provenance}`. Set `"narrate": true` for POV-aware logs or `false` for CI-friendly roll sheets.
- Modder hooks `on_battle_resolved` and `on_battle_simulated` now include `weights`, `breakdown`, `rng`, `provenance`, `predicted_outcome`, `narrate`, `rounds`, and optional `log`/`narration` fields so overlays, telemetry, or exporters can mirror Studio output without re-querying REST.
- The Battle Narration prompt pack at `docs/PROMPT_PACKS/BATTLE_NARRATION.md` remains the canonical beat library; pair outcomes with prop styling guidance in `docs/VISUAL_STYLE_MAPPER.md` when dressing victory/defeat scenes.

🌐 Public Provider Catalog & Dry-Run Adapters
- `/api/providers/gpu/public/{provider}/{health,submit,poll}` and `/api/providers/{image,video}/{provider}/{health,submit,poll}` expose consistent dry-run envelopes with deterministic job ids, `pricing_url`, `last_checked`, and capability metadata. Catalog routes continue to return curated pricing snapshots across GPU, media, translate, and LLM tracks.
- Adapters in `comfyvn/public_providers/*` merge payloads with `config/comfyvn.secrets.json` (or env vars) while honouring feature flags (`enable_public_gpu`, `enable_public_image_providers`, `enable_public_video_providers`). Missing credentials force `dry_run` + `execution_allowed: false`, keeping automation safe.
- Health endpoints accept optional `{"config": {...}}` payloads so contributors can validate credential formats without storing secrets. Submit routes register `public.{gpu,image,video}.submit` tasks for downstream tooling, and poll routes never hit third-party APIs.
- Run the smoke profile `python tools/check_current_system.py --profile p3_providers_gpu_image_video --base http://127.0.0.1:8001` before enabling live traffic. Docs `docs/PROVIDERS_GPU_IMAGE_VIDEO.md` and `docs/dev_notes_public_media_providers.md` capture opt-in flows, pricing links, and debug hooks; `docs/WORKBOARD_PHASE7_POV_APIS.md` retains long-form research notes.

🧠 Character Emulation & LLM Registry
- Feature flag: set `features.silly_compat_offload` (or `COMFYVN_SILLY_COMPAT_OFFLOAD=1`) to opt-in to the emulation engine. `/api/emulation/status`, `/toggle`, `/persona`, and `/chat` surface persona memory, style guides, and adapter-backed replies.
- Registry discovery: `/api/llm/registry`, `/api/llm/runtime/*`, and `/api/llm/test-call` surface the JSON-backed provider list, let you register temporary adapters, and provide a dry-run chat echo without touching paid APIs. Prompt-pack endpoints are still pending; see `docs/LLM_RECOMMENDATIONS.md` for the current roadmap.
- FastAPI wiring: include the viewer, POV, render, and LLM routers inside your app factory so Studio builds gain the center pane + proxy endpoints:

  ```python
  # Phase 2/2 Project Integration Chat — POV & Viewer Phase
  from comfyvn.server.routes import viewer, pov, pov_render, llm
  app.include_router(viewer.router)
  app.include_router(pov.router)
  app.include_router(pov_render.router)
  app.include_router(llm.router)
  ```

- Studio center panes: set `center_router.set_default(VNViewer)` and `center_router.register("designer", CharacterDesigner)` so VN playback is the default middle pane with a quick jump to the Character Designer toolkit.
- VN Viewer chat panel (`Modules → VN Chat`) mirrors SceneStore dialogue and queues prompts for the forthcoming `/api/llm/chat` router. Until that lands, wire custom tooling through `/api/llm/test-call` or runtime adapters to keep workflows deterministic.

🧠 LLM Registry & Adapters
- `comfyvn/models/registry.json` centralises provider-neutral metadata (`tags`, defaults, base URLs) so Studio features and automation scripts can negotiate capabilities without hard-coding vendors.
- Adapter implementations (`comfyvn/models/adapters/{openai_compat,lmstudio,ollama,anthropic_compat}.py`) proxy chat requests while honouring provider overrides such as custom headers, timeouts, and environment-supplied API keys (`COMFYVN_LLM_<PROVIDER>_{BASE_URL,API_KEY,HEADERS}`).
- FastAPI currently exposes `/api/llm/{registry,runtime,test-call}` for discovery, adapter injection, and stubbed replies. The documented `/api/llm/chat` proxy is still on the roadmap; consult the Public LLM Router work order stub for status and integration notes.
- Tuning notes live in `docs/LLM_RECOMMENDATIONS.md`, covering per-module defaults (`chat`, `translate`, `worldbuild`, `json`, `long-context`) and sample payloads for contributors wiring bespoke tooling.

✨ New Additions
🤝 Roleplay Import & Collaboration System

(New Subsystem 11)
Enables uploading .txt or .json multi-user chat logs to convert into VN scenes.

New Modules: parser.py, formatter.py, analyzer.py, roleplay_api.py

Endpoints:

POST /roleplay/import → parse & convert logs

GET /roleplay/preview/{scene_uid} → preview generated scene JSON

POST /roleplay/apply_corrections → persist editor updates back into the scene registry

POST /roleplay/sample_llm → run detail-aware LLM cleanup and store the final variant

Data Folders:

/data/roleplay/raw

/data/roleplay/processed (editable scripts; legacy mirror remains in /converted)

/data/roleplay/final (LLM-enhanced outputs)

/data/roleplay/preview

🧠 Automatically detects participants and outputs VN-ready scene structures.

🌐 WebSocket Job System (Server + GUI)

Introduced full real-time job tracking via /jobs/ws.

New module: server/modules/job_manager.py

GUI now supports async job updates, tray alerts, and task overlays.

/jobs/poll, /jobs/logs, /jobs/reset, /jobs/kill endpoints added.

Graceful WebSocket shutdowns and heartbeats for reliability.

🧾 Live Collaboration & Presence

- Feature flag `features.enable_collaboration` gates the shared CRDT document hub (`comfyvn/collab/{crdt,room}.py`) and the `/api/collab/*` HTTP/WebSocket surfaces. Disable it to fall back to solo editing in hosted or offline builds.
- WebSocket entrypoint: `ws(s)://<host>/api/collab/ws?scene_id=<id>`. Every client joins with actor headers (`X-ComfyVN-User`, `X-ComfyVN-Name`) and receives the snapshot + presence roster shown below.

  ```json
  {
    "type": "room.joined",
    "scene_id": "intro",
    "version": 12,
    "clock": 48,
    "snapshot": {"scene_id": "intro", "nodes": [], "lines": []},
    "presence": {"participants": [], "control": {"owner": null, "queue": []}}
  }
  ```
- REST & headless helpers sit beside the WebSocket flow: `POST /api/collab/room/{create,join,leave,apply}` (headless presence + debug ops), `GET /api/collab/room/cache` (hub stats), plus `health`, `presence/{scene_id}`, `snapshot/{scene_id}`, `history/{scene_id}?since=<version>`, and `POST /api/collab/flush`. Example probes: 

  ```bash
  curl -s $BASE/api/collab/health | jq
  curl -s $BASE/api/collab/presence/demo_scene | jq '.presence.control'
  curl -s $BASE/api/collab/history/demo_scene?since=0 | jq '.history | length'
  ```
- Server emits structured log lines (`collab.op applied ...`) to `logs/server.log` for replay and regression capture. The same payload reaches `on_collab_operation` on the modder bus and the WebSocket topic `modder.on_collab_operation`.
- Studio’s `TimelineView` attaches a `CollabClient` overlay displaying participants (marking `headless` REST callers), cursor focus, and lock queue state. Local edits are diffed into CRDT ops so concurrent changes converge without losing nodes or metadata; remote snapshots are replayed through the editor automatically.
- Docs + debugging aids live in `docs/COLLAB_EDITING.md`, `docs/development_notes.md` (architecture), and `docs/DEBUG_SNIPPETS/STUB_DEBUG_BLOCK.md` (step-by-step verification checklist).

🧭 Scenario Schema & Deterministic Runtime

Canonically defines a branching scene JSON schema (Scene → Node → Choice → Action), wired into a seeded runner so identical seeds replay the same path.

New Bits: `comfyvn/schema/scenario_schema.json`, `comfyvn/runner/scenario_runner.py`, `comfyvn/runner/rng.py`, and FastAPI route wiring in `comfyvn/server/routes/scenario.py`.

Endpoints:

POST /api/scenario/validate → returns `{valid:bool, errors:list}` for the provided scene payload.

POST /api/scenario/run/step → applies deterministic branching with optional `seed`, `state`, and explicit `choice_id`, returning the updated state plus peek data for the next node.

Testing:

`tests/test_scenario_runtime.py` (pending migration) should be expanded to hit the new `/api/scenario/*` routes for parity.

🎮 Playtest Harness & Golden Diffs

- QA helpers live under `comfyvn/qa/playtest/{headless_runner,golden_diff}.py`; they wrap the deterministic `ScenarioRunner` and emit canonical JSON traces plus structured `.log` companions under `logs/playtest/`.
- FastAPI now exposes `POST /api/playtest/run` (feature flag `features.enable_playtest_harness`, disabled by default). Payload accepts `{scene, seed?, pov?, variables?, prompt_packs?, workflow?, persist?, dry_run?}` and replies with the trace digest, provenance block, and optional `trace_path`/`log_path` when persistence is enabled.
- Sample call:
  ```bash
  curl -s http://127.0.0.1:8000/api/playtest/run \
    -H 'Content-Type: application/json' \
    -d '{"scene": {...}, "seed": 682, "dry_run": true}' | jq '.digest'
  ```
- Modder hook bus adds `on_playtest_start`, `on_playtest_step`, and `on_playtest_finished` so tooling can stream run metadata or diff traces without polling; see `docs/dev_notes_modder_hooks.md` for payload fields.
- Golden comparisons: import `comfyvn.qa.playtest.compare_traces(actual, golden)` or run the new pytest suite (`tests/test_playtest_headless.py`, `tests/test_playtest_api.py`) to flag regressions when seeds/pov/vars drift.

💾 Runtime Savepoints & Checkpoints

- Runtime snapshots are written to `data/saves/<slot>.json` through `comfyvn/runtime/savepoints.py`, using atomic temp-file swaps so slots never half-write.
- New REST surface in `comfyvn/server/routes/save.py` exposes `POST /api/save/{slot}`, `GET /api/save/{slot}`, and `GET /api/save/list` for persisting and enumerating checkpoints.
- Save payloads require `{vars, node_pointer, seed}` and accept extra metadata, letting callers stash runner history or UI context alongside the core state.
- Designed around the deterministic `ScenarioRunner`: storing its RNG state alongside variables ensures the very next `step()` after a restore matches the original branch.

🌐 Translation Manager & Live Language Switch

(New Subsystem 12)
Introduced a versioned Translation Memory backed by `comfyvn/translation/tm_store.py` plus the lightweight language registry at `comfyvn/translation/manager.py`. Active/fallback languages persist to `config/comfyvn.json`, inline tables merge with JSON overrides under `config/i18n/` + `data/i18n/`, and the shared `t()` helper now consults TM overrides before falling back to the key itself. Full docs live in `docs/TRANSLATION_MANAGER.md`.

New Bits: `comfyvn/translation/__init__.py`, `comfyvn/translation/manager.py`, `comfyvn/translation/tm_store.py`, `comfyvn/server/routes/translation.py`

Endpoints:

- POST `/api/translate/batch` → resolves cached TM hits, records identity stubs (`origin="stub"`, `confidence=0.35`) for review, and echoes per-item `links` + `meta` so modders can deep link into exports.
- GET `/api/translate/review` → fetches pending/approved entries with filters (`status`, `lang`, `key`, `asset`, `component`, `limit`, `include_meta`). Legacy `/pending` remains as a shim.
- POST `/api/translate/review` → approves/edits translations, updates reviewer + confidence, toggles `reviewed`, and enriches `meta` in-place. Legacy `/approve` reuses the new handler.
- GET `/api/translate/export/{json,po}` → exports reviewed entries (optionally scoped by `lang` and `key`, with `include_meta=1` to embed asset hooks).
- GET `/api/i18n/lang` / POST `/api/i18n/lang` → unchanged surface for reporting and toggling the active/fallback languages with hot reload.

Upcoming Phase — Public MT/OCR/Speech APIs
- Feature flags (disabled by default) land under `config/comfyvn.json → features`:  
  - `enable_public_translation_apis`  
  - `enable_public_ocr_apis`  
  - `enable_public_speech_apis`
  Toggle them via **Settings → Debug & Feature Flags** or by editing the JSON file; long-lived processes should call `feature_flags.refresh_cache()` after changes.
- New adapters will live in `comfyvn/public_providers/` and expose `from_env()` constructors plus `translate()/quota()`, `extract()/quota()`, and `transcribe()/quota()` methods. Until those adapters are wired, the TM routes degrade to the existing identity fallback.
- Diagnostics surface through `/api/providers/translate/test`, `/api/providers/ocr/test`, and `/api/providers/speech/test`. With feature flags off or missing credentials, the routes reply with HTTP 200 and payloads such as:
  ```jsonc
  {
    "ok": false,
    "providers": [
      {
        "id": "google_translate",
        "configured": false,
        "errors": [{"code": "missing_credentials"}]
      }
    ]
  }
  ```
  Pass environment variables like `COMFYVN_TRANSLATE_DEEPL_KEY` or populate `config/public_providers.json` to see quota/plan summaries once adapters land.
- Dry-run mode remains available across every paid call: set `"dry_run": true` inside the payload (translation/speech) or use the `dry_run=1` query parameter (OCR). The server short-circuits network calls and responds with cached diagnostics so modders can script validation without incurring costs.
- GET `/api/i18n/lang` → reports `{active, fallback, available}` languages.
- POST `/api/i18n/lang` → updates active/fallback and persists them instantly.

Runtime & GUI Helpers:

- `comfyvn.translation.t(key, lang=None)` resolves strings through the active language with automatic fallback.
- Dropping a JSON file at `config/i18n/<lang>.json` overrides bundled strings; hitting `POST /api/i18n/lang` with the same language hot-reloads the overrides without restarts.

🛠 Developer & Modding Hooks

- Assets REST surface: `/assets/` (list/filter), `/assets/{uid}`, `/assets/{uid}/download`, `/assets/upload`, and `/assets/register` expose provenance metadata and relative-path safeguards for automation scripts. Query parameters now cover `type`, `hash`, `tags`/`tag`, and `q` (case-insensitive substring search) so tooling can zero in on specific assets, e.g. `curl '/assets?type=portrait&tags=hero&hash=abc123&q=summer'` (see `docs/development_notes.md`).
- Asset gallery tooling: Panels → Asset Gallery adds a search field (path/metadata), type/tag/license filters, async thumbnails, bulk tag/license edits, and a clipboard debug exporter so modders can inspect sidecars without leaving Studio (see `docs/ASSET_REGISTRY.md` for the full workflow and hook matrix).
- Registry hook bus: `AssetRegistry.add_hook(event, callback)` surfaces `asset_registered`, `asset_meta_updated`, `asset_removed`, and `asset_sidecar_written` events for provenance or automation scripts. The Modder Hook bus now publishes `on_asset_registered`, `on_asset_saved` (alias), `on_asset_meta_updated`, `on_asset_sidecar_written`, and `on_asset_removed`; REST consumers can fetch the spec/history via `/assets/debug/{hooks,modder-hooks,history}` or subscribe over `/api/modder/hooks/ws`. Sidecars remain first-class APIs: fetch the parsed payload with `GET /assets/{uid}/sidecar` when diffing provenance or replaying renders. Deep-dive workflows live in `docs/dev_notes_asset_registry_hooks.md` and `docs/development/modder_asset_debug.md`.
- Advisory plugin & liability workflows: `docs/development/advisory_modding.md` covers acknowledgement flows, scanner extension points, and debug/API hooks for contributors building custom policy tooling.
- Debug toggles: `COMFYVN_LOG_LEVEL=DEBUG` raises verbosity; `COMFYVN_RUNTIME_ROOT` redirects runtime folders for sandboxing; asset registration logs include sidecar and thumbnail targets when running at debug level.
- Observability & privacy toolkit: `comfyvn/obs/` ships anonymisation helpers (`anonymize_payload`, `hash_identifier`, `anonymous_installation_id`), the opt-in `TelemetryStore`, and crash recorder plumbing that register digests once uploads are explicitly allowed. The umbrella flag `enable_observability` (legacy `enable_privacy_telemetry`) and `enable_crash_uploader` remain **OFF** by default and surface in **Settings → Debug & Feature Flags** alongside the `config/comfyvn.json → telemetry` consent block. Endpoints respond with hashed identifiers, consent metadata, and a lightweight health snapshot:
  ```bash
  # Check flag + consent state without mutating anything
  curl http://localhost:8001/api/telemetry/health | jq '{flag_enabled, telemetry_active, dry_run}'

  # Opt in locally (keep dry-run true so nothing ever leaves the machine)
  curl -X POST http://localhost:8001/api/telemetry/opt_in \
       -H "Content-Type: application/json" \
       -d '{"diagnostics": true, "dry_run": true}'

  # Record modder instrumentation (payload fields with id/key/token/secret/etc are hashed automatically)
  curl -X POST http://localhost:8001/api/telemetry/events \
       -H "Content-Type: application/json" \
       -d '{"event": "modder.on_asset_saved", "payload": {"asset_id": "abc123", "author": "jane@example.com"}}'

  # Export a scrubbed diagnostics bundle (manifest + telemetry snapshot + crash summary)
  curl -OJ http://localhost:8001/api/telemetry/diagnostics
  ```
  Responses include `feature_flag` echoes, per-feature counters, hook samples, consent state, and scrubbed crash hashes while omitting raw PII. See `docs/OBS_TELEMETRY.md`, `docs/development/observability_debug.md`, and `docs/dev_notes_observability_perf.md` for full payload schemas, hook catalogues, and verification checklists.
- Performance budgets & profiler: `comfyvn/perf/{budgets,profiler}.py` keep soft CPU/RAM/VRAM caps, queue throttling, lazy asset eviction, and a lightweight tracer for modder tooling. Toggle `features.enable_perf` (legacy `enable_perf_budgets` / `enable_perf_profiler_dashboard`) when you want the `/api/perf/*` surface; routes now expose a `health` snapshot and echo `feature_flag` so smoke checks can gracefully skip when budgets are disabled:
  ```bash
  curl http://localhost:8001/api/perf/health | jq '{feature_flag, budgets_enabled, profiler_enabled}'
  curl -X POST http://localhost:8001/api/perf/budgets/apply \
       -H "Content-Type: application/json" \
       -d '{"max_cpu_percent": 70, "max_running_jobs": 2}'
  curl http://localhost:8001/api/perf/profiler/dashboard?limit=5 | jq '.dashboard.top_time'
  ```
  Budget decisions are broadcast via `on_perf_budget_state`, profiler snapshots via `on_perf_profiler_snapshot`, and both surfaces are documented in `docs/PERF_BUDGETS.md` and `docs/dev_notes_observability_perf.md`.
- Remote installer orchestrator: flip on **Settings → Debug & Feature Flags → Remote Installer** (persists `features.enable_remote_installer=false` by default) to access `/api/remote/modules`, `/api/remote/install`, and `/api/remote/status`. Plans now honour encrypted SSH credentials resolved from `config/comfyvn.secrets.json`, probe remote sentinels before executing, and only upload config blobs when the destination is absent. Every run appends to `logs/remote/install/<host>.log` and updates `data/remote/install/<host>.json`, capturing `installed/skipped/failed` state per module.
  ```bash
  curl -X POST http://localhost:8001/api/remote/install \
       -H "Content-Type: application/json" \
       -d '{"host":"gpu.example.com","modules":["comfyui","ollama"],"secrets":{"provider":"remote_installer"}}'
  ```
  Responses include `status`, `installed`, `skipped`, `failed`, `log_path`, `status_path`, and the resolved plan. Use `"dry_run":true` to lint steps without touching disk, or query `/api/remote/status?host=<name>` to reconcile orchestration state. See `docs/REMOTE_INSTALLER.md` and `docs/SECURITY_SECRETS.md` for full payload schemas, curl workflows, and vault guidance.
- Doctor Phase 4: run `python tools/doctor_phase4.py --base http://127.0.0.1:8000` to exercise `/health`, verify crash dumps, and ensure the structured logger is wired. The doctor emits a JSON report and returns non-zero when any probe fails, making it CI-friendly.
- Doctor Phase 8: run `python tools/doctor_phase8.py --pretty` to instantiate the app factory in-process, assert there are no duplicate router mounts, confirm core debug surfaces (`/api/weather/state`, `/api/props/*`, `/api/battle/*`, `/api/modder/hooks`, `/api/viewer/mini/*`, `/api/narrator/status`, `/api/pov/confirm_switch`) and verify feature defaults (`enable_mini_vn`/`enable_viewer_webmode` **ON**, external providers **OFF**, `enable_compute` **ON**). The script emits a JSON summary with `"pass": true` when the integration surface is healthy and returns non-zero otherwise—ideal for CI gates.
- Scenario E2E contract: `tests/e2e/test_scenario_flow.py` drives `/api/scenario`, `/api/save`, `/api/presentation/plan`, and `/api/export/*` endpoints against `tests/e2e/golden/phase4_payloads.json`. Update the golden file intentionally and call out payload changes in the changelog so modders can sync.
- Translation overrides: add locale files, then call `POST /api/i18n/lang` to refresh the active language during UI testing.
- SillyTavern bridge endpoints: `GET /st/health` now returns ping stats **plus** bundled vs installed manifest versions for the extension and comfyvn-data-exporter plugin, along with watch-path diagnostics. `GET /st/paths` surfaces the resolved copy targets. Use `POST /st/extension/sync` with `{"dry_run": true}` to preview copy plans (flip to `false` to write files). Chat transcripts now flow through the ST importer pipeline (feature flag `features.enable_st_importer`, default **OFF**): `POST /api/import/st/start` accepts uploads, inline text, or bridge URLs, writes artefacts to `imports/<runId>/`, generates scenario graphs (`data/scenes/<scene>.json`), and updates the target project (`data/projects/<id>.json`). Poll progress via `GET /api/import/st/status/{runId}`—payloads surface `phase`, `progress`, generated scenes, preview metadata, and aggregated warnings. `POST /st/session/sync` still pushes the active VN scene/variables/history to SillyTavern and pulls back a reply for the VN Chat panel (2 s timeout by default). Persona payloads continue to land in the registry while chat imports emit the new Modder Hooks `on_st_import_started`, `on_st_import_scene_ready`, `on_st_import_completed`, and `on_st_import_failed` for dashboards and automation.
- Bridge debug helpers: export `COMFYVN_ST_EXTENSIONS_DIR` or `SILLYTAVERN_PATH` to override detection, set `COMFYVN_LOG_LEVEL=DEBUG` to log file-level copy operations, and watch `/st/health` for `watch_paths`, `alerts`, and version statuses (`extension.version_status`, `plugin.version_status`) so mismatches trigger proactive syncs.
- Modder quickstart notes live in `docs/dev_notes_modder_hooks.md`, summarising API payloads, expected sidecar outputs, and representative cURL invocations for each bridge/asset endpoint.
- Automation helpers: run `python tools/assets_enforcer.py --dry-run --json` to audit sidecar coverage in CI, or add `--fill-metadata` to backfill tags/licences from folder structure before committing assets.
- Studio developer tooling: enable Developer Tools to surface an inline request inspector for `/api/*` calls when building custom panels or external modding scripts.

🎙️ Narrator Outliner & Role Mapping
- Server rails: `/api/narrator/{status,mode,propose,apply,stop,rollback,chat}` stay behind `features.enable_narrator` (default OFF). Proposals are deterministic offline drafts that queue JSON `{choice_id?, vars_patch, rationale}` without mutating variables until `/api/narrator/apply` approves them; each node enforces a three-turn cap and rollback replays emit the same hook payloads.
- Role routing: `/api/llm/{roles,assign,health}` (flag `features.enable_llm_role_mapping`) maps Narrator/MC/Antagonist/Extras to adapters or devices, tracks sticky sessions/budgets, and dry-runs routing plans for the VN Chat drawer. Offline adapter `offline.local` remains the default reply engine so multi-GPU setups are strictly opt-in.
- Modder hooks: `on_narrator_proposal` and `on_narrator_apply` surface scene/node/turn metadata, choice ids, vars patches, and digests for dashboards; hook specs live in `comfyvn/core/modder_hooks.py` and the spec recap sits in `docs/NARRATOR_SPEC.md`.
- Debug: run `python tools/check_current_system.py --profile p2_narrator --base http://127.0.0.1:8001` to confirm flags, routes, and docs exist; failures flip `"pass": false` for CI.
```bash
curl -s -X POST http://127.0.0.1:8001/api/narrator/propose \
  -H 'Content-Type: application/json' \
  -d '{
    "scene_id": "demo_scene",
    "node_id": "demo_scene.node_1",
    "prompt": "Offer a reflective beat before the next choice.",
    "choices": [{"id": "choice_continue"}],
    "context": [{"speaker": "MC", "text": "I need a second."}],
    "force": true
  }' | jq '.state.queue[0]'

curl -s "http://127.0.0.1:8001/api/llm/roles?dry_run=true&role=Narrator" | jq '.plans[0]'
```

🛰️ Phase 6 POV & Viewer Foundations
- Docs: `docs/WORKBOARD_PHASE6_POV.md`, `docs/POV_DESIGN.md`, `docs/VIEWER_README.md`, and `docs/LLM_RECOMMENDATIONS.md` outline the roadmap, manager/runner internals, viewer API, and adapter guidance for modders.
- API: `/api/viewer/{start,stop,status}`, `/api/pov/{get,set,fork,candidates}`, and `/api/llm/{registry,runtime,test-call}` are wired directly in `create_app()` so Studio, CLI, and automation clients share the same surface without requiring the unfinished `/api/llm/chat` proxy.
- GUI: the main window hosts a `CenterRouter` that defaults to the VN Viewer and registers the Character Designer stub; switching views keeps registries in sync and exposes quick actions for assets/timeline/logs.
- Config: new feature flags (`enable_st_bridge`, `enable_llm_proxy`, `enable_narrator_mode`, `enable_narrator`, `enable_llm_role_mapping`) live in `config/comfyvn.json` with safe defaults. Toggle them through **Settings → Debug & Feature Flags** or edit the JSON and call `feature_flags.refresh_cache()` in long-lived processes.
- Runtime LLM registry: `comfyvn/models/runtime_registry.py` plus `/api/llm/runtime/*` enable temporary adapter registration without editing the on-disk registry.

🪟 GUI Framework Expansion

New Version: v1.2.0-dev

Added Task Manager Dock with live updates and right-click actions.

Added TraySystem notifications and job summaries.

Added Settings UI for API/Render configuration.

Implemented Progress Overlay and unified Status Bar.

Async refactor: switched to httpx.AsyncClient.

Scaffolded “Import Roleplay” dialog (Phase 3.2 GUI target).

Read-only Scenes, Characters, and Timeline inspectors now live under `comfyvn/gui/views/` and source their lists from `/api/{scenes,characters,timelines}` via the shared `ServerBridge`, falling back to mock payloads when the backend is offline. Selection updates a JSON inspector so designers can sanity-check payloads without leaving the Studio shell.
- Character Designer complements the inspectors with full CRUD, LoRA attachment management, and hardened render buttons that surface asset UIDs + thumbnails inline for rapid iteration.

🌍 World & Ambience Enhancements

Added Day/Night + Weather Profiles.

Added TTL-based cache refresh for active world data.

Linked to AudioManager for ambience syncing.

Extended /data/worlds/ format with environmental metadata.

Theme kits now span fourteen palettes (`ModernSchool` → `Cozy`) with prompt flavors, camera defaults, props, and tag remaps captured in `comfyvn/themes/templates.py`. `/api/themes/{templates,preview,apply}` expose catalog data, deterministic plan deltas, and VN Branch commits so OFFICIAL⭐ lanes remain clean. Debug, hook payloads, and curl walkthroughs live in `docs/THEME_SWAP_WIZARD.md`; flavor matrices and shared vocabulary live in `docs/THEME_KITS.md` + `docs/STYLE_TAGS_REGISTRY.md`.

🫂 Persona & Group Layout

Emotion blending and transitional tweening added.

Persona overlay for “User Character” implemented.

Group auto-layout based on Roleplay participants.

Persona state serialization to /data/persona/state.json.

Player Persona Manager panel syncs `/player/*` APIs, enabling roster imports, offline persona selection, and guaranteed active VN characters.

Image→Persona analyzer (`features.enable_image2persona`, default **off**) ingests 1–N reference images and emits deterministic appearance tags, 5–8 color swatches, pose anchors, expression prototypes, and style/LoRA name suggestions. Results merge into `metadata.image2persona` with provenance hashes so modders can diff/QA the pipeline. See `docs/IMAGE2PERSONA.md` for API usage and `docs/dev_notes_image2persona.md` for hook/QA notes; verify flag + docs with `python tools/check_current_system.py --profile p6_image2persona --base http://127.0.0.1:8001`.

Persona importer + consent gate (`features.enable_persona_importers`, default **off**) map community markdown or JSON dumps into the persona schema once `POST /api/persona/consent` records rights + NSFW handling. `/api/persona/import/{text,images}` normalise payloads, enqueue `persona.image2persona` jobs, `/api/persona/map` persists to `data/characters/<id>/persona.json` + provenance sidecars, and `/api/persona/preview` powers UI previews. Modder hook `on_persona_imported` broadcasts persona payloads + sidecar paths for dashboards/webhooks. Docs: `docs/PERSONA_IMPORTERS.md`, `docs/NSFW_GATING.md`, and `docs/dev_notes_persona_importers.md`.

🔊 Audio & FX Foundation

Centralized audio_settings.json.

Adaptive layering plan (mood-based playback).

Thread-safe audio calls and volume normalization.

Audio Lab stubs are gated behind `features.enable_audio_lab` (default **false**). Flip the flag to exercise the following offline surfaces:

- `GET /api/tts/voices` exposes the stub voice catalog (`id`, `character`, `styles`, `default_model`, `tags`, `sample_text`) so panels can pre-populate dropdowns without hitting external providers.
- `POST /api/tts/speak` now emits alignment checksums and lipsync metadata alongside the cache response. Sidecars record `alignment_checksum`, `text_sha1`, WAV `checksum_sha1`, and provenance so exporters and CLI scripts can diff stems deterministically.
- `POST /api/audio/align` returns phoneme timings plus optional lipsync payloads; set `{"persist": true}` to mirror the JSON under `data/audio/alignments/<text_sha1>/` for batch pipelines.
- `POST /api/audio/mix` continues to mix deterministic stems with ducking controls; sidecars now capture `checksum_sha1`, `bytes`, `peak_amplitude`, `rms`, and `rendered_at` so replay loops can assert stability.
- Modder hooks `on_audio_tts_cached`, `on_audio_alignment_generated`, and `on_audio_mix_rendered` broadcast cache events (`cache_key`, checksums, file paths) to dashboards, OBS overlays, or automation scripts. Subscribe via `/api/modder/hooks` or `ws://…/api/modder/hooks/ws`.

See `docs/AUDIO_LAB.md` for request/response shapes, cache layouts, and debugging steps. Replays reuse cached WAVs and JSON, letting contributors diff downstream mastering passes without re-rendering core stems.

🧬 LoRA Management

Async LoRA registry and sha256 verification.

Local index /data/lora/lora_index.json.

Prepared search hooks for GUI and persona consistency.
LoRA attachments authored via the Character Designer persist to `data/characters/<id>/lora.json`; the hardened bridge consumes them automatically during `/api/characters/render` runs and mirrors applied weights in asset metadata for modder scripts.

POV render pipeline auto-completes portraits via `/api/pov/render/switch`, caching renders by `(character, style, pose)` and injecting each character's LoRA stack through the hardened ComfyUI bridge.

Asset sidecars now record workflow id, prompt id, and the applied LoRA payloads; the originating ComfyUI sidecar is mirrored alongside the registered artifact for provenance diffs.

Enable `LOG_LEVEL=DEBUG` (or scope `comfyvn.pov.render`) to trace cache hits/misses and inspect generated assets under `assets/characters/<character>/<style>/`.

🧪 Playground Expansion

- Feature flags `enable_playground` + `enable_stage3d` now reveal the **Playground** tab (Tier-0 parallax + Tier-1 Stage 3D) inside the Studio center router. The view lives in `comfyvn/gui/central/playground_view.py` and hot-loads as soon as the flag flips on.
- Snapshots land in `exports/playground/render_config.json` with deterministic camera/layer/light payloads and fire `on_stage_snapshot` hooks so Codex A (“Add node” / “Fork”) flows can ingest them directly from Studio.
- Stage 3D no longer requires CDN access: Three.js `0.159.0` + `@pixiv/three-vrm@2.0.1` modules are vendored under `comfyvn/playground/stage3d/vendor/`, and the HTML import map keeps everything offline-friendly.
- Docs: `docs/PLAYGROUND.md`, `docs/3D_ASSETS.md` capture tier behaviour, asset layout, hooks, and the offline runtime notes.

🛠️ Production Workflow Baselines

Bridge layer refreshed for deterministic sprite/scene/video/voice runs:

- `comfyvn/bridge/comfy.py` (queue/poll/download), `comfyvn/bridge/tts.py` (XTTS/RVC), `comfyvn/bridge/remote.py` (SSH probe).
- Canonical ComfyUI graphs live under `comfyvn/workflows/` (`sprite_pack.json`, `scene_still.json`, `video_ad_evolved.json`, `voice_clip_xtts.json`).
- Provider template + lock in `comfyvn/providers/`, regenerated through `tools/lock_nodes.py`.
- Overview and usage notes documented in `docs/production_workflows_v0.6.md`.
- Offline LLM registry ships a `local_llm` provider preset and ComfyUI LLM bridge pack for fully offline dialogue generation.
- SillyTavern bridge respects configurable base + plugin paths (set in **Settings → Integrations** and the ST extension panel). Roots API mirrors source file locations for worlds, characters, and personas.
- Roleplay imports store raw transcripts, processed editor JSON, and LLM-finalized scenes; detail levels (`Low`, `Medium`, `High`) drive the cohesion prompt pipeline.

📦 Packaging & Build

File sanitization for cross-platform exports.

Build logs saved to the user log directory (see **Runtime Storage**) as `build.log`.

Added “dry-run” mode for preview exports.

Packaging roadmap tracked in `docs/packaging_plan.md`.

🖼️ Sprite & Pose Toolkit

- Modules → `Sprites` opens the sprite panel for managing persona expressions, previews, and pose assignments.
- Poses load from user runtime directories (`data/poses`); active pose JSON is embedded in persona metadata and surfaced to ComfyUI workflows.
- Ship with starter ComfyUI workflow templates: `sprite_composite_basic`, `pose_blend_basic`, and `sprite_pose_composite`.

⚙️ Cross-System Improvements
Category	Update
Async Safety	Replaced blocking I/O with asyncio.create_task().
Logging	Standardized under the user log directory (`system.log`) using rotating handlers.
Configuration	Added /config/paths.json for all base URLs and directories.
Validation	Schema templates /docs/schema/scene.json, /docs/schema/world.json.
Thread Safety	Added cleanup hooks and WebSocket lock protection.
Error Handling	Replaced bare except: with structured exceptions and logs.
Testing	Added pytest stubs for API endpoints.

## Running ComfyVN Locally

`python run_comfyvn.py [options]` bootstraps the virtualenv, installs requirements, and then launches either the GUI or the FastAPI server depending on the flags you pass. Handy commands:

- `python run_comfyvn.py` – launch the GUI and auto-start a local backend on the resolved default port.
- `run_comfyvn.bat` (Windows) performs the same bootstrap and attempts a `git pull --ff-only` first when the working tree is clean, keeping local installs up to date before delegating to `run_comfyvn.py`.
- `python run_comfyvn.py --server-only --server-host 0.0.0.0 --server-port 9001` – start only the FastAPI server (headless) listening on an alternate interface/port.
- `python run_comfyvn.py --server-url http://remote-host:8001 --no-server-autostart` – open the GUI but connect to an already-running remote server without spawning a local instance.
- `python run_comfyvn.py --server-only --server-reload` – headless development loop with uvicorn’s auto-reload.
- `python run_comfyvn.py --uvicorn-app comfyvn.server.app:create_app --uvicorn-factory` – run the server via the application factory if you need a fresh app per worker.

Environment variables honour the same knobs:

- `COMFYVN_SERVER_BASE` / `COMFYVN_BASE_URL` – default authority for the GUI, CLI helpers, and background workers (populated automatically from `--server-url` or the derived host/port).
- `COMFYVN_SERVER_AUTOSTART=0` – disable GUI auto-start of a local server.
- `COMFYVN_SERVER_HOST`, `COMFYVN_SERVER_PORT`, `COMFYVN_SERVER_APP`, `COMFYVN_SERVER_LOG_LEVEL` – default values consumed by the launcher when flags are omitted.
- Viewer helpers honour `COMFYVN_RENPY_PROJECT_DIR` (override the default `renpy_project` path), `COMFYVN_RENPY_EXECUTABLE` (explicit runtime binary), `COMFYVN_RENPY_SDK` (SDK folder), plus the feature flags `enable_viewer_webmode` and `enable_mini_vn`. See `docs/VIEWER_README.md` for the decision tree and API surface.
- Base URL authority lives in `comfyvn/config/baseurl_authority.py`. Resolution order: explicit `COMFYVN_BASE_URL` → runtime state file (`config/runtime_state.json` or cache override) → persisted settings (`settings/config.json`) → `comfyvn.json` fallback → default `http://127.0.0.1:8001`. The launcher writes the resolved host/port back to `config/runtime_state.json` after binding so parallel launchers, the GUI, and helper scripts stay aligned.
- When no `--server-url` is provided the launcher derives a connectable URL from the chosen host/port (coercing `0.0.0.0` to `127.0.0.1` etc.), persists it via the base URL authority, and exports `COMFYVN_SERVER_BASE`/`COMFYVN_BASE_URL`/`COMFYVN_SERVER_PORT` for child processes.
- Settings → **Network / Port Binding** now ships a web admin page at `/studio/settings/network.html` (token guard requires an admin role). It calls `/api/settings/ports/{get,set,probe}` to edit host, rollover ports, and optional public base overrides, mirrors the “would bind to” probe result, and surfaces ready-to-share curl drills for modders. Changes persist through `config/comfyvn.json` and update `.runtime/last_server.json`; see `docs/PORTS_ROLLOVER.md` for automation hooks.
- GUI → Settings → *Compute / Server Endpoints* now manages both local and remote compute providers: discover loopback servers, toggle activation, edit base URLs, and persist entries to the shared provider registry (and, when available, the running backend).
- Backend `features.enable_compute` now defaults to `false`. Enable it explicitly before wiring remote GPUs; compute APIs still respond while disabled but remote advice and cost previews stay informational only. After toggling, call `feature_flags.refresh_cache()` (or restart the backend) so long-lived workers see the change.
- Compute routes add structured debug hooks: append `?debug=1` to `/api/gpu/list` or `/api/providers`, post `{"debug": true}` to `/api/compute/advise` for advisor thresholds + queue snapshots, and use `/api/compute/costs` to preview base/transfer/VRAM costs without dispatching jobs. All responses echo the feature flag state so Studio and modders can surface clear guidance.
- The Settings panel also exposes a local backend port selector with a “Find Open Port” helper so you can avoid clashes with other services; the selection is saved to the user config directory (`settings/config.json`), mirrored to the current environment, and honoured by the next launcher run.
- Backend `/settings/{get,set,save}` endpoints now use the shared settings manager with deep-merge semantics, so GUI updates and CLI edits land in the same file without clobbering unrelated sections.
- Settings → **Debug & Feature Flags** hosts the ComfyUI hardened bridge toggle; once enabled the flag is persisted to `config/comfyvn.json` so subsequent ComfyUI submissions pick up prompt overrides, per-character LoRAs, and sidecar polling without needing to edit JSON by hand.
- Asset imports enqueue thumbnail generation on a background worker so large images stop blocking the registration path; provenance metadata is embedded into PNGs and, when the optional `mutagen` package is installed, MP3/OGG/FLAC/WAV assets as well.
- Install `mutagen` with `pip install mutagen` if you need audio provenance tags; without it the system still registers assets but skips embedding the metadata marker.
- The launcher performs a basic hardware probe before auto-starting the embedded backend. When no suitable compute path is found it skips the local server, logs the reason, and guides you to connect to a remote node instead of crashing outright.

## Asset Cache Maintenance

- A hash-based deduplication index now lives in `comfyvn/cache/cache_manager.py`. Each asset path tracks the blob digest, refcount, pin flag, and last-access timestamp so identical files collapse into one cached blob while retaining per-path metadata.
- Pinned entries (`pinned: true`) bypass LRU eviction, and refcounts decrement automatically when paths are released.
- Rebuild or audit the cache at any time with:

  ```bash
  python scripts/rebuild_dedup_cache.py --assets ./assets
  ```

  Add `--index /custom/path.json` to target a different cache file, `--max-entries` / `--max-bytes` to enforce limits during the rebuild, or `--no-preserve-pins` when performing a full reset.
- Generated indices persist under the runtime cache directory (see `comfyvn.config.runtime_paths.cache_dir`). Rebuild operations keep existing pins by default so curated assets remain protected across scans.

### Runtime Storage

ComfyVN Studio stores mutable state outside the repository using the platform-aware directories exposed by `comfyvn.config.runtime_paths` (`platformdirs` under the hood). By default:

- **Logs** live in the user log directory (for example `~/.local/share/ComfyVN Studio/logs` on Linux or `%LOCALAPPDATA%\ComfyVN Studio\Logs` on Windows). Files such as `system.log`, `gui.log`, `server_detached.log`, and timestamped `run-*` folders are written here.
- **Configuration** is persisted beneath the user config directory (`settings/config.json`, `settings/gpu_policy.json`, etc.). Override with `COMFYVN_CONFIG_DIR` or `COMFYVN_RUNTIME_ROOT` if you need a portable layout.
- **Workspaces & user data** are stored under the user data directory (e.g., `workspaces/`, saved layouts, and importer artefacts). Override with `COMFYVN_DATA_DIR`.
- **Caches** (thumbnails, audio/music caches, render scratch space) reside in the user cache directory; set `COMFYVN_CACHE_DIR` to relocate them.

Environment overrides include `COMFYVN_RUNTIME_ROOT` (sets all four roots), or the specific `COMFYVN_LOG_DIR`, `COMFYVN_CONFIG_DIR`, `COMFYVN_DATA_DIR`, and `COMFYVN_CACHE_DIR`. The package bootstraps legacy-friendly symlinks (`logs/`, `cache/`, `data/workspaces`, `data/settings`) when possible so existing scripts continue to function. If a conflicting file already exists at one of these paths, remove or relocate it so the directory can be created.

The GUI’s “Start Server” helper still delegates to `python comfyvn/app.py`, logging output to `server_detached.log` inside the user log directory, so manual invocations remain in sync with UI behaviour.

### Cloud Sync & Secrets Vault

- Feature flags: toggle `features.enable_cloud_sync` together with `features.enable_cloud_sync_s3` and `features.enable_cloud_sync_gdrive` in `config/comfyvn.json`. All default to **false** so offsite services stay opt-in.
- Docs: `docs/CLOUD_SYNC.md` (manifests, providers, API) and `docs/BACKUPS.md` (local archives) capture setup, IAM scopes, and recovery steps.
- Secrets vault: credentials live in `config/comfyvn.secrets.json`, encrypted with AES-GCM (PBKDF2-HMAC-SHA256 key derivation). Export `COMFYVN_SECRETS_KEY="<passphrase>"` before launching the backend so the vault can decrypt locally; each update keeps five encrypted backups inline for disaster recovery.
- GET manifest — inspect the current manifest and checksum without touching remote storage:
  ```bash
  curl "$BASE_URL/api/sync/manifest?snapshot=nightly&include=assets,config"
  ```
- Dry-run (S3) — plan only, no writes:
  ```bash
  curl -X POST "$BASE_URL/api/sync/dry_run" \
    -H 'Content-Type: application/json' \
    -d '{
      "service": "s3",
      "snapshot": "nightly",
      "paths": ["assets", "config"],
      "credentials_key": "cloud_sync.s3",
      "service_config": {"bucket": "studio-nightly", "prefix": "dev"}
    }'
  ```
  Returns `{manifest, plan, summary, remote_manifest}`, emits `on_cloud_sync_plan`, and reuses cached manifests when the provider SDK is missing.
- Run (Drive) — apply the plan; partial failures surface in `summary.errors` and keep the manifest untouched so re-runs stay idempotent:
  ```bash
  curl -X POST "$BASE_URL/api/sync/run" \
    -H 'Content-Type: application/json' \
    -d '{
      "service": "gdrive",
      "snapshot": "milestone-12",
      "credentials_key": "cloud_sync.gdrive",
      "service_config": {
        "parent_id": "<drive-folder>",
        "manifest_parent_id": "<manifest-folder>"
      }
    }'
  ```
- Local backups — zip selective folders before flipping flags or rotating credentials:
  ```bash
  curl -X POST "$BASE_URL/api/backup/create" \
    -H 'Content-Type: application/json' \
    -d '{"label": "pre-sync", "max_backups": 7}'
  ```
  Archives land in `backups/cloud/`, embed their manifest under `__meta__/cloud_sync/`, and honour rotation limits.
- Hooks & logs: `on_cloud_sync_plan` fires after dry-runs and `on_cloud_sync_complete` fires after runs (status + counts). Structured logs (`sync.dry_run`, `sync.run`, `backup.create`, `backup.restore`) land in `logs/server.log`; secrets never hit the log stream.

### Ren'Py Reference Project

The `renpy_project/` directory is a pristine sample used for rendering validations and export smoke tests. Treat it as read-only—copy assets out if you need to modify them, and keep build artefacts, saves, and caches out of the tree so the reference stays clean.

### Ren'Py Export Orchestrator

Use `python scripts/export_renpy.py --project <id>` to build a playable Ren'Py project under `build/renpy_game/`. Key helpers:

- Add `--dry-run` to print a diff against the current export without touching disk—ideal for pipeline previews. The FastAPI mirror lives at `GET /api/export/renpy/preview` so Studio and automation bots can surface the same diff payload to modders.
- Pass `--publish --publish-out exports/renpy/<name>.zip` to generate a deterministic archive containing `game/`, `publish_manifest.json`, and per-platform placeholders. Combine with `--invoke-sdk --renpy-sdk /path/to/renpy` when you want the orchestrator to call the Ren'Py launcher immediately after zipping.
- Use `--no-per-scene` to skip auxiliary `.rpy` modules or `--platform <id>` to customise placeholder folders for downstream packagers.
- `--pov-mode` (`auto`, `master`, `forks`, `both`, `disabled`) and `--no-pov-switch` govern POV-aware exports. In the default `auto` mode the orchestrator analyses scene/timeline metadata, emits a master build with an in-game “Switch POV” menu, and materialises per-POV forks under `forks/<slug>/`. Disable the menu when distribution bundles should select POV externally (e.g., standalone character routes).
- `--bake-weather` toggles deterministic weather/lighting baking (default inherits the `enable_export_bake` feature flag) and writes `<out>/label_manifest.json` with POV label coverage plus the `battle_labels` catalogue hashed for cache invalidation.
- Successful runs now drop `provenance_bundle.zip` and a readable `provenance.json` beside the export. The CLI summary echoes `provenance_bundle`, `provenance_json`, and `provenance_findings` so downstream jobs can archive or lint the provenance payloads without unpacking the archive.
- Modder hooks `on_export_started` / `on_export_completed` broadcast CLI runs (project, timeline, weather bake flag, label manifest path, provenance bundle status) so CI/CD can react without tailing logs.

See `docs/development_notes.md` for additional CLI samples, REST hooks, and environment toggles aimed at modders and tooling authors.

#### Steam & itch packagers

- Feature flags: enable `enable_export_publish` plus `enable_export_publish_{steam,itch}` in `config/comfyvn.json` when you want `/api/export/publish` online (they default to `false` so local builds stay private).
- `POST /api/export/publish` orchestrates the Ren'Py export and returns deterministic Steam/itch archives with `publish_manifest.json`, `license_manifest.json`, provenance sidecars, and per-platform builds. Pass `"dry_run": true` to receive diff summaries without touching disk; logs land in `logs/export/publish.log`.
- Supply optional `icon`, `eula`, or `license_path` fields to override the generated assets. When omitted, the packager writes placeholders so QA can run smoke checks without blocking on legal copy.
- Modder hooks `on_export_publish_preview` and `on_export_publish_complete` broadcast package metadata (`targets`, `platforms`, checksums, provenance sidecars) over the hook bus/WebSocket so automation can mirror release notes in Discord or CI dashboards without parsing ZIPs.

Example dry-run:

```bash
curl -s -X POST http://127.0.0.1:8001/api/export/publish \
  -H 'Content-Type: application/json' \
  -d '{
        "project": "demo",
        "label": "Demo Build",
        "version": "0.1.0",
        "dry_run": true,
        "platforms": ["windows","linux"],
        "targets": ["steam","itch"]
      }' | jq '.packages'
```

### Developer System Dependencies

Running the full pytest suite (especially GUI workflows powered by PySide6) requires a few EGL/X11 libraries to be present on the host OS. Debian/Ubuntu developers can install the curated list in `requirements-dev-system.txt` with:

```bash
sudo apt-get update
sudo xargs -a requirements-dev-system.txt apt-get install --yes
```

After system packages are in place, install the Python development extras (including `platformdirs`) with:

```bash
pip install -r requirements-dev.txt
```

Currently the file covers `libegl1`, `libxkbcommon0`, and `libdbus-1-3`; add new entries there whenever additional system packages are needed for tests.

## Debug & Verification Checklist

Embed this block (copy/paste) into every PR description so reviewers can confirm coverage:

- [ ] **Docs updated** — README, architecture docs, CHANGELOG, and `/docs` notes (include what changed and why).
- [ ] **Feature flags** — persisted in `config/comfyvn.json`; external services stay OFF by default.
- [ ] **API surfaces** — list endpoints added/modified with sample `curl` + expected JSON.
- [ ] **Modder hooks** — enumerate events/WS topics emitted (e.g., `on_scene_enter`, `on_asset_meta_updated`, `on_asset_removed`, `on_asset_sidecar_written`, `on_cloud_sync_plan`, `on_cloud_sync_complete`).
- [ ] **Logs** — structured log lines + error surfaces documented (note log file path like `logs/server.log`).
- [ ] **Provenance** — sidecars/metadata updated with tool/version/seed/workflow/pov context.
- [ ] **Determinism** — same seed + vars + POV ⇒ same next node (call out any intentional drift).
- [ ] **Windows/Linux** — sanity run (native or CI mock) on both platforms.
- [ ] **Security** — secrets pulled only from `config/comfyvn.secrets.json` (git-ignored).
- [ ] **Dry-run mode** — ensure any paid/public API call honours dry-run toggles.
- [ ] 🧪 Run `python tools/prompt_pack_linter.py <KIND> <file.json>` for prompt-pack payloads before merging.
- [ ] 🩺 Run `python tools/doctor_phase8.py --pretty` and confirm the report ends with `"pass": true`.
- [ ] 🧩 Image→Persona — keep `enable_image2persona` **off** by default, run `python tools/check_current_system.py --profile p6_image2persona --base http://127.0.0.1:8001`, and attach palette/anchor diffs if the analyzer output changed.
- [ ] 🎬 Editor UX — keep `enable_blocking_assistant` + `enable_snapshot_sheets` **off** by default, run `python tools/check_current_system.py --profile p6_editor_ux --base http://127.0.0.1:8001`, and include sample plan/sheet outputs or hook payloads when the behaviour changes.

## Logging & Debugging

- Server logs aggregate at `system.log` inside the user log directory. Override defaults with `COMFYVN_LOG_FILE`/`COMFYVN_LOG_LEVEL` before launching `uvicorn` or the CLI.
- GUI messages write to `gui.log`; launcher activity goes to `launcher.log` under the same directory.
- The Studio status bar now shows a dedicated “Scripts” indicator. Installers and scripted utilities update the indicator so failed runs surface as a red icon with the last error message while keeping the application responsive.
- CLI commands (e.g. `python -m comfyvn bundle ...`) create timestamped run directories under `run-*/run.log` in the user log directory via `comfyvn.logging_setup`.

## Tools & Ports

- CLI diagnostics (`python tools/check_current_system.py`, `python tools/doctor_phase_all.py`) now auto-discover the backend base URL by reading `config/comfyvn.json` (`server.host`, `server.ports`, `server.public_base`) and the `COMFYVN_BASE|HOST|PORTS` environment overrides. The first `/health` probe that responds becomes the active base; failures exit `2` and print the attempted URLs.
- Pin a specific backend in CI or remote staging with `--base` to bypass rollover probing. See `docs/PORTS_ROLLOVER.md` for the discovery order, debugging tips, and guidance on adding new ports.

## Policy Enforcement & Audit

- REST surface: `POST /api/policy/enforce` accepts `{action, bundle?, override?}` and returns `{allow, counts, findings, log_path}`. Example:

  ```bash
  curl -s -X POST "$BASE_URL/api/policy/enforce" \
    -H 'content-type: application/json' \
    -d '{"action": "export.bundle", "bundle": {"metadata": {"source": "docs-example"}}}' | jq
  ```

  Returns `{"ok": true, "result": {"allow": true, "counts": {"info":0,"warn":0,"block":0}, ...}}` when the bundle is clear.

- Timeline view: `GET /api/policy/audit?limit=25&export=1` responds with `events`, `summary`, and writes a JSON report under `logs/policy/policy_audit_<timestamp>.json` when `export=1`.
- Enforcement logs append to `logs/policy/enforcer.jsonl`; each entry captures the raw findings and whether the action proceeded.
- Modder hook bus now emits `on_policy_enforced` with `{action, allow, counts, blocked, warnings, log_path, timestamp}`, so tooling can subscribe via `/api/modder/hooks` or the WebSocket stream for real-time audit overlays.
- When tracking regressions, run `pytest tests/test_server_entrypoint.py` to confirm `/health`, `/healthz`, and `/status` remain reachable.
- The quick HTTP/WS diagnostics in `smoke_checks.py` exercise `/limits/status`, `/scheduler/health`, and the collab WebSocket. Run it while the backend is online to capture network traces.

## Health & Smoke Checks

Use the resolved base URL from `config/runtime_state.json` (written by the launcher) or by calling `comfyvn.config.baseurl_authority.default_base_url()` if you've changed ports.

- `curl "$BASE_URL/health"` validates the FastAPI wiring from `comfyvn.server.app`.
- `curl "$BASE_URL/healthz"` remains available for legacy tooling expecting the older probe.
- `python smoke_checks.py` performs REST + WebSocket checks against the current authority and prints any failures alongside connection debug information.
- `python scripts/smoke_test.py --base-url "$BASE_URL"` hits `/health` and `/system/metrics` (with an optional roleplay upload) and serves as the required pre-PR smoke test.

## Extension Development

See `docs/MARKETPLACE.md` for marketplace workflow details (manifest schema snapshots, trust allowlists, signature policy, CLI examples, and `/api/market/{list,install,uninstall,health}` curl recipes) alongside the Debug & Verification checklist in `docs/dev_notes_marketplace.md`. `docs/extension_manifest_guide.md` remains the exhaustive schema reference for extension authors.

## World Lore

- Sample world data lives in `defaults/worlds/auroragate.json` (AuroraGate Transit Station). Pair it with `docs/world_prompt_notes.md` and `comfyvn/core/world_prompt.py` to translate lore into ComfyUI prompt strings.
- New `features.debug_health_checks` flag lets Studio emit verbose health probe logs only when you need to diagnose backend startups—default off to keep console noise low while still surfacing failure reasons in the dashboard.
