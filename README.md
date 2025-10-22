🚀 Overview

This update transforms ComfyVN from a static scene exporter into a multi-layer, interactive VN engine that merges SillyTavern-style roleplay logs, ComfyUI rendering, and Ren’Py exports under one adaptive framework.

Highlights:

🛡️ Legal & Creative Responsibility
- You retain full creative freedom over the stories, assets, and exports you craft with ComfyVN. The platform provides guardrails—like the advisory scanner and liability gate—to surface risks, not to dictate content.
- Before distributing builds, acknowledge the legal terms once per installation (Studio: **Settings → Advisory**, CLI: `scripts/export_bundle.py` prompts on block-level findings). This acknowledgement records that you accept all downstream responsibility for compliance with licences, ratings, and local regulations.
- Block-level advisory findings halt exports; warnings flag items for manual review while keeping your workflow unblocked. See `docs/development/advisory_modding.md` for plugin hooks, troubleshooting, and override workflows.
- Contributors shipping mods or automation scripts should reference the debug/API matrix in the same doc to understand available hooks, expected audit trails, and how to publish their own scanners without restricting user choice.

🔒 Rating Matrix & SFW Gate
- `comfyvn/rating/classifier_stub.py` ships a conservative ESRB-style matrix (`E/T/M/Adult`) that scores prompts, metadata, and tags. Reviewer overrides persist to `config/settings/rating/overrides.json`, ensuring manual calls stay sticky across restarts.
- `/api/rating/{matrix,classify,overrides,ack,acks}` exposes review workflows. Classification returns `{rating, confidence, nsfw, ack_token}` so Studio and automation scripts can present warnings or request acknowledgement before continuing. Feature flag: `features.enable_rating_api`.
- SFW mode now gates high-risk prompts and exports by default. `/api/llm/test-call` and the Ren'Py orchestrator raise HTTP 423 with the issued `ack_token` until `/api/rating/ack` records the reviewer acknowledgement. CLI parity: `scripts/export_renpy.py --rating-ack-token <token> --rating-acknowledged`.
- Export manifests embed the resolved rating (`manifest.rating`) plus gate status, letting downstream pipelines enforce distribution policies or surface the info alongside provenance metadata.
- Modder hook bus gained `on_rating_decision`, `on_rating_override`, and `on_rating_acknowledged` (feature flag `enable_rating_modder_stream`). Subscribing via `/api/modder/hooks` or the WS stream lets tooling react to rating changes without polling the new API.

🧩 New Roleplay Import System

🌐 Live WebSocket JobManager

🪟 Expanded GUI with Tray Notifications

🌍 Enhanced World + Audio + Persona sync

⚙️ Unified Logging, Config, and Async Safety

🧱 Fully modular directory structure

🎨 Theme & World Changer
- Theme presets live in `comfyvn/themes/templates.py`, coordinating LUT stacks, ambience assets, music packs, and prompt styles across `Modern`, `Fantasy`, `Romantic`, `Dark`, and `Action`.
- `/api/themes/templates` hydrates Studio pickers; `POST /api/themes/apply` returns checksum-stable `plan_delta` payloads with `mutations` for assets, LUTs, music, prompts, and per-character overrides so you can preview tone swaps without triggering renders.
- Deterministic checksums make it safe to cache ambience mixes or thumbnails; use the same response as a diff source in automation scripts before queuing renders or advisory scans.
- Modder/CLI guidance lives in `docs/development/theme_world_changer.md` with curl examples, troubleshooting flow, and notes on chaining deltas with `/api/presentation/plan` or asset registry hooks.

🌦️ Weather, Lighting & Transitions
- `comfyvn/weather/engine.py` compiles world state (`time_of_day`, `weather`, `ambience`) into deterministic background-layer stacks, light rigs, transition envelopes, particle payloads, and ambience SFX. `WeatherPlanStore` exposes versioned snapshots with timestamps and hashes so exporters can diff quickly.
- `/api/weather/state` (GET/POST) updates or reads the shared planner without blocking the GUI. A shared feature flag (`enable_weather_planner`) under `config/comfyvn.json → features` lets deployments toggle the surface; Studio surfaces the switch under **Settings → Debug & Feature Flags**.
- Every plan update emits `on_weather_plan` over the modder hook bus with `{state, summary, transition, particles, meta}` so automation scripts can queue renders or bake overlays. Watch `logs/server.log` (logger name `comfyvn.server.routes.weather`) for structured updates that include hash, exposure shift, and particle type.
- Quick curl sample:
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/weather/state \
    -H 'Content-Type: application/json' \
    -d '{"weather": "rain", "time_of_day": "dusk"}' | jq '.scene.summary'
  ```
- Docs: `docs/WEATHER_PROFILES.md` captures presets, payload schema, feature flag setup, and modder automation tips; changelog coverage keeps exporters aligned with hash/version expectations.

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
- The new marketplace toolkit lives under `comfyvn/market/{manifest,packaging,service}.py`. `manifest` defines the JSON schema (metadata, permissions, trust envelopes, sandboxed routes) shared by both the loader and the packaging CLI. `service` owns catalog ingestion, install/uninstall flows, `.market.json` sidecars, and trust-level enforcement.
- Feature flags `enable_extension_market` and `enable_extension_market_uploads` default **OFF** inside `config/comfyvn.json`, keeping marketplace installs opt-in for production builds. Toggle via the Settings → Debug & Feature Flags drawer or by editing the config, then call `feature_flags.refresh_cache()` in long-lived workers.
- REST surfaces mount under `/api/market/*`: `GET /api/market/catalog` (catalog snapshot), `GET /api/market/installed` (local sidecars), `POST /api/market/install` (zip path payload), and `POST /api/market/uninstall` (extension id). Install logs emit structured entries (`event=market.install|market.uninstall`) to `logs/server.log` with the package digest and trust level for audit trails.
- Pack extensions with `bin/comfyvn_market_package.py <extension-root>` (or `python -m comfyvn.market.packaging`). The CLI normalises the manifest, enforces sandbox allowlists (non-verified archives cannot expose global routes), and writes deterministic `.cvnext` bundles with SHA-256 digests.
- Manifests declare permissions via known scopes (`assets.read`, `hooks.listen`, `ui.panels`, `api.global`, etc.) and list expected modder hooks (`hooks: [...]`) so contributors can wire dashboards or automation against `docs/dev_notes_modder_hooks.md`. Verified packages may expose allowlisted global routes (`/api/modder/*`, `/api/hooks/*`); unverified packages are sandboxed under `/api/extensions/{id}`.

🛠️ Modder Hook Bus & Debug Integrations
- `comfyvn/core/modder_hooks.py` fans out scenario (`on_scene_enter`, `on_choice_render`), asset (`on_asset_registered`, legacy alias `on_asset_saved`, `on_asset_meta_updated`, `on_asset_removed`, `on_asset_sidecar_written`), and planner (`on_weather_plan`) envelopes to in-process listeners, optional dev plugins (`COMFYVN_DEV_MODE=1`), REST webhooks, and the shared WebSocket stream.
- REST + WS surfaces: `GET /api/modder/hooks` exposes specs, history, and plugin host state; `POST /api/modder/hooks/webhooks` registers signed callbacks; `ws://<host>/api/modder/hooks/ws` streams `modder.on_*` topics with timestamps so automation dashboards can react without polling.
- Asset registry writes now broadcast the refreshed asset type, sidecar path, and metadata snapshot across `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, and `on_asset_sidecar_written`, aligning with `/assets/{list,upload,register,delete}` payloads and the structured logs under `logs/server.log` (`comfyvn.studio.core.asset_registry`) for provenance audits.
- New registry debug surfaces live under `/assets/debug/{hooks,modder-hooks,history}` so contributors can inspect active in-process callbacks, filter the Modder Hook Bus to asset events, and quickly diff hook payloads without standing up custom dashboards.
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
- Settings → **Accessibility** exposes sliders and toggles for font multiplier, filters, high contrast, and subtitles; Settings → **Input & Controllers** captures hotkeys via the shared `ShortcutCapture` widget and maps controller buttons (QtGamepad when available). Feature flags (`enable_accessibility_controls`, `enable_controller_profiles`, `enable_accessibility_api`) live in `config/comfyvn.json` and surface in the Debug drawer.
- The input map manager (`comfyvn/accessibility/input_map.py`) centralises keyboard/controller profiles, replays bindings to registered widgets (VN Viewer today), and broadcasts `on_accessibility_input_map` / `on_accessibility_input` modder hooks so automation can respond without polling.
- FastAPI routes `/api/accessibility/{state,filters,subtitle,input-map,input/event}` provide REST control. See `comfyvn/server/routes/accessibility.py` for request/response models and sample logging extras.
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
- **Feature Flags** panel persists toggles (including `enable_public_image_providers` and `enable_public_video_providers`, which keep the legacy `enable_public_image_video` flag in sync for automation) to `config/comfyvn.json`; changes broadcast through the notifier bus so Studio panels react instantly. Secrets for public providers live in `config/comfyvn.secrets.json` and are merged automatically when the backend builds dry-run payloads.
- Panels → **Log Hub** tails runtime logs (`gui.log`, `server.log`, `render.log`, `advisory.log`, `combined.log`) without leaving Studio. Inline Scenario Runner notes help designers correlate UI actions with backend events; modders can fetch `/api/modder/hooks/history` or subscribe to `ws://<host>/api/modder/hooks/ws` for deeper inspection.
- Viewer control routes (`POST /api/viewer/start`, `/stop`, `GET /api/viewer/status`) launch or embed the Ren’Py viewer. `docs/VIEWER_README.md` covers payload keys (`project_path`, `renpy_executable`, `renpy_sdk`) and environment overrides.
- Narrative automation can lean on the POV Rewrite prompt pack documented in `docs/PROMPT_PACKS/POV_REWRITE.md`, which mirrors the `on_scene_enter`/`on_choice_render` payloads so LLM tooling can restyle narration without diverging from canonical choices.

⚔️ Battle Layer Planner
- `comfyvn/battle/plan()` (new stub) returns a deterministic three-phase timeline (`setup`, `engagement`, `resolution`) while the full simulator is under construction. It records POV/world metadata and keeps payloads predictable for UI prototyping.
- `/api/battle/plan` is feature-gated by `enable_battle` and echoes `{plan, feature}` so Studio panels and automation scripts know when the simulation stack is offline. Docs outline how to swap in a real engine without breaking callers.
- Debug hooks: set `COMFYVN_LOG_LEVEL=DEBUG` to audit battle planning payloads; modders can emit custom envelopes with `POST /api/modder/hooks/test` to mirror plan updates in bespoke overlays.
- The Battle Narration prompt pack at `docs/PROMPT_PACKS/BATTLE_NARRATION.md` defines 4–8 beat JSON outputs that align with `/api/battle/{resolve,simulate}` responses and `vars_patch.battle_outcome`, keeping LLM narrators deterministic.

🌐 Public Provider Catalog & Dry-Run Adapters
- `/api/providers/{gpu,image-video,translate,llm}/public/catalog` returns curated pricing snapshots (RunPod, HF, Replicate, Modal, Runway, Pika, Luma, fal.ai, Google, AWS, DeepL, Deepgram, AssemblyAI, OpenAI, Anthropic, Gemini, OpenRouter, Azure) sourced from their current pricing sheets.
- Dry-run adapters in `comfyvn/public_providers/*` merge payloads with `config/comfyvn.secrets.json` and short-circuit network calls until operators flip the corresponding `enable_public_*` feature flag.
- `/api/providers/gpu/public/runpod/{health,submit,poll}` mirrors the RunPod adapter contract, returning deterministic IDs/status traces to unblock GUI testing. Translation and LLM endpoints follow the same pattern (`/google/translate` echoes inputs when keys are absent).
- `docs/WORKBOARD_PHASE7_POV_APIS.md` consolidates pricing anchors, review notes, ToS reminders, and recommended debug hooks + WebSocket topics for each track so contributors can spin up new adapters safely.

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
- REST helpers (`GET` unless noted) expose diagnostics and transcripts for modders and test harnesses: `health`, `presence/{scene_id}`, `snapshot/{scene_id}`, `history/{scene_id}?since=<version>`, and `POST /api/collab/flush`. Example probes: 

  ```bash
  curl -s $BASE/api/collab/health | jq
  curl -s $BASE/api/collab/presence/demo_scene | jq '.presence.control'
  curl -s $BASE/api/collab/history/demo_scene?since=0 | jq '.history | length'
  ```
- Server emits structured log lines (`collab.op applied ...`) to `logs/server.log` for replay and regression capture. The same payload reaches `on_collab_operation` on the modder bus and the WebSocket topic `modder.on_collab_operation`.
- Studio’s `TimelineView` attaches a `CollabClient` overlay displaying participants, cursor focus, and lock queue state. Local edits are diffed into CRDT ops so concurrent changes converge without losing nodes or metadata; remote snapshots are replayed through the editor automatically.
- Docs + debugging aids live in `docs/development_notes.md` (architecture) and `docs/DEBUG_SNIPPETS/STUB_DEBUG_BLOCK.md` (step-by-step verification checklist).

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
Introduced `comfyvn/translation/manager.py`, a lightweight language registry that persists active/fallback languages to `config/comfyvn.json`, merges inline tables with JSON overrides under `config/i18n/` and `data/i18n/`, and exposes a shared `t()` helper with automatic fallback.

New Bits: `comfyvn/translation/__init__.py`, `comfyvn/translation/manager.py`, `comfyvn/server/routes/translation.py`

Endpoints:

- POST `/api/translate/batch` → stubbed identity mapping to let clients shape MT payloads before real transformers land.
- GET `/api/translate/review/pending`, POST `/api/translate/review/approve`, and `/api/translate/export/{json,po}` power the TM review queue and export flow.

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
- Asset gallery tooling: Panels → Asset Gallery exposes filters, async thumbnails, bulk tag/license edits, and a clipboard debug exporter so modders can inspect sidecars without leaving Studio (see `docs/dev_notes_asset_registry_hooks.md`).
- Registry hook bus: `AssetRegistry.add_hook(event, callback)` surfaces `asset_registered`, `asset_meta_updated`, `asset_removed`, and `asset_sidecar_written` events for provenance or automation scripts. The Modder Hook bus now publishes `on_asset_registered`, `on_asset_saved` (alias), `on_asset_meta_updated`, `on_asset_sidecar_written`, and `on_asset_removed`; REST consumers can fetch the spec/history via `/assets/debug/{hooks,modder-hooks,history}` or subscribe over `/api/modder/hooks/ws`. Sidecars remain first-class APIs: fetch the parsed payload with `GET /assets/{uid}/sidecar` when diffing provenance or replaying renders. Deep-dive workflows live in `docs/dev_notes_asset_registry_hooks.md` and `docs/development/modder_asset_debug.md`.
- Advisory plugin & liability workflows: `docs/development/advisory_modding.md` covers acknowledgement flows, scanner extension points, and debug/API hooks for contributors building custom policy tooling.
- Debug toggles: `COMFYVN_LOG_LEVEL=DEBUG` raises verbosity; `COMFYVN_RUNTIME_ROOT` redirects runtime folders for sandboxing; asset registration logs include sidecar and thumbnail targets when running at debug level.
- Observability & privacy toolkit: `comfyvn/obs/` now bundles
  - anonymisation helpers (`anonymize_payload`, `hash_identifier`, `anonymous_installation_id`) that keep payloads deterministic while scrubbing IDs,
  - `TelemetryStore` with opt-in counters + hook sampling persisted to `logs/telemetry/usage.json`,
  - crash recorder integration that registers reports when `features.enable_crash_uploader` is toggled on.
  Feature flags (`enable_privacy_telemetry`, `enable_crash_uploader`) remain false by default and surface in **Settings → Debug & Feature Flags** alongside the `config/comfyvn.json → telemetry` opt-in block. FastAPI exposes `/api/telemetry/*` once the flag is enabled:
  ```bash
  # Enable local counters without enabling uploads
  curl -X POST http://localhost:8001/api/telemetry/settings \
       -H "Content-Type: application/json" \
       -d '{"telemetry_opt_in": true, "dry_run": true}'

  # Inspect aggregated feature usage + hook samples
  curl http://localhost:8001/api/telemetry/summary | jq

  # Record a custom modder event (automatically anonymised server-side)
  curl -X POST http://localhost:8001/api/telemetry/events \
       -H "Content-Type: application/json" \
       -d '{"event": "modder.on_asset_saved", "payload": {"uid": "abc123"}}'

  # Export a scrubbed diagnostics bundle (requires diagnostics opt-in)
  curl -OJ http://localhost:8001/api/telemetry/diagnostics
  ```
  Responses include hashed `anonymous_id`, per-feature counters, hook samples, and `crash` digests while omitting raw payloads. See `docs/development/observability_debug.md` & `docs/development_notes.md` for hook catalogues, WebSocket topics, and tailoring guidance for modders.
- Remote installer orchestrator: flip on **Settings → Debug & Feature Flags → Remote Installer** (persists `features.enable_remote_installer=false` by default) to access `/api/remote/modules` and `/api/remote/install`. The planner emits SSH-friendly install steps plus optional config sync descriptors for ComfyUI, SillyTavern, LM Studio, and Ollama. Each run appends to `logs/remote/install/<host>.log` and snapshots status to `data/remote/install/<host>.json`, enabling resumable automation.
  ```bash
  curl -X POST http://localhost:8001/api/remote/install \
       -H "Content-Type: application/json" \
       -d '{"host":"gpu.example.com","modules":["comfyui","ollama"]}'
  ```
  Responses include `{"status":"installed|noop","log_path":"...","status_path":"...","plan":[...]}` so toolchains can replay commands over SSH or diff planned steps via `"dry_run":true` before execution. See `docs/development_notes.md` for module metadata, log format, and tips on broadcasting structured events (e.g. task registry hooks) after each install step.
- Doctor Phase 4: run `python tools/doctor_phase4.py --base http://127.0.0.1:8000` to exercise `/health`, verify crash dumps, and ensure the structured logger is wired. The doctor emits a JSON report and returns non-zero when any probe fails, making it CI-friendly.
- Scenario E2E contract: `tests/e2e/test_scenario_flow.py` drives `/api/scenario`, `/api/save`, `/api/presentation/plan`, and `/api/export/*` endpoints against `tests/e2e/golden/phase4_payloads.json`. Update the golden file intentionally and call out payload changes in the changelog so modders can sync.
- Translation overrides: add locale files, then call `POST /api/i18n/lang` to refresh the active language during UI testing.
- SillyTavern bridge endpoints: `GET /st/health` now returns ping stats **plus** bundled vs installed manifest versions for the extension and comfyvn-data-exporter plugin, along with watch-path diagnostics. `GET /st/paths` surfaces the resolved copy targets. Use `POST /st/extension/sync` with `{"dry_run": true}` to preview copy plans (flip to `false` to write files), `POST /st/import` for `worlds`, `personas`, `characters`, or `chats`, and `POST /st/session/sync` to push the active VN scene/variables/history to SillyTavern and pull back a reply for the VN Chat panel (2 s timeout by default). Persona payloads continue to land in the registry while chat transcripts become Studio scenes automatically.
- Bridge debug helpers: export `COMFYVN_ST_EXTENSIONS_DIR` or `SILLYTAVERN_PATH` to override detection, set `COMFYVN_LOG_LEVEL=DEBUG` to log file-level copy operations, and watch `/st/health` for `watch_paths`, `alerts`, and version statuses (`extension.version_status`, `plugin.version_status`) so mismatches trigger proactive syncs.
- Modder quickstart notes live in `docs/dev_notes_modder_hooks.md`, summarising API payloads, expected sidecar outputs, and representative cURL invocations for each bridge/asset endpoint.
- Automation helpers: run `python tools/assets_enforcer.py --dry-run --json` to audit sidecar coverage in CI, or add `--fill-metadata` to backfill tags/licences from folder structure before committing assets.
- Studio developer tooling: enable Developer Tools to surface an inline request inspector for `/api/*` calls when building custom panels or external modding scripts.

🛰️ Phase 6 POV & Viewer Foundations
- Docs: `docs/WORKBOARD_PHASE6_POV.md`, `docs/POV_DESIGN.md`, `docs/VIEWER_README.md`, and `docs/LLM_RECOMMENDATIONS.md` outline the roadmap, manager/runner internals, viewer API, and adapter guidance for modders.
- API: `/api/viewer/{start,stop,status}`, `/api/pov/{get,set,fork,candidates}`, and `/api/llm/{registry,runtime,test-call}` are wired directly in `create_app()` so Studio, CLI, and automation clients share the same surface without requiring the unfinished `/api/llm/chat` proxy.
- GUI: the main window hosts a `CenterRouter` that defaults to the VN Viewer and registers the Character Designer stub; switching views keeps registries in sync and exposes quick actions for assets/timeline/logs.
- Config: new feature flags (`enable_st_bridge`, `enable_llm_proxy`, `enable_narrator_mode`) live in `config/comfyvn.json` with safe defaults.
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

Theme templates now live under `comfyvn/themes/templates.py`, pairing ambience and prompt styles across `Modern`, `Fantasy`, `Romantic`, `Dark`, and `Action`. Use `/api/themes/templates` to hydrate pickers and `POST /api/themes/apply` to generate checksum-stable `plan_delta` payloads (assets, LUTs, music, prompts, character overrides) before pushing renders or advisory scans. Debug and automation tips: `docs/development/theme_world_changer.md`.

🫂 Persona & Group Layout

Emotion blending and transitional tweening added.

Persona overlay for “User Character” implemented.

Group auto-layout based on Roleplay participants.

Persona state serialization to /data/persona/state.json.

Player Persona Manager panel syncs `/player/*` APIs, enabling roster imports, offline persona selection, and guaranteed active VN characters.

🔊 Audio & FX Foundation

Centralized audio_settings.json.

Adaptive layering plan (mood-based playback).

Thread-safe audio calls and volume normalization.

TTS speak requests now emit deterministic phoneme alignment and optional lipsync sidecars: call `/api/tts/speak` with `{"lipsync": true}` to receive `alignment[{phoneme,t_start,t_end}]`, on-disk `alignment.json`, and `lipsync.json` frame data so modders can drive lip rigs without extra tooling.

Scene mixes are orchestrated through `/api/audio/mix`, which accepts per-track gain/offsets plus ducking controls (`trigger_roles`, `amount_db`, `attack_ms`, `release_ms`) and caches WAV renders under `data/audio/mixes/<cache_key>/`. Sidecars record track metadata and ducking envelopes for repeatable exports.

Debug hooks: enable `LOG_LEVEL=DEBUG` to trace `comfyvn.server.routes.audio` and inspect generated assets under `data/audio/tts/<cache_key>/` and `data/audio/mixes/<cache_key>/`. Replays of the same payload reuse caches so contributors can diff downstream filters without re-rendering core stems.

🧬 LoRA Management

Async LoRA registry and sha256 verification.

Local index /data/lora/lora_index.json.

Prepared search hooks for GUI and persona consistency.
LoRA attachments authored via the Character Designer persist to `data/characters/<id>/lora.json`; the hardened bridge consumes them automatically during `/api/characters/render` runs and mirrors applied weights in asset metadata for modder scripts.

POV render pipeline auto-completes portraits via `/api/pov/render/switch`, caching renders by `(character, style, pose)` and injecting each character's LoRA stack through the hardened ComfyUI bridge.

Asset sidecars now record workflow id, prompt id, and the applied LoRA payloads; the originating ComfyUI sidecar is mirrored alongside the registered artifact for provenance diffs.

Enable `LOG_LEVEL=DEBUG` (or scope `comfyvn.pov.render`) to trace cache hits/misses and inspect generated assets under `assets/characters/<character>/<style>/`.

🧪 Playground Expansion

Scene mutation API stubs created.

Undo/Redo stack base implemented (collections.deque).

Safe auto-backup of live edits to /data/playground/history/.

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
- Viewer helpers honour `COMFYVN_RENPY_PROJECT_DIR` (override the default `renpy_project` path), `COMFYVN_RENPY_EXECUTABLE` (explicit runtime binary), and `COMFYVN_RENPY_SDK` (SDK folder). These map directly to the payload options accepted by `/api/viewer/start`; see `docs/VIEWER_README.md` for launch examples.
- Base URL authority lives in `comfyvn/config/baseurl_authority.py`. Resolution order: explicit `COMFYVN_BASE_URL` → runtime state file (`config/runtime_state.json` or cache override) → persisted settings (`settings/config.json`) → `comfyvn.json` fallback → default `http://127.0.0.1:8001`. The launcher writes the resolved host/port back to `config/runtime_state.json` after binding so parallel launchers, the GUI, and helper scripts stay aligned.
- When no `--server-url` is provided the launcher derives a connectable URL from the chosen host/port (coercing `0.0.0.0` to `127.0.0.1` etc.), persists it via the base URL authority, and exports `COMFYVN_SERVER_BASE`/`COMFYVN_BASE_URL`/`COMFYVN_SERVER_PORT` for child processes.
- GUI → Settings → *Compute / Server Endpoints* now manages both local and remote compute providers: discover loopback servers, toggle activation, edit base URLs, and persist entries to the shared provider registry (and, when available, the running backend).
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

- Feature flags: toggle `features.enable_cloud_sync` together with `features.enable_cloud_sync_s3` and `features.enable_cloud_sync_gdrive` in `config/comfyvn.json`. All default to `false` so offsite services stay opt-in.
- Secrets vault: credentials live in `config/comfyvn.secrets.json`, encrypted with AES-GCM. Export `COMFYVN_SECRETS_KEY="<passphrase>"` before launching the backend so the vault can decrypt locally. Each update keeps up to five encrypted backups inline under the `"backups"` key.
- Dry-run (S3) — plan only, no writes:
  ```bash
  curl -X POST "$BASE_URL/api/sync/dry-run" \
    -H 'Content-Type: application/json' \
    -d '{
      "service": "s3",
      "snapshot": "nightly",
      "paths": ["assets", "config"],
      "credentials_key": "cloud_sync.s3",
      "service_config": {"bucket": "studio-nightly", "prefix": "dev"}
    }'
  ```
  The response returns `{plan, manifest, summary}` over REST, emits `on_cloud_sync_plan`, and caches the manifest under `cache/cloud/manifests/s3/nightly.json` for idempotent replays.
- Run (Drive) — apply the plan and persist manifests:
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
  Successful runs upload changed files, refresh the remote manifest, store the local manifest (`cache/cloud/manifests/gdrive/milestone-12.json`), and emit `on_cloud_sync_complete` with upload/delete counts.
- Hooks & logs: `on_cloud_sync_plan` fires for dry-runs and `on_cloud_sync_complete` fires after a run completes. Both surface on the modder webhook/WS bus for dashboards or Discord bots. Structured logs land in `logs/server.log`; search for `sync.dry_run` or `sync.run`.

### Ren'Py Reference Project

The `renpy_project/` directory is a pristine sample used for rendering validations and export smoke tests. Treat it as read-only—copy assets out if you need to modify them, and keep build artefacts, saves, and caches out of the tree so the reference stays clean.

### Ren'Py Export Orchestrator

Use `python scripts/export_renpy.py --project <id>` to build a playable Ren'Py project under `build/renpy_game/`. Key helpers:

- Add `--dry-run` to print a diff against the current export without touching disk—ideal for pipeline previews. The FastAPI mirror lives at `GET /api/export/renpy/preview` so Studio and automation bots can surface the same diff payload to modders.
- Pass `--publish --publish-out exports/renpy/<name>.zip` to generate a deterministic archive containing `game/`, `publish_manifest.json`, and per-platform placeholders. Combine with `--invoke-sdk --renpy-sdk /path/to/renpy` when you want the orchestrator to call the Ren'Py launcher immediately after zipping.
- Use `--no-per-scene` to skip auxiliary `.rpy` modules or `--platform <id>` to customise placeholder folders for downstream packagers.
- `--pov-mode` (`auto`, `master`, `forks`, `both`, `disabled`) and `--no-pov-switch` govern POV-aware exports. In the default `auto` mode the orchestrator analyses scene/timeline metadata, emits a master build with an in-game “Switch POV” menu, and materialises per-POV forks under `forks/<slug>/`. Disable the menu when distribution bundles should select POV externally (e.g., standalone character routes).

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

## Logging & Debugging

- Server logs aggregate at `system.log` inside the user log directory. Override defaults with `COMFYVN_LOG_FILE`/`COMFYVN_LOG_LEVEL` before launching `uvicorn` or the CLI.
- GUI messages write to `gui.log`; launcher activity goes to `launcher.log` under the same directory.
- The Studio status bar now shows a dedicated “Scripts” indicator. Installers and scripted utilities update the indicator so failed runs surface as a red icon with the last error message while keeping the application responsive.
- CLI commands (e.g. `python -m comfyvn bundle ...`) create timestamped run directories under `run-*/run.log` in the user log directory via `comfyvn.logging_setup`.

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

See `docs/extension_manifest_guide.md` for the manifest schema, permission scopes, trust envelopes, and examples of registering REST routes + Studio panels. Packaging instructions (`bin/comfyvn_market_package.py`) and API samples (`/api/market/{catalog,install,uninstall}`) are documented alongside a Debug & Verification checklist.

## World Lore

- Sample world data lives in `defaults/worlds/auroragate.json` (AuroraGate Transit Station). Pair it with `docs/world_prompt_notes.md` and `comfyvn/core/world_prompt.py` to translate lore into ComfyUI prompt strings.
