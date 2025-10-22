ComfyVN Developer Notes
=======================

This document captures active hooks and helpers for modders, tool authors, and contributors.

Runtime Debugging
-----------------
- `COMFYVN_LOG_LEVEL=DEBUG` — elevates backend verbosity (server & CLI) so FastAPI routes and managers emit granular traces.
- `COMFYVN_RUNTIME_ROOT=/tmp/comfyvn-runtime` — redirects the runtime `data/`, `config/`, `cache/`, and `logs/` folders for sandboxing.
- Asset registry emits detailed provenance and sidecar logs when running at DEBUG level; combine with `COMFYVN_LOG_LEVEL=DEBUG` for full traces.
- Flat → Layers pipeline: enable `features.enable_flat2layers`, then watch hooks from `comfyvn.pipelines.flat2layers.FlatToLayersPipeline` (`on_mask_ready`, `on_plane_exported`, `on_debug`). Pair with `tools/depth_planes.py` for threshold tuning and the Playground SAM channel (`flat2layers.sam`) to record brush edits.
- Performance budgets & profiler: enable `features.enable_perf` (legacy `enable_perf_budgets` / `enable_perf_profiler_dashboard`) for local testing, then call `feature_flags.refresh_cache()` in long-running processes. REST helpers live under `/api/perf/*`; see `docs/PERF_BUDGETS.md`, `docs/dev_notes_observability_perf.md`, and `docs/development/perf_budgets_profiler.md` for curl examples, lazy asset eviction hooks, and the `on_perf_budget_state` / `on_perf_profiler_snapshot` modder envelopes.
- Integration guardrail: run `python tools/doctor_phase8.py --pretty` after touching router wiring, feature defaults, or modder hook specs. The doctor instantiates `create_app()` headless, asserts key debug surfaces (`/api/weather/state`, `/api/props/*`, `/api/battle/*`, `/api/modder/hooks`, `/api/viewer/mini/*`, `/api/narrator/status`, `/api/pov/confirm_switch`), checks for duplicate routes, validates the hook catalogue, and confirms feature defaults (Mini-VN/web viewer ON, external providers OFF, compute ON). CI should fail fast if the script reports `"pass": false`.

Dungeon Runtime & Snapshot Hooks
--------------------------------
- Feature flag `features.enable_dungeon_api` defaults **false**. Enable it in `config/comfyvn.json` before calling `/api/dungeon/*`; run `feature_flags.refresh_cache()` in REPLs to pick up edits without restarting.
- Session flow: `enter → step → (encounter_start → resolve)* → leave`. Responses carry deterministic `room_state`, optional `snapshot`, and `vn_snapshot` payloads with traversal history for Snapshot→Node/Fork.
- Modder hooks: `on_dungeon_enter`, `on_dungeon_snapshot`, `on_dungeon_leave`. Subscribe via `/api/modder/hooks?events=on_dungeon_snapshot` or the WebSocket mirror to monitor dungeon sessions.
- REPL helper:
  ```python
  from comfyvn.dungeon.api import API
  sid = API.enter({"backend": "grid", "seed": 1010})["session_id"]
  API.step({"session_id": sid, "direction": "north", "snapshot": True})
  API.resolve({"session_id": sid, "outcome": {"result": "victory"}})
  API.leave({"session_id": sid})
  ```
- Docs & verification: `docs/DUNGEON_API.md`, `docs/dev_notes_dungeon_api.md`, and `python tools/check_current_system.py --profile p3_dungeon --base http://127.0.0.1:8001`.

Narrator Outliner & Role Mapping
--------------------------------
- Feature flags: `features.enable_narrator` and `features.enable_llm_role_mapping` default to `false` in both `comfyvn/config/feature_flags.py` and `config/comfyvn.json`. Pass `"force": true` when issuing local curl drills, but keep production tooling flag-aware.
- REST rails (`comfyvn/server/routes/narrator.py`): `/api/narrator/{status,mode,propose,apply,stop,rollback,chat}` implement Observe → Propose → Apply with a deterministic proposal queue, three-turn per-node cap, and rollback ring buffer. Only `/api/narrator/apply` mutates variables; proposals queue `{vars_patch, rationale, choice_id}` for approval. Hook specs `on_narrator_proposal` and `on_narrator_apply` live in `comfyvn/core/modder_hooks.py`.
- Role orchestrator (`comfyvn/llm/orchestrator.py`): `/api/llm/{roles,assign,health}` expose offline-first role→adapter planning with sticky sessions, token budgets, and dry-run previews for Narrator/MC/Antagonist/Extras. When no adapter is armed the offline adapter (`offline.local`, model `codex/offline-narrator`) handles replies so tests remain network-free.
- VN Chat binding: `comfyvn/gui/central/chat_panel.py` sends prompts through `/api/narrator/chat`, surfaces adapter/model/tokens metadata per turn, and honours the role drawer. Offline replies reuse the planning digest so dashboards can correlate queue entries with chat previews.
- CI/automation: `python tools/check_current_system.py --profile p2_narrator --base http://127.0.0.1:8001` verifies flags, routes, and doc presence. Failures flip `"pass": false` to stop regressions early.
```bash
curl -s -X POST http://127.0.0.1:8001/api/narrator/propose \
  -H 'Content-Type: application/json' \
  -d '{"scene_id":"demo","node_id":"demo.root","message":"Check-in on the player.","force":true}' | jq '.state.queue'

curl -s http://127.0.0.1:8001/api/narrator/status?scene_id=demo | jq '.state.turn_counts'
```

Editor Blocking Assistant & Snapshot Sheets
-------------------------------------------
- Feature flags: `features.enable_blocking_assistant`, `features.enable_snapshot_sheets` (both default **false** in `config/comfyvn.json` and `comfyvn/config/feature_flags.py`).
- REST endpoints (`comfyvn/server/routes/editor.py`): `POST /api/editor/blocking` outputs deterministic shot/beat plans with digest + seed; `POST /api/editor/snapshot_sheet` composes PNG/PDF boards into `exports/snapshot_sheets/`.
- Modder hooks: `on_blocking_suggested` (plan digest, seed, shot/beat ids) and `on_snapshot_sheet_rendered` (sheet id, digest, output list, project/timeline metadata). Subscribe via `/api/modder/hooks` or the WebSocket stream for automation.
- Docs & drills: `docs/EDITOR_UX_ADVANCED.md` captures schemas/flags/hook payloads; `docs/development/dev_notes_editor_blocking.md` provides curl snippets, determinism reference, and troubleshooting steps.
- Verification: `python tools/check_current_system.py --profile p6_editor_ux --base http://127.0.0.1:8001`.

Viewer & Export Updates
-----------------------
- Fallback order: native embed → web (`/api/viewer/web/{token}/{path}`) → Mini-VN (`/api/viewer/mini/{snapshot,refresh,thumbnail}`). Feature flags `enable_viewer_webmode` and `enable_mini_vn` gate the behaviour.
- Mini-VN snapshot payloads surface `mini_digest` and thumbnail URLs; automation can call `/api/viewer/mini/refresh` with a deterministic seed to rebuild caches.
- Modder hook `on_thumbnail_captured` fires when thumbnails refresh.
- `scripts/export_renpy.py` / `/api/export/renpy/*` now raise `on_export_started` / `on_export_completed` and honour `--bake-weather` (`enable_export_bake` default). Successful exports write `<out>/label_manifest.json` summarising POV and battle labels; dry runs embed the manifest inline.
- Golden harness (`HeadlessPlaytestRunner`) now produces deterministic timestamps and offers `run_per_pov_suite(plan)` to capture the linear / choice-heavy / battle trio per POV. Reference `docs/GOLDEN_TESTS.md` for suite planning.

Security & Sandbox Audit
------------------------
- Encrypted secrets vault lives at `config/comfyvn.secrets.json`; manage it via `comfyvn/security/secrets_store.py` or the `/api/security/secrets/*` endpoints when `features.enable_security_api` is enabled. Generate/store `COMFYVN_SECRETS_KEY`, keep `config/comfyvn.secrets.key` git-ignored, and export overrides as `COMFYVN_SECRET_<PROVIDER>_<FIELD>`.
- Audit lines append to `${COMFYVN_SECURITY_LOG_FILE:-logs/security.log}` capturing `secrets.read`, `secrets.write`, `secrets.key.rotated`, and sandbox denials. Tail with `jq` or view through `GET /api/security/audit`.
- Plugin sandbox network guard defaults to strict mode (`features.enable_security_sandbox_guard`: true). Use `SANDBOX_NETWORK_ALLOW` or per-job `network_allow` to open specific hosts. Disable the flag only for legacy integrations.
- Modder hooks: subscribe to `security.secret_read`, `security.key_rotated`, and `security.sandbox_blocked` (WS topics) for dashboards and CI checks. Additional workflows and curl samples live in `docs/dev_notes_security.md`.

Observability & Privacy Telemetry
---------------------------------
- Feature flags: `features.enable_observability` (legacy `enable_privacy_telemetry`) and `features.enable_crash_uploader` default to `false`. Toggle them via **Settings → Debug & Feature Flags** or edit `config/comfyvn.json` and call `feature_flags.refresh_cache()` where needed.
- Consent storage: `/api/telemetry/settings` persists `{telemetry_opt_in, crash_opt_in, diagnostics_opt_in, dry_run}` under `config/comfyvn.json → telemetry`. Dry-run keeps telemetry local even when feature flags are enabled.
- Hashing helpers: import `from comfyvn.obs import anonymize_payload, hash_identifier` to scrub IDs before emitting custom events. The anonymiser stores a per-installation secret at `config/telemetry/anonymizer.json`; `anonymous_installation_id()` exposes a stable hash for correlating bundles without leaking raw IDs.
- API surface:
  - `GET /api/telemetry/summary` → `{anonymous_id, features, hooks, crashes, telemetry_active, crash_uploads_active, diagnostics_opt_in}`.
  - `POST /api/telemetry/features` with `{"feature": "on_asset_registered", "variant": "modpack"}` increments counters when telemetry is enabled.
  - `POST /api/telemetry/events` accepts arbitrary payloads; keys containing `id|uuid|path|token|email|user` are hashed automatically.
  - `GET /api/telemetry/hooks` lists hook counters plus the last five anonymised samples per event.
  - `GET /api/telemetry/diagnostics` returns a scrubbed zip (`manifest.json`, `telemetry.json`, `crashes.json`) once diagnostics opt-in is enabled.
- Modder hooks: `comfyvn/core/modder_hooks.emit` now forwards events into the telemetry store. Expect counters for `on_scene_enter`, `on_choice_render`, `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, `on_asset_sidecar_written`, `on_prop_applied`, `on_weather_changed`, `on_battle_simulated`, and more. Use `/api/telemetry/hooks` or the diagnostics bundle when auditing automation coverage.
- Logs & crash digests: telemetry counters live in `logs/telemetry/usage.json`; crash digests remain under `logs/crash/` and are registered with telemetry when crash uploads are enabled. Exported bundle filenames follow `comfyvn-diagnostics-<timestamp>-<anon>.zip`.

Playground Tiers
----------------
- Feature flags: `features.enable_playground` gates the new Playground tab in the Studio center router; `features.enable_stage3d` enables the Tier-1 WebGL stage inside that tab. Toggle both via **Settings → Debug & Feature Flags** and the UI will hot-load/unload the tab without restarting.
- Tier-0 (2.5D parallax) lives in `comfyvn/playground/parallax.py`; Tier-1 (`comfyvn/playground/stage3d/viewport.html`) embeds Three.js/VRM modules that we vendor under `comfyvn/playground/stage3d/vendor/` to stay offline. When bumping versions, refresh the vendor folder and keep the directory structure intact.
- `PlaygroundView` (Qt) exposes `register_hook("on_stage_snapshot" | "on_stage_load" | "on_stage_log", callback)` so tooling can react to user captures. Snapshots persist to `exports/playground/render_config.json` and include deterministic camera/layer/light data for Codex A automation.
- Runtime logs: center router logs snapshot paths via `_handle_playground_snapshot` and forwards stage warnings/errors through `_handle_playground_log`. Enable `COMFYVN_LOG_LEVEL=DEBUG` to watch Stage 3D loader callbacks, actor placement, and light edits in real time.
- CURL quickstart:
  ```bash
  # enable counters locally
  curl -X POST http://localhost:8001/api/telemetry/settings \
       -H "Content-Type: application/json" \
       -d '{"telemetry_opt_in": true, "dry_run": true}'

  # record a custom feature hit from an automation script
  curl -X POST http://localhost:8001/api/telemetry/features \
       -H "Content-Type: application/json" \
       -d '{"feature": "modder.asset.packaged"}'
  ```
Collaboration & Live Presence
-----------------------------
- Feature flag: `features.enable_collaboration` defaults to `true`. Disable it in hosted/solo builds to remove the `/api/collab/*` surfaces while keeping offline editors intact. Toggle via **Settings → Debug & Feature Flags** or edit `config/comfyvn.json`, then call `feature_flags.refresh_cache()` in long-lived processes.
- Core primitives — `comfyvn/collab/crdt.py` (Lamport-clock CRDT for scene fields, nodes, script lines) + `comfyvn/collab/room.py` (per-scene presence, request-control locks, dirty tracking). Hub wiring lives in `comfyvn/server/core/collab.py`, persisting snapshots through `scene_save()` with `{version, lamport}`.
- WebSocket contract: `ws(s)://<host>/api/collab/ws?scene_id=<id>` with headers `X-ComfyVN-User`, `X-ComfyVN-Name`. Messages: `doc.apply`, `doc.pull`, `presence.update`, `control.request`, `control.release`, `feature.refresh`, `ping`. Initial `room.joined` payload contains `{snapshot, presence, feature_flags}`.
- REST helpers: `POST /api/collab/room/{create,join,leave,apply}` (headless presence + debug ops), `GET /api/collab/room/cache`, `GET /api/collab/health`, `GET /api/collab/presence/<scene_id>`, `GET /api/collab/snapshot/<scene_id>`, `GET /api/collab/history/<scene_id>?since=<version>`, `POST /api/collab/flush`.
- Smoke probes:
  ```bash
  BASE=${BASE:-http://127.0.0.1:8001}
  curl -s "$BASE/api/collab/health" | jq
  curl -s "$BASE/api/collab/presence/intro" | jq '.presence.control'
  curl -s "$BASE/api/collab/history/intro?since=0" | jq '.history | length'
  ```
- Logs & hooks: `logs/server.log` emits `collab.op applied scene=<id> version=<n> ops=[...]`. Modder hook `on_collab_operation` mirrors the WebSocket payload and is also exposed via topic `modder.on_collab_operation`.
- GUI integration: `TimelineView` instantiates a reconnecting `CollabClient` (`comfyvn/gui/services/collab_client.py`) + `SceneCollabAdapter` that diff node-editor edits into CRDT ops, surface presence/lock overlays, and replay remote snapshots in <200 ms on LAN.
- Verification checklist: `docs/DEBUG_SNIPPETS/STUB_DEBUG_BLOCK.md` lists required smoke steps (docs, feature flag, API samples, hooks, logs, determinism, Windows/Linux sanity, secrets, dry-run). Copy the block into PR descriptions/releases for traceability.
- Automation tips: poll `/api/collab/history/<scene_id>?since=<version>` to rebuild state or subscribe to `modder.on_collab_operation` for streaming updates. Payload schema matches the CRDT wire format (`op_id`, `actor`, `clock`, `kind`, `payload`, `applied`).


Policy Enforcement & Audit
--------------------------
- Feature flag: `features.enable_policy_enforcer` (default `true`) enables the new enforcement pipeline. Toggle via **Settings → Debug & Feature Flags** and call `feature_flags.refresh_cache()` in long-lived processes.
- REST helpers:
  - `POST /api/policy/enforce` → returns `{allow, counts, findings, log_path, gate}` for the supplied bundle. Expect HTTP `423` with `result.blocked` when scanners emit `level: block`.
  - `GET /api/policy/audit?limit=25&export=1` → returns the latest enforcement events (`events`, `summary`) and writes a JSON report to `logs/policy/policy_audit_<ts>.json` when `export=1`.
- Logs: JSONL entries append to `logs/policy/enforcer.jsonl`; import/export responses bubble the enforcement decision under `enforcement` and provenance payloads include the raw findings.
- Modder hook: `on_policy_enforced` publishes `{action, allow, counts, blocked, warnings, log_path, timestamp}` to the REST + WebSocket surfaces (`/api/modder/hooks`, `/api/modder/hooks/ws`). Use this for dashboard overlays or CI alarms when builds trip hard policy rules.

Rating Gate & SFW Workflow
--------------------------
- Feature flags: `features.enable_rating_api` (routes + gating) defaults to true; `features.enable_rating_modder_stream` (modder hook emission) defaults to false. Use Settings → Debug & Feature Flags or edit `config/comfyvn.json` followed by `feature_flags.refresh_cache()` to toggle.
- Core module: `comfyvn/rating/classifier_stub.py` delivers the heuristic matrix, JSON-backed overrides, and acknowledgement tracking. Persistence path: `config/settings/rating/overrides.json`.
- REST API: `/api/rating/{matrix,classify,overrides,ack,acks}`. `classify` returns `{rating, confidence, nsfw, matched, ack_token}`; repeat the call with `acknowledged=true` and the confirmed token to unblock SFW workflows.
- Integrations: `/api/llm/test-call` and `RenPyOrchestrator.export` consume the gate, responding with HTTP 423 until `/api/rating/ack` records acknowledgement. CLI parity via `scripts/export_renpy.py --rating-ack-token <token> --rating-acknowledged`.
- Modder hooks (`on_rating_decision`, `on_rating_override`, `on_rating_acknowledged`) broadcast decisions when the stream flag is enabled, letting dashboards react without polling.
- Logging: rating decisions/overrides log through `comfyvn.rating`; blocked prompts/exports warn via `comfyvn.server.routes.llm` and `comfyvn.exporters.renpy_orchestrator`.

Debug & Verification Checklist
------------------------------
- [ ] **Docs updated** — README, architecture.md, CHANGELOG.md, docs/development_notes.md capture telemetry/anonymiser changes, curl samples, and debug hooks.
- [ ] **Feature flags** — `config/comfyvn.json → features` contains `enable_observability` (legacy `enable_privacy_telemetry`) and `enable_crash_uploader` (both default `false`); toggles surface in the Settings panel.
- [ ] **API surfaces** — `/api/telemetry/{summary,settings,events,features,hooks,crashes,diagnostics}` documented with sample requests/responses; dry-run keeps external calls disabled.
- [ ] **Modder hooks** — hook bus publishes `on_scene_enter`, `on_asset_saved`, `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, `on_asset_sidecar_written`, `on_prop_applied`, `on_weather_changed`, `on_battle_simulated`, etc.; telemetry captures counts/samples.
- [ ] **Logs** — structured events in `logs/telemetry/usage.json`; crash reports under `logs/crash/`; diagnostics bundle path returned by `/api/telemetry/diagnostics`.
- [ ] **Provenance** — telemetry bundle includes hashed crash summaries (event id, timestamp, exception type) and feature counters for reproducibility.
- [ ] **Determinism** — anonymiser uses per-installation keys so identical seeds/vars/pov yield identical hashes; bundle content is stable between runs when inputs match.
- [ ] **Windows/Linux** — runtime paths respect `COMFYVN_RUNTIME_ROOT`; telemetry/anonymiser directories are created via `runtime_paths.config_dir/logs_dir` for cross-platform compatibility.
- [ ] **Security** — telemetry & crash uploads honour dry-run + opt-in; no secrets leave `config/comfyvn.secrets.json`.
- [ ] **Dry-run mode** — `TelemetrySettings.dry_run` ensures automation can exercise endpoints without forwarding data externally.
- [ ] **Rating docs** — README, architecture.md, CHANGELOG.md, and `docs/dev_notes_rating_gate.md` reflect the matrix, gating flow, overrides, and ack workflow.
- [ ] **Feature flags** — `enable_rating_api` defaults true; `enable_rating_modder_stream` defaults false.
- [ ] **API surfaces** — `/api/rating/{matrix,classify,overrides,ack,acks}` documented with sample curl + ack flow.
- [ ] **Modder hooks** — `on_rating_decision`, `on_rating_override`, `on_rating_acknowledged` emit when the stream flag is enabled.
- [ ] **Logs** — rating classifier + gating warnings recorded under `comfyvn.rating`, `comfyvn.server.routes.llm`, and `comfyvn.exporters.renpy_orchestrator`.
- [ ] **Provenance** — export manifests store `{rating, rating_gate}` for downstream audits.
- [ ] **Determinism** — identical payloads yield consistent ratings; overrides pin the score with stored timestamps.
- [ ] **Windows/Linux** — override store path resolves via `config_dir("rating", "overrides.json")`.
- [ ] **Security** — overrides/acks remain local; no external services invoked by default.
- [ ] **Dry-run mode** — rating classifier operates locally; ack flow never triggers paid APIs.

Translation Manager
-------------------
- Locale overrides live under `config/i18n/<lang>.json`. Files follow a flat key/value map, e.g.:

  ```json
  {
    "ui.menu.play": "Play",
    "ui.menu.quit": "Quit"
  }
  ```

- Active/fallback languages are exposed at `GET /api/i18n/lang` and can be updated via `POST /api/i18n/lang` with `{ "lang": "es" }`.
- `POST /api/translate/batch` currently echoes `{src, tgt}` pairs; clients should treat the response shape as stable while we wire real MT providers.
- Use `comfyvn.translation.t("ui.menu.play")` in Python to fetch the active language string with an automatic fallback to the configured default.
- Public provider blueprint (`docs/development/public_translation_ocr_speech.md`) defines upcoming feature flags (`enable_public_translation_apis`, `enable_public_ocr_apis`, `enable_public_speech_apis`), diagnostics routes (`/api/providers/{translate,ocr,speech}/test`), and dry-run behaviour. Until adapters land these routes respond with `configured=false`, enabling tooling to surface setup guidance without raising.

Asset APIs
----------
- List/filter assets: `GET /assets` accepts `type`, `hash`, `tags`/`tag`, `q`, and `limit` query parameters. Filters are case-insensitive and cumulative; e.g. `curl '/assets?type=portrait&tags=hero&tags=modpack&q=summer&limit=50'`.
- Fetch metadata: `GET /assets/{uid}` returns the registered payload including sidecar data.
- Download source file: `GET /assets/{uid}/download`.
- Upload new asset: `POST /assets/upload` (multipart) with fields:
  - `file`: binary payload
  - `asset_type`: logical bucket (e.g. `portrait`, `bgm`)
  - `dest_path`: optional relative path under the assets root
  - `metadata`: JSON string (optional) supporting `{ "license": "CC-BY-4.0", "source": "modpack-01" }`
- Register existing file: `POST /assets/register` with JSON body:

  ```json
  {
    "path": "/abs/path/to/portrait.png",
    "asset_type": "portrait",
    "dest_path": "characters/hero/portrait.png",
    "metadata": { "artist": "modder42" },
    "copy": false
  }
  ```

- All write operations require the `assets.write` scope; REST clients should authenticate accordingly.
- Registry events: `AssetRegistry.add_hook(event, callback)` supports `asset_registered`, `asset_meta_updated`, `asset_removed`, and `asset_sidecar_written`. Hooks receive the asset payload (including sidecar metadata) and run on the GUI thread, so long-running work should delegate to background threads or enqueue jobs via the scheduler APIs below. Each hook also emits a Modder event (`on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, `on_asset_sidecar_written`, plus the legacy `on_asset_saved`) exposed through `/assets/debug/{hooks,modder-hooks,history}`, `/api/modder/hooks`, and the WebSocket fanout—see `docs/dev_notes_asset_registry_hooks.md` for curl/WebSocket samples and payload fields.
- Discovery helpers: `GET /assets/debug/{hooks,modder-hooks,history}` exposes registry listeners, filtered modder specs, and recent payloads, while `GET /assets/{uid}/sidecar` returns the parsed sidecar payload for provenance diffs or deterministic test fixtures.

Remote Installer Orchestrator
-----------------------------
- Feature flag: `features.enable_remote_installer` (default `false`) stored in `config/comfyvn.json`. Flip it via **Settings → Debug & Feature Flags** or patch the JSON then call `feature_flags.refresh_cache()` in long-lived workers.
- Discovery: `GET /api/remote/modules` returns module metadata (`id`, `name`, `tags`, `install_steps`, `config_sync`, `notes`) so GUIs/CLI tooling can render installers without hard-coding commands.
- Execution: `POST /api/remote/install` accepts `{"host": "...", "modules": ["comfyui","sillytavern"], "dry_run": false}` and records every step to `logs/remote/install/<host>.log`. Status manifests live at `data/remote/install/<host>.json` and include per-module state (`installed`, timestamps, tags).
- Dry run: set `"dry_run": true` to emit the plan without touching disk. Responses always echo the plan so automation can diff future runs before dispatching an SSH executor.
- Modder hooks: the orchestrator itself is dry (no SSH). Tail the log file or watch the status manifest for updates, then feed the recorded steps into your provisioning runner. Pair with `comfyvn.core.task_registry` if you want to publish structured events—register a job before invoking `/api/remote/install`, stream the log path to the UI, and close the job once your executor finishes each command.
- Failure handling: unknown modules are skipped with a log line but do not crash the install flow. Extend `comfyvn/remote/installer.py::_registry()` to add new modules (e.g., Stable Diffusion forks) and the REST surfaces will pick them up automatically once the feature flag is enabled.

Scenario Runner & POV Hooks
---------------------------
- Active perspective snapshots live at `GET /api/pov/get` (`{"pov": "...", "history": [...]}`). `POST /api/pov/set` swaps the POV (defaults to the manager’s configured narrator when omitted), while `POST /api/pov/fork` returns a deterministic save-slot suffix for the requested POV (`{"slot": "slot__pov_alice_2"}`).
- Candidate discovery: call `POST /api/pov/candidates` with the current scene payload (matches the Studio node editor output) to receive `{candidates: [{id,name,source}]}` covering cast + node metadata. Studio’s Scenario Runner uses this before populating breakpoint pickers.
- Runner integration: `/api/scenario/run/step` accepts `{scene, state?, seed?, choice_id?}` and returns `{"ok": true, "state": {...}, "node": {...}, "choices": [...]}`. Persist `state` with your save slots; pair with the POV fork helper to name slots per perspective.
- Viewer control surface: `POST /api/viewer/start` launches Ren’Py or a Tk stub. Optional payload keys include `project_path`, `project_id`, `renpy_executable`, and `renpy_sdk`. Stop or query with `POST /api/viewer/stop` / `GET /api/viewer/status`. Env overrides: `COMFYVN_RENPY_PROJECT_DIR`, `COMFYVN_RENPY_EXECUTABLE`, `COMFYVN_RENPY_SDK`.
- Logs stream to `logs/viewer/renpy_viewer.log`. Pair with the Studio Log Hub dock (`Panels → Log Hub`) or tail the file directly when troubleshooting viewer startups.
- Auto renders: `POST /api/pov/render/switch` wires POV updates into the hardened ComfyUI pipeline. Payloads such as `{"character_id": "alice", "style": "hero", "poses": ["neutral","smile"]}` return per-pose entries (`cached`, `asset_path`, `asset_sidecar`, `bridge_sidecar`, `loras[]`).
- Cache policy: renders dedupe by `(character, style, pose)` and store metadata alongside the asset (`assets/characters/<char>/<style>/<pose>.png`). Send `{"force": true}` to regenerate and refresh the cache entry.
- Debugging: set `LOG_LEVEL=DEBUG` (or scope `comfyvn.pov.render`) to trace cache hits/misses and sidecar copies. The pipeline mirrors the original ComfyUI sidecar as `<pose>.png.bridge.json` next to the registered asset for provenance tooling.
- Prompt pack: `docs/PROMPT_PACKS/POV_REWRITE.md` documents the strict narration/monologue/observations schema so LLM tooling can restyle node text while staying aligned with `on_scene_enter` / `on_choice_render` hook payloads.
- Hardened ComfyUI adapter: toggle from Studio via **Settings → Debug & Feature Flags** (`enable_comfy_bridge_hardening`). The checkbox persists to `config/comfyvn.json`, so CLI tooling and backend workers honour the same flag.
- Battle layer: `POST /api/battle/resolve` always returns `editor_prompt: "Pick winner"` plus deterministic breakdowns, weights, RNG state, provenance, and a predicted outcome; narration is optional via `"narrate": true`. `POST /api/battle/sim` (requires `enable_battle_sim`; `/simulate` aliases remain) returns `{outcome, seed, rng, weights, breakdown[], formula, provenance}` and only emits narration when requested. Set `COMFYVN_BATTLE_SEED` for deterministic defaults; `COMFYVN_LOG_LEVEL=DEBUG` logs roll breakdowns and RNG draws under the `comfyvn.battle.engine` logger.
- Battle narration prompt pack: `docs/PROMPT_PACKS/BATTLE_NARRATION.md` pairs with `/api/battle/{resolve,sim}` responses (choice + sim modes) and codifies the 4–8 beat JSON contract (`outcome`, `beats[]`, `vars_patch`) for deterministic automation; skip it by sending `"narrate": false`.
- Reference: `docs/POV_DESIGN.md` and `docs/VIEWER_README.md` expand on the contracts, fallback behaviour, and save-slot naming helpers.

Scheduler & Worker Hooks
------------------------
- Lifecycle endpoints: use `/api/schedule/enqueue` to push work items (payloads accept `queue` = `local`|`remote`, `priority`, `sticky_device`, and optional provider hints) and `/api/schedule/claim` from a worker loop to reserve the next job (`POST {"worker_id": "cli-worker-01"}`).
- Completion telemetry: workers should call `/api/schedule/complete` or `/api/schedule/fail` with `{job_id, status, bytes_tx, bytes_rx, vram_gb, duration_sec}` so the scheduler records `cost_estimate`, `duration_sec`, and transfer metrics. Provider metadata (see `/api/providers` or `config/compute_providers.json`) influences cost calculations.
- Debug snapshots: `/api/schedule/state` returns raw queue contents (active, queued, completed history) while `/api/schedule/board` emits a Gantt-friendly summary that the Studio Scheduler Board consumes. Capture `/board` diffs in CI to detect queue starvation or unexpected cost spikes.
- Hooks for modders: combine scheduler events with asset registry hooks to chain remote baking pipelines—enqueue renders after registering assets, then write back provenance or sidecars when completion payloads arrive.

LLM Registry & Chat Proxy
-------------------------
- Discovery: `GET /api/llm/registry` returns provider-neutral metadata from `comfyvn/models/registry.json`, including tags (`chat`, `translate`, `worldbuild`, `json`, `long-context`), base URLs, and adapter names. Consume this before hard-coding provider assumptions in tooling.
- Dry-run proxy: `POST /api/llm/test-call` mirrors OpenAI's message payload (`{"registry_id": "lmstudio_local", "model": "phi-3-mini-4k-instruct", "messages": [...]}`) and returns `{reply, raw, usage}` via the selected adapter (or echoes the last user turn when using the `stub` provider). Supports optional kwargs (`temperature`, `max_tokens`, etc.) that flow straight to the adapter.
- Environment overrides: export `COMFYVN_LLM_<PROVIDER>_BASE_URL`, `COMFYVN_LLM_<PROVIDER>_API_KEY`, `COMFYVN_LLM_<PROVIDER>_HEADERS` (JSON string), or `COMFYVN_LLM_<PROVIDER>_TIMEOUT` to adjust runtime behaviour without editing the registry file. A global `COMFYVN_LLM_DEFAULT_TIMEOUT` also applies when provider-specific timeouts are omitted.
- Debugging: run the backend with `COMFYVN_LOG_LEVEL=DEBUG` to trace adapter payloads; errors bubble up as `502` with contextual messages from the adapter. See `docs/LLM_RECOMMENDATIONS.md` for module-level defaults and cURL samples.

Developer UI Tools
------------------
- Studio → Settings → Developer Tools toggles the request inspector panel, logging the router, payload, and duration for each `/api/*` call made by the GUI.
- Savepoint APIs (`/api/save/{slot}`) are useful for scripted regression tests: pair `POST` and `GET` calls with the deterministic `ScenarioRunner` to snapshot and replay VN states.
- Extension loader writes panel mounts to the Studio “Extensions” card. See `docs/development/plugins_and_assets.md` for manifest schema, REST endpoints, and panel script helpers.

Release Communication
---------------------
- Architectural intent and acceptance criteria live in `ARCHITECTURE.md`; milestone deltas are tracked in `architecture_updates.md`.
- High-level progress pings should be recorded in `docs/CHANGEME.md` so downstream teams can track doc refreshes and tooling hooks that affect their workflows.

Ren'Py Export Hooks
-------------------
- Use `python scripts/export_renpy.py --project <id> --dry-run` to preview scene graph and asset changes without writing to disk. The JSON response lists per-file diff status (`new`, `modified`, `unchanged`) plus short unified diffs for `.rpy` files so modders can inspect script mutations quickly.
- The backend mirrors this behaviour at `GET /api/export/renpy/preview?project=<id>[&timeline=<id>]`. Automation bots can surface the same payload to chat channels, and Studio panels can offer a "Preview Export" button without shell access.
- A successful export writes `export_manifest.json` summarising background/portrait provenance, missing asset references, and SHA256 digests. Downstream tooling should ingest this manifest when building mod packs or validating asset provenance.
- `--publish` adds a deterministic zip named via `--publish-out`; each platform placeholder (customise with `--platform <name>`) ships a README instructing modders where to drop final builds, making the archive safe for version control diffs.
- Add `--invoke-sdk --renpy-sdk /path/to/renpy-sdk` to chain into Ren'Py's launcher `distribute` command once the zipped payload is ready. Capture the resulting stdout/stderr from the JSON response to debug failing CLI invocations.

LLM Proxy & Emulation
---------------------
- SillyCompatOffload flag: toggle via `/api/emulation/toggle` or set `COMFYVN_SILLY_COMPAT_OFFLOAD=1`; status lives at `/api/emulation/status`.
- Persona seeds: `/api/emulation/persona` accepts `{persona_id, memory?, style_guides?, safety?, metadata?}`; chat proxies the LLM registry via `/api/emulation/chat`.
- Neutral adapters: `/api/llm/registry` lists providers/models, `/api/llm/test-call` exercises adapters without hitting paid endpoints, and the planned `/api/llm/{chat,prompt-pack}` routes remain tracked in `docs/CODEX_STUBS/2025-10-21_PUBLIC_LLM_ROUTER_AND_TOP10_A_B.md`.
- Tuning cheatsheet: `docs/LLM_RECOMMENDATIONS.md` outlines temperature/top_p defaults; update alongside `comfyvn/models/registry.json` when swapping providers.
- Debugging: raise `COMFYVN_LOG_LEVEL=DEBUG` to log adapter payloads and persona history; call `comfyvn.models.registry.refresh_registry()` after editing the registry file.

Asset Debug Hooks
-----------------
- Set `COMFYVN_ASSETS_ROOT=/path/to/modpack/assets` before launching the backend to stage a temporary asset sandbox without moving the canonical repository files. Pair with `COMFYVN_RUNTIME_ROOT` when running experiments you plan to discard.
- Run `python tools/rebuild_asset_registry.py --assets-dir <assets> --db-path comfyvn/data/comfyvn.db` after bulk edits to reconcile the registry with on-disk changes; the script replays sidecar metadata and highlights any failures.
- Call `GET /assets/?type=portrait&limit=500` (or any supported `type=` filter) to verify that new files registered under the expected buckets before promoting them to production branches.
- Trigger `GET /api/export/renpy/preview` before and after hooking a new asset pack; the `missing_assets` section highlights backgrounds/portraits that still need coverage while the diff entries confirm copied files.
