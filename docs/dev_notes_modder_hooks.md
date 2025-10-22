# ComfyVN Modder Hooks & Debug Notes

Updated: 2025-11-10 • Scope: Bridge, Asset, and Scene tooling surfaces  
Owner: Project Integration (Chat P) — share feedback in `CHAT_WORK_ORDERS.md`

This companion note aggregates the entry points modders and contributors can rely on
when extending ComfyVN. It focuses on REST payloads, debug toggles, and filesystem
sidecars that are safe to automate against during the v0.7 run-up.

---

> Integration tip: `python tools/doctor_phase8.py --pretty` now exercises the modder hook catalogue alongside key REST routes (battle/props/weather/viewer/narrator/pov). Add it to automation pipelines after tweaking hooks or feature flags—the script emits `"pass": true` when the expected topics remain available.

## 1. Bridge & Import APIs

### 1.1 SillyTavern extension sync
- `GET /st/paths` → resolved source/destination, bundled manifest version, plugin
  package info, and `watch_paths` for health monitors.
- `GET /st/health` → ping timings + HTTP status, merged configuration snapshot, `alerts`
  when manifests diverge, and `versions.extension` / `versions.plugin` comparing bundled,
  installed, and remote plugin manifests. `plugin_needs_sync` flags mismatched
  comfyvn-data-exporter installs.
- `POST /st/extension/sync` →
  ```jsonc
  {
    "dry_run": true,
    "source": null,
    "destination": null,
    "extension_name": "ComfyVN"
  }
  ```
  Set `dry_run=false` to perform the copy. Responses echo manifest versions and the
  actions list (`create`, `update`, `skip`, `mkdir`) so CI scripts can diff results.
- Environment overrides: export `COMFYVN_ST_EXTENSIONS_DIR` for a direct destination
  or `SILLYTAVERN_PATH` for auto-detection. Debug mode (`COMFYVN_LOG_LEVEL=DEBUG`)
  logs each copy decision to `logs/server.log`.

### 1.2 SillyTavern payload imports
- Endpoint: `POST /st/import` with `{"type": "<worlds|personas|characters>", "data": ...}`.
- Worlds → persisted with `WorldLoader.save_world`, returns `{"filename": "<name>.json"}`.
- Personas → normalised via `SillyPersonaImporter` (character registry + persona profile),
  returns lists of registered personas/characters plus any errors.
- Characters → upserts through `CharacterManager.import_character`. Use when persona JSON
  and character JSON are delivered separately.
- Active payloads (`{"type": "active"}`) allow extensions to hint the currently focused
  world; the loader updates `WorldLoader.active_world` for GUI/CLI consumers.

### 1.3 ST chat importer pipeline
- Feature flag `enable_st_importer` (default **false**) gates the importer. Toggle through **Settings → Debug & Feature Flags** or edit `config/comfyvn.json` and call `feature_flags.refresh_cache()`.
- `POST /api/import/st/start` accepts a multipart form with `projectId` plus one of `file`, `text`, or `url`. SillyTavern `.json` and roleplay `.txt` exports are normalised into canonical turns (`imports/<runId>/turns.json`) and mapped into scenario graphs (`imports/<runId>/scenes.json`). Scenes are written to `data/scenes/<scene>.json` and appended to `data/projects/<projectId>.json` under `imports.st_chat[]`.
- `GET /api/import/st/status/{runId}` reports `{phase, progress, scenes, warnings, preview}` so dashboards can follow the run. Phases: `initializing → parsed → mapped → completed`; failures populate `error` and leave the run in `failed`.
- Artefacts:
  - `imports/<runId>/turns.json` — normalised transcript for debugging/diffing.
  - `imports/<runId>/scenes.json` — generated scenario payloads (line/choice/end nodes).
  - `imports/<runId>/preview.json` — summary (`scene_count`, `turn_count`, participants).
  - `imports/<runId>/status.json` — progress tracker with timestamps, warnings, preview path.
- Modder hooks fire for automation:
  - `on_st_import_started` → `{run_id, project_id, source, timestamp}`
  - `on_st_import_scene_ready` → `{run_id, project_id, scene_id, title, participants, warnings}`
  - `on_st_import_completed` → `{run_id, project_id, scene_count, warnings, status, preview_path}`
  - `on_st_import_failed` → `{run_id, project_id, error, timestamp}`
  Subscribe via `/api/modder/hooks/ws` or `modder_hooks.register_listener()` to mirror progress in CI/dashboard tooling. Structured logs land under `comfyvn.server.routes.import_st` when `COMFYVN_LOG_LEVEL=DEBUG`.
- Docs: `docs/ST_IMPORTER_GUIDE.md` covers export steps, API payloads, heuristics, and troubleshooting. Companion dev note: `docs/dev_notes_st_importer.md`.

### 1.4 SillyTavern session sync
- Endpoint: `POST /st/session/sync`
- Purpose: push the current VN scene ID, POV, variable map, and recent chat turns to
  SillyTavern (via comfyvn-data-exporter) and pull back a reply payload tailored for
  the VN Chat panel.
- Payload (example):
  ```jsonc
  {
    "scene_id": "demo_scene",
    "pov": "narrator",
    "variables": {"mood": "tense"},
    "messages": [
      {"role": "narrator", "content": "You enter the room."},
      {"role": "alice", "content": "Welcome back!"}
    ],
    "limit_messages": 40,
    "timeout": 2.0
  }
  ```
- Response fields:
  - `reply` → raw plugin payload (string or object) returned by SillyTavern.
  - `panel_reply` → normalised `{role, content, emotion?, meta?}` entry ready for the
    VN Chat panel; `reply_text` duplicates the content string for convenience.
  - `message_count` → how many turns were transmitted after trimming.
  - `context` → the exact payload forwarded to the plugin (after resolving scene data
    from `SceneStore` when `scene_id` is supplied).
  - `latency_ms` → measured round-trip latency; default timeout is 2 s.
  - `alerts` surface mismatch warnings inherited from `/st/health` when the bridge is
    also polled (see Section 1.1).
- Set `"dry_run": true` to preview the payload formatting without contacting
SillyTavern. Supply `"limit_messages": 0` to forward the entire history.

### 1.5 Bridge feature flags
- Flags live under `config/comfyvn.json → features`. Studio exposes toggles in **Settings → Debug & Feature Flags**, and `comfyvn/config/feature_flags.py` offers helpers (`load_feature_flags()`, `is_enabled()`, `refresh_cache()`).
- `enable_comfy_preview_stream` disables hardened preview polling when false, letting custom render bridges avoid writing manifests in development environments.
- `enable_sillytavern_bridge` gates every SillyTavern helper (`WorldLoader.sync_from_sillytavern`, `STSyncManager`, `/st/health`). When the flag is off these entry points return `{"status": "disabled"}`, signalling automation to skip bridge calls gracefully.
- `enable_narrator_mode` toggles the inline VN Chat overlay beneath the viewer; leave it disabled when scripting raw Ren'Py embedding or external narrator dashboards.
- CLI/scripts should call `feature_flags.refresh_cache()` after mutating `config/comfyvn.json` so long-lived processes pick up flag changes immediately.

### 1.6 Quick CLI tests
```bash
curl -s http://127.0.0.1:8001/st/health | jq
curl -s http://127.0.0.1:8001/st/paths | jq '.sync.watch_paths'
curl -s -X POST http://127.0.0.1:8001/st/extension/sync \
  -H 'Content-Type: application/json' \
  -d '{"dry_run": true}' | jq '.actions[:5]'
curl -s -X POST http://127.0.0.1:8001/st/import \
  -H 'Content-Type: application/json' \
  -d @docs/samples/st_personas_sample.json | jq '.personas | length'
run_id=$(curl -s -X POST http://127.0.0.1:8001/api/import/st/start \
  -F projectId=demo-import \
  -F 'text=Aurora: Welcome back!\nYou: Choice: Ask about the relic\nYou: > Leave' | jq -r '.runId')
echo "run_id=${run_id}"
curl -s "http://127.0.0.1:8001/api/import/st/status/${run_id}" | jq '{phase, progress, warnings}'
curl -s -X POST http://127.0.0.1:8001/st/session/sync \
  -H 'Content-Type: application/json' \
  -d '{"scene_id":"demo_scene","messages":[{"role":"narrator","content":"Ping from CLI"}],"dry_run":true}' | jq '.context'
```

### 1.7 Persona importer & community connector hooks
- Feature flag `enable_persona_importers` (default **false**) gates `/api/persona/{consent,import/text,import/images,map,preview}`. Without consent, each route returns HTTP 403.
- Persona mapping emits `on_persona_imported` with `{persona_id, persona, character_dir, sidecar, image_assets, sources, requested_at}` so dashboards/webhooks can mirror persona payloads and provenance sidecars.
- Community connector routes (`/api/connect/flist/*`, `/api/connect/furaffinity/upload`, `/api/connect/persona/map`) introduce three additional hook payloads:
  - `on_flist_profile_parsed` → fired after an F-List profile is parsed, includes `{persona_id, persona, warnings, debug, requested_at}`.
  - `on_furaffinity_asset_uploaded` → triggered per upload batch, returning `{persona_id, assets[], debug[], requested_at}` with hashed paths/sidecars.
  - `on_connector_persona_mapped` → mirrors `on_persona_imported` but scopes to connector flows; payload includes `provenance` (sidecar path) so automation can trace connector imports separately.
- Subscribe via:
  ```bash
  websocat ws://127.0.0.1:8001/api/modder/hooks/ws \
    | jq 'select(.event | test("on_(persona_imported|connector_persona_mapped|flist_profile_parsed|furaffinity_asset_uploaded)"))'
  ```
  or register a REST webhook:  
  `curl -s -X POST http://127.0.0.1:8001/api/modder/hooks/webhooks -d '{"event":"on_persona_imported","url":"https://example.org/hook"}'`
- Debug docs: `docs/PERSONA_IMPORTERS.md`, `docs/COMMUNITY_CONNECTORS.md`, `docs/NSFW_GATING.md`, `docs/dev_notes_persona_importers.md`, and `docs/dev_notes_community_connectors.md`. Use `python tools/check_current_system.py --profile p6_persona_importers` and `python tools/check_current_system.py --profile p7_connectors_flist_fa` after toggling flags to confirm route/hook coverage.

---

## 2. Asset & Registry Hooks

### 2.1 REST surface
- `GET /assets` supports `type`, `hash`, repeated `tags=`/`tag=`, and `q` (case-insensitive path/metadata substring) filters; returns provenance metadata. Combine them freely, e.g. `curl '/assets?type=portrait&tags=hero&tags=modpack&q=summer'`. See `docs/development/asset_debug_matrix.md` for additional curl/WebSocket recipes.
- `POST /assets/register` registers loose files and produces `<asset>.asset.json`
  sidecars, thumbnails, and registry rows.
- `POST /assets/upload` accepts multipart uploads with optional `target_type` metadata.

### 2.2 Debug environment variables
- `COMFYVN_RUNTIME_ROOT` → redirect runtime storage (helps when scripting in sandboxes).
- `COMFYVN_ASSET_CACHE_STRICT=1` → fail fast when sidecar generation detects collisions.
- `COMFYVN_LOG_LEVEL=DEBUG` → extends asset logs to include generated thumbnail paths and
  provenance chain details.

### 2.3 Sidecar expectations
- Character sprites: `assets/characters/<id>/<file>` with `<file>.asset.json` describing
  tags, hashes, and sprite slices.
- Audio: `data/audio/mixes/<cache_key>/mix.wav` plus `mix.asset.json`, `ducking.json`,
  and `alignment.json` when generated via `/api/audio/mix` or `/api/tts/speak`.
- Scenes: `data/scenes/<scene_id>.json` created via SceneStore or `/st/import` chat ingestion.

### 2.4 POV & Viewer debug taps
- `GET /api/pov/get` mirrors the viewer header; append `?debug=true` to include runner context (active filters + history).
- `POST /api/pov/fork` supports asset automation: send `{"slot": "save-1", "pov": "alice"}` and reuse the returned suffix when rendering POV-specific thumbnails.
- `POST /api/pov/candidates` accepts either `{ "scene": {...} }` or a raw scene mapping and returns filtered POV candidates. Add `"debug": true` to receive per-filter traces.
- `/api/pov/worlds` returns named POV worldlines with metadata (`nodes`, `choices`, `assets`, `lane`, `lane_color`, `parent_id`) plus `_wl_delta` so callers can inspect the stored delta over the parent. `POST /api/pov/worlds` upserts entries (set `"activate": true` to switch) and accepts inline `snapshot` payloads which now echo `workflow_hash` + `sidecar` fields; `/api/diffmerge/{scene,worldlines/graph,worldlines/merge}` (feature flag `enable_diffmerge_tools`) surfaces POV-masked node diffs, timeline graphs, and dry-run/apply merges. `/api/pov/auto_bio_suggest` summarises deltas, recent snapshots, and optional diffs for bios/dashboards. Exports echo the resolved selection in `export_manifest.json["worlds"]`, and the CLI/server preview accept `--world` / `--world-mode` for canonical vs multi-world builds (see `docs/development/pov_worldlines.md`). Modder hooks `on_worldline_diff` / `on_worldline_merge` forward delta summaries, fast-forward flags, and merge conflicts in realtime for dashboards or CI bots.
- Timeline overlay stack (feature flags `enable_worldlines` + `enable_timeline_overlay`) unlocks `/api/pov/confirm_switch` plus fork-on-confirm flows. Snapshot payloads follow the cache-key recipe `{scene,node,worldline,pov,vars,seed,theme,weather}` and now add provenance metadata (`workflow_hash`, `sidecar`). The system emits:
  - `on_worldline_created` when a lane is first registered or forked (payload includes `delta`, lane colour, and parent id).
  - `on_snapshot` after `WorldlineRegistry.record_snapshot()` writes thumbnail metadata (hash, badges, lane color, timestamp) and now mirrors `workflow_hash`, `sidecar`, and `worldline` fields for automation.
- Hook consumers should subscribe to `modder.on_worldline_created` / `modder.on_snapshot` via `/api/modder/hooks/ws` to keep dashboards aligned with Studio’s Ctrl/⌘-K workflow.
- `GET /api/viewer/status` returns `{ "running": false, "project_id": null, ... }` so out-of-process tools can stay in sync with the Studio center without Qt bindings.
- Character Designer stubs live in the center router. API scaffolding (`/api/characters{,/save}`) is planned for Phase 6B; rely on the shared registry helpers in the meantime.

### 2.5 Character Designer & Hardened renders
- Storage layout: character metadata now lives at `data/characters/<id>/character.json`; LoRA attachments persist to `data/characters/<id>/lora.json`. Legacy flat files (`data/characters/<id>.json`) are still written for older tooling, but new automation should target the folder layout.
- `GET /api/characters` → `{ok, data:{items:[{id,name,tags,pose,expression,loras[],avatars[]}],count}}`. LoRA entries surface `{path, weight?, clip?}` and avatars include the latest registered assets.
- `POST /api/characters/save` accepts:
  ```jsonc
  {
    "id": "alice",
    "name": "Alice",
    "tags": ["hero", "vn"],
    "pose": "arms_crossed",
    "expression": "determined",
    "meta": {"tone": "optimistic"},
    "loras": [
      {"path": "models/loras/alice.safetensors", "weight": 0.8}
    ]
  }
  ```
  The route writes `character.json`, mirrors LoRA payloads to `lora.json`, and returns the normalised record (including stored LoRAs and avatars).
- `POST /api/characters/render` accepts `{"id": "alice", "kind": "portrait"}` (or `"fullbody"`), injects saved LoRAs into the hardened bridge, and responds with:
  ```jsonc
  {
    "ok": true,
    "data": {
      "asset": {
        "uid": "9f1b…",
        "path": "characters/alice/portrait/20251101-120530_output.png",
        "thumb": "cache/thumbs/…",
        "sidecar": "data/assets/…/output.asset.json"
      },
      "character": {"id": "alice", "avatars": [...], "loras": [...]},
      "bridge": {"workflow_id": "character.portrait", "prompt_id": "..."}
    }
  }
  ```
  Registered assets emit the local `asset_registered` hook plus the Modder Hook bus topics `modder.on_asset_registered`, `modder.on_asset_meta_updated`, and `modder.on_asset_sidecar_written`, each carrying provenance + sidecar paths so automation scripts can chain additional processing. Deletions publish `modder.on_asset_removed` before files are trashed.
- Debugging: export `COMFYVN_LOG_LEVEL=DEBUG` to trace hardened bridge submissions (`comfyvn.server.routes.characters`), watch `data/characters/<id>/` for updated JSON, and use `AssetRegistry.wait_for_thumbnails()` in scripting contexts that need to block on thumbnail generation.

### 2.6 Battle Layer Choice & Sim (v0)
- Endpoints: `/api/battle/resolve` deterministically stamps `vars.battle_outcome`, always returns `editor_prompt: "Pick winner"`, and optionally generates a narration log when `stats` + `seed` are supplied. `/api/battle/sim` (guarded by feature flag `enable_battle_sim`, default **OFF**; legacy `/simulate` alias still routes here) runs the v0 formula `base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)` and returns `{outcome, seed, rng, weights, breakdown[], formula, provenance}` with narration only when `"narrate": true`.
- Stats schema accepts either a scalar (treated as `base`) or an object with `base`, `str`, `agi`, `weapon_tier`, `status_mod`, and optional `rng` variance multiplier per contender. Breakdowns expose component totals so overlays and QA harnesses can display and assert roll sheets.
- Hooks: `on_battle_resolved` now ships `{editor_prompt, formula, seed, rng, weights, breakdown, log?, narration?, predicted_outcome, provenance, narrate, rounds}`; `on_battle_simulated` mirrors the simulation payload plus the `narrate` flag and optional narration beats. Subscribe via `/api/modder/hooks/subscribe?topics=on_battle_resolved,on_battle_simulated` or register listeners through `comfyvn.core.modder_hooks` to keep overlays and telemetry in sync.
- Debug hooks: set `COMFYVN_LOG_LEVEL=DEBUG` (or scope `comfyvn.battle.engine`) to log breakdowns and RNG draws. `COMFYVN_BATTLE_SEED=<int>` overrides Studio’s default seed when one isn’t supplied, enabling deterministic regression tests.
- Integration tips: Scenario Runner emits `battle.simulated`/`battle.resolved` for UI extensions; pair simulation logs with `/api/schedule/enqueue` or props styling via `docs/VISUAL_STYLE_MAPPER.md` before resolving.
- Docs: `docs/BATTLE_DESIGN.md` and `docs/development/battle_layer_hooks.md` capture payload schemas, CLI snippets, and troubleshooting notes. Prompt beats remain under `docs/PROMPT_PACKS/BATTLE_NARRATION.md`.

### 2.7 Weather planner & transitions
- Feature flag: `/api/weather/state` sits behind `enable_weather_overlays` (default **OFF**). Partial updates merge into the canonical state before compilation. Studio mirrors the toggle in **Settings → Debug & Feature Flags**.
- Planner core: `comfyvn/weather/engine.py` normalises `{time_of_day, weather, ambience}` (aliases included) and returns deterministic payloads featuring `scene.background_layers`, `scene.light_rig`, `scene.lut`, `scene.bake_ready`, `transition`, optional `particles`, and ambience `sfx` (with `fade_in`/`fade_out`). Each plan carries `meta.hash`, `meta.version`, `meta.updated_at`, and `meta.flags`.
- Shared store: `comfyvn/weather/__init__.py` exposes `WEATHER_PLANNER` — call `.snapshot()` for the latest plan or `.update(state_dict)` to compile new values inside automation scripts (locks ensure thread safety).
- Modder hook: every snapshot or POST update emits `on_weather_changed` with `{state, summary, transition, particles, sfx, lut, bake_ready, flags, meta, trigger}`. Subscribe through `/api/modder/hooks/subscribe` (`topics: ["on_weather_changed"]`) or register an in-process listener via `comfyvn.core.modder_hooks.register_listener` to enqueue renders, bake overlays, or sync LUTs.
- Logging: enable `COMFYVN_LOG_LEVEL=DEBUG` or watch `logs/server.log` for `comfyvn.server.routes.weather` entries containing the state hash, exposure shift, particle type, and LUT path.
- curl quickstart:
  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/weather/state \
    -H 'Content-Type: application/json' \
    -d '{"state": {"time_of_day": "sunrise", "weather": "stormy", "ambience": "dramatic"}}' | jq '.meta'
  ```
- Reference doc: `docs/WEATHER_PROFILES.md` lists preset tables, alias mapping, hook payloads, feature-flag setup, and exporter checklist.

### 2.8 Prop Manager & Anchors
- Feature flag `enable_props` (default **OFF**) gates `/api/props/{anchors,ensure,apply}`. Anchors return normalised coordinates; ensure writes deterministic sidecars/thumbnails (deduped via digest); apply evaluates conditions + tweens against flattened scenario state.
- Hook `on_prop_applied` mirrors apply responses (`prop_id`, `anchor`, `z_order`, `visible`, `tween`, `evaluations`, `thumbnail`, `context`, `applied_at`) so automation scripts, OBS overlays, or exporter daemons can react without polling.
- Conditions support `and`/`or`/`not` + chained comparisons. Missing identifiers resolve to `0`, keeping expressions safe. Tween payloads default to `{duration: 0.45, ease: "easeInOutCubic", hold: 0, stop_at_end: true}` unless overridden.
- Docs: `docs/PROPS_SPEC.md` covers anchors, API payloads, and condition grammar; styling guidance ties into `docs/VISUAL_STYLE_MAPPER.md`. Tests live in `tests/test_props_routes.py`.

### 2.9 Theme Swap Wizard
- Feature flag `enable_themes` (default **OFF**) unlocks `/api/themes/{templates,preview,apply}`. Preview composes checksum-stable plan deltas (assets, palette, camera, props, style tags, per-character overrides, anchor preservation); apply forks or updates a VN Branch lane and appends `theme_swap` provenance without touching OFFICIAL⭐.
- Hooks `on_theme_preview` and `on_theme_apply` broadcast `{theme, theme_label, subtype, variant, anchors_preserved, plan, branch?, branch_created?, checksum, scene, timestamp}` over REST/WebSocket. Use them to feed dashboards (palette previews, diff overlays), OBS layers, advisory pipelines, or CI bots—checksums let you dedupe repeated previews instantly.
- Reference material: `docs/THEME_SWAP_WIZARD.md` (payload diagrams, curl cookbook, provenance rules), `docs/THEME_KITS.md` (flavor/palette matrices), `docs/STYLE_TAGS_REGISTRY.md` (shared vocabulary for filters).

---

## 3. Public Translation, OCR, & Speech Diagnostics

- Feature flags (planned for Phase 7) live under `config/comfyvn.json → features` and default to false so production builds never call public APIs unless explicitly enabled:  
  - `enable_public_translation_apis`  
  - `enable_public_ocr_apis`  
  - `enable_public_speech_apis`  
  Toggle them via **Settings → Debug & Feature Flags** or script updates to `config/comfyvn.json`; call `feature_flags.refresh_cache()` in long-running processes to reload.

## 4. Security Audit Stream & Sandbox Guard

### 4.1 Secrets vault events
- `security.secret_read` (`on_security_secret_read`) fires whenever the encrypted vault serves a provider payload. Payload shape:  
  ```jsonc
  {
    "provider": "runpod",
    "keys": ["api_key", "token"],
    "override_keys": ["api_key"],
    "present": true,
    "timestamp": "2025-11-25T18:02:11Z"
  }
  ```
  Values never leave the store — only key names and override indicators surface so dashboards can monitor usage safely. Audit lines are mirrored to `${COMFYVN_SECURITY_LOG_FILE:-logs/security.log}`.
- `security.key_rotated` (`on_security_key_rotated`) emits after re-encrypting with a new Fernet key. Expect `{fingerprint, providers, timestamp}` so automation can stash rotation history without persisting the raw key.

### 4.2 Sandbox network guard
- `security.sandbox_blocked` (`on_sandbox_network_blocked`) is published whenever the sandbox denies an outbound connection. Payload: `{"host": "api.example.com", "port": 443, "timestamp": "..."}`. Pair with audit logs to identify unauthorised calls during plugin tests.
- FastAPI `/api/security/sandbox/check` supports dry-run validation of allowlists; feed the response into dashboards alongside hook history to prove denied vs allowed routes.

### 4.3 Feature flags & quick tests
- Enable `enable_security_api` to unlock `/api/security/{secrets/providers,secrets/rotate,audit,sandbox/check}`. Example tail:  
  ```bash
  curl -s http://127.0.0.1:8000/api/security/secrets/providers | jq
  curl -s http://127.0.0.1:8000/api/security/audit?limit=5 | jq '.["items"][]'
  ```
- Guard strictness lives behind `enable_security_sandbox_guard`; when disabled the sandbox reverts to legacy behaviour (`network: true` → allow all). Default configs keep the guard enabled so plugin tests remain hermetic by default.
- Diagnostics routes (shipping with the adapters) provide safe capability checks and quota summaries:  
  - `GET /api/providers/translate/test`  
  - `GET /api/providers/ocr/test`  
  - `GET /api/providers/speech/test`  
  When feature flags are off or credentials are missing, each route returns HTTP 200 with `{"configured": false}` entries so Studio can guide setup without hard failures.
- Sample `translate/test` payload with DeepL configured:
  ```jsonc
  {
    "ok": true,
    "providers": [
      {
        "id": "deepl",
        "configured": true,
        "plan": {"tier": "pro", "used": 15234, "limit": 1000000},
        "limits": {"free_tier": "500k chars/mo", "overage_per_million": 25},
        "errors": [],
        "diagnostics": {"credentials": ["COMFYVN_TRANSLATE_DEEPL_KEY"], "checked_at": "2025-11-07T15:54:08Z"}
      }
    ]
  }
  ```
  OCR and speech responses mirror the shape but expose provider-specific metadata (`models`, `language_support`, `streaming_available`).
- Adapter layout (under construction):  
  - Translation: `comfyvn/public_providers/translate_{google,deepl,amazon}.py`  
  - OCR/CV: `comfyvn/public_providers/ocr_{google_vision,aws_rekognition}.py`  
  - Speech: `comfyvn/public_providers/speech_{deepgram,assemblyai}.py`
  Each exposes `from_env()` helpers that sniff environment variables (`COMFYVN_TRANSLATE_GOOGLE_API_KEY`, standard AWS credentials, etc.) or `config/public_providers.json` entries and returns `(adapter, diagnostics)`.
- Dry-run behaviour: pass `"dry_run": true` on POST payloads (translation/speech) or append `?dry_run=1` to OCR requests to validate payload shaping without invoking paid APIs. Diagnostics routes always operate in dry-run mode unless `force=true` is provided.
- TM integration: successful translation calls record entries in `TranslationMemoryStore` with `source="provider:<id>"` and seed `confidence` from provider metadata. Automation scripts can watch for `tm.entry.recorded` bus events (emitted alongside store writes) to trigger custom review workflows or analytics.
- Logging (planned): providers log to `logs/providers/<category>.log` (`translate.log`, `ocr.log`, `speech.log`) with JSON lines `{provider, event, latency_ms, quota, dry_run}`. Until adapters ship these files remain absent; once available, tail them while iterating on credentials or payload tuning.
- Modder hooks: the diagnostics router emits event bus topics (`providers.translate.test`, `providers.ocr.test`, `providers.speech.test`) after each request. Subscribe via `comfyvn.core.events.subscribe()` to surface provider status in custom dashboards or CI scripts.

---

## 4. Translation & Locale Overrides

- `POST /api/i18n/lang` with `{"active": "ja-JP", "fallback": "en-US"}` hot-swaps the
  active language in Studio and persists to `config/comfyvn.json`.
- Drop override files in `config/i18n/<lang>.json` (for deployment-wide defaults) or
  `data/i18n/<lang>.json` (per-project customisations). The manager will merge them on
  the next language toggle.
- Debugging: run `COMFYVN_LOG_LEVEL=DEBUG` and watch `translation.manager` log entries
  for cache invalidations and missing keys.

---

## 5. Testing & Troubleshooting

- Use `python -m comfyvn.tools.doctor` (doctor script) before distributing mods; it
  checks registry integrity, advisory acknowledgement state, and required directories.
- When iterating on bridge payloads, tail `logs/server.log` for `st_bridge` records.
  Manifest mismatches or missing watch paths surface in the `extension.watch_paths`
  array returned by `/st/health`.
- Regenerate personas or characters by re-posting payloads with `overwrite` flags. The
  importers preserve `metadata.source="SillyTavern"` and `metadata.imported_at` so you
  can diff outputs across runs.

---

## 6. LLM Registry & Chat Proxy

- Enumerate providers via `GET /api/llm/registry`; the payload surfaces tags, base URLs, and adapter names taken from `comfyvn/models/registry.json`. Use this instead of hard-coding Ollama or LM Studio assumptions in tooling.
- Exercise adapters via `POST /api/llm/test-call` with `{"registry_id": "<provider>", "model": "<id>", "messages": [...]}`. Optional params (`temperature`, `top_p`, `max_tokens`) are forwarded to the adapter and merged with registry defaults; responses include `{reply, raw, usage}` so scripts can log provenance without hitting paid endpoints. The full `/api/llm/chat` proxy remains a TODO (see public LLM router work order).
- Supported adapters (`openai_compat`, `lmstudio`, `ollama`, `anthropic_compat`) inherit common error handling and expose `reply`, `usage`, and raw vendor payloads. Failures raise 502 with the adapter's message so CLI wrappers can emit helpful diagnostics.
- Overrides: export `COMFYVN_LLM_<PROVIDER>_{BASE_URL,API_KEY,HEADERS}` to target remote gateways or inject auth headers without touching the registry. `COMFYVN_LLM_DEFAULT_TIMEOUT` sets a global fallback (seconds).
- Quick test:

  ```bash
  curl -s -X POST http://127.0.0.1:8000/api/llm/test-call \
    -H 'Content-Type: application/json' \
    -d '{
      "registry_id": "ollama_default",
      "model": "llama3:latest",
      "messages": [{"role": "user", "content": "Summarise ComfyVN in one line."}],
      "params": {"temperature": 0.4}
    }' | jq '.reply'
  ```

  Adjust `registry_id`/`model` based on `/api/llm/registry` output.

---

## 7. Modder Hook Bus & Debug Integrations

### 7.1 Hook events
- `on_scene_enter` — emitted whenever the Scenario Runner enters a node (initial state + every `step`). Payload:
  ```jsonc
  {
    "scene_id": "demo_scene",
    "node": "intro_002",
    "pov": "narrator",
    "variables": {"mood": "tense"},
    "history": [
      {"node": "intro_001", "choice": "start"},
      {"node": "intro_002", "choice": null}
    ],
    "finished": false,
    "timestamp": 1734806400.123
  }
  ```
- `on_choice_render` — fired alongside `on_scene_enter`, containing the filtered choices preview:
  ```jsonc
  {
    "scene_id": "demo_scene",
    "node": "intro_002",
    "choices": [
      {"id": "ask", "label": "Ask a question", "target": "intro_003"},
      {"id": "leave", "label": "Leave the room", "target": "intro_004"}
    ],
    "pov": "narrator",
    "finished": false,
    "timestamp": 1734806400.123
  }
  ```
- `on_narrator_proposal` — emitted whenever `/api/narrator/propose` enqueues a draft. Payload mirrors the queued proposal (choice id, vars patch, rationale, turn index) plus a deterministic digest so instrumentation can match proposals with offline planner outputs without storing raw dialogue.
  ```jsonc
  {
    "scene_id": "demo_scene",
    "node_id": "demo_scene.node_3",
    "proposal_id": "p0002",
    "choice_id": "choice_continue",
    "vars_patch": {
      "$narrator": {
        "scene_id": "demo_scene",
        "node_id": "demo_scene.node_3",
        "turn": 2,
        "choice_id": "choice_continue",
        "digest": "7ea891aa"
      }
    },
    "rationale": "Offline planner suggested choice 'choice_continue' using adapter offline.local.",
    "turn_index": 2,
    "mode": "propose",
    "timestamp": 1735660800.12
  }
  ```
- `on_narrator_apply` — fired when `/api/narrator/apply` commits a proposal or when rollback replays an apply (`rolled_back: true`). Use it to drive dashboards, audit variable changes, or rebuild deterministic transcripts.
  ```jsonc
  {
    "scene_id": "demo_scene",
    "node_id": "demo_scene.node_3",
    "proposal_id": "p0002",
    "choice_id": "choice_continue",
    "vars_patch": {
      "$narrator": {
        "scene_id": "demo_scene",
        "node_id": "demo_scene.node_3",
        "turn": 2,
        "choice_id": "choice_continue",
        "digest": "7ea891aa"
      }
    },
    "turn_index": 2,
    "timestamp": 1735660810.42,
    "rolled_back": false
  }
  ```
- `on_collab_operation` — emitted whenever the collaboration hub applies a batch of CRDT ops to a scene. Fired by WebSocket clients (`doc.apply`) and REST consumers replaying `/api/collab/history`. Use it to mirror live edits, stream activity dashboards, or rebuild state without fetching full snapshots.
  ```jsonc
  {
    "scene_id": "intro",
    "version": 17,
    "clock": 84,
    "actor": "client:4b21f4",
    "operations": [
      {
        "op_id": "client:4b21f4:12",
        "actor": "client:4b21f4",
        "clock": 83,
        "kind": "graph.node.upsert",
        "payload": {"node": {"id": "intro_a", "text": "Hello world"}},
        "timestamp": 1732380042.12
      }
    ],
    "applied": [true],
    "timestamp": 1732380042.18,
    "snapshot": {"scene_id": "intro", "nodes": [...], "lines": [...]}
  }
  ```
  - `snapshot` is omitted when the batch produced no changes (duplicate ops, stale clocks). Re-request `/api/collab/history/<scene_id>?since=<version>` to backfill missed operations.
  - Feature flag: `features.enable_collaboration` must remain enabled; consult `docs/development_notes.md` for curl probes and the collab debug checklist.
  - `applied` mirrors `operations` one-for-one so automation can detect rejected ops and schedule a resync.
- `on_accessibility_settings` — fired when accessibility preferences (font scale, color filter, high contrast, subtitles) change.
  ```jsonc
  {
    "state": {
      "font_scale": 1.1,
      "color_filter": "deuteranopia",
      "high_contrast": true,
      "subtitles_enabled": true,
      "ui_scale": 1.25,
      "view_overrides": {
        "viewer": 1.5
      }
    },
    "source": "api.accessibility.state.post",
    "timestamp": 1732924800.42
  }
  ```
- `on_accessibility_subtitle` — emitted when the viewer subtitle overlay updates or clears.
  ```jsonc
  {
    "text": "Advance",
    "origin": "Input",
    "expires_at": 1732924803.0,
    "enabled": true,
    "reason": "accessibility.subtitle.push",
    "timestamp": 1732924800.43
  }
  ```
- `on_accessibility_input_map` — broadcast after an input binding (keyboard/controller) is updated.
  ```jsonc
  {
    "action": "viewer.advance",
    "binding": {
      "action": "viewer.advance",
      "label": "Advance / Continue",
      "primary": "Ctrl+Right",
      "secondary": null,
      "gamepad": "button_a",
      "category": "viewer"
    },
    "timestamp": 1732924801.12,
    "reason": "update"
  }
  ```
- `on_accessibility_input` — fires whenever a mapped input action triggers (keyboard shortcut, controller button, or API trigger).
  ```jsonc
  {
    "action": "viewer.menu",
    "source": "controller",
    "meta": {"device": 0},
    "timestamp": 1732924802.55
  }
  ```
- `on_playtest_start` — emitted by the headless playtest harness when a trace begins. Payload mirrors the API request context so automation can seed dashboards:
  ```jsonc
  {
    "scene_id": "demo_scene",
    "seed": 682,
    "pov": "narrator",
    "prompt_packs": ["POV_REWRITE"],
    "workflow": "ci-smoke",
    "persist": true,
    "variables_digest": "4a221814...",
    "timestamp": 1734806450.004
  }
  ```
- `on_playtest_step` — dispatched after every deterministic step recorded by the harness:
  ```jsonc
  {
    "scene_id": "demo_scene",
    "step_index": 1,
    "from_node": "intro",
    "to_node": "path_a",
    "choice_id": "choose_a",
    "choice_target": "path_a",
    "choice_text": "Take path A",
    "rng_before": {"seed": 682, "value": 12345, "uses": 0},
    "rng_after": {"seed": 682, "value": 409818404, "uses": 1},
    "variables_digest": "51c97c3f...",
    "finished": true,
    "timestamp": 1734806450.205
  }
  ```
- `on_playtest_finished` — published when the harness finalises the trace digest:
  ```jsonc
  {
    "scene_id": "demo_scene",
    "seed": 682,
    "pov": "narrator",
    "digest": "1f6be12f...",
    "steps": 1,
    "aborted": false,
    "persisted": true,
    "timestamp": 1734806450.209
  }
  ```
- `on_asset_registered` (alias `on_asset_saved`) — dispatched after `AssetRegistry.register_file` writes the sidecar (covers character renders, audio mixes, etc.). Payload:
  ```jsonc
  {
    "uid": "9f1b5f6ad31b4f6e",
    "type": "character.portrait",
    "path": "characters/alice/portrait/alice.png",
    "meta": {"tags": ["hero"]},
    "sidecar": "characters/alice/portrait/alice.png.asset.json",
    "bytes": 524288,
    "hook_event": "asset_registered",
    "timestamp": 1734806421.042
  }
  ```
- `on_asset_meta_updated` — triggered whenever asset metadata or sidecar contents change (bulk tag edits, CLI enforcement, rebuilds). Payload mirrors `on_asset_registered` but focuses on the refreshed metadata:
  ```jsonc
  {
    "uid": "9f1b5f6ad31b4f6e",
    "type": "character.portrait",
    "path": "characters/alice/portrait/alice.png",
    "meta": {"tags": ["hero", "debug"]},
    "sidecar": "characters/alice/portrait/alice.png.asset.json",
    "hook_event": "asset_meta_updated",
    "timestamp": 1734806432.512
  }
  ```
- `on_asset_removed` — fires after a registry row (and optional files) are deleted so automation can drop cache entries:
  ```jsonc
  {
    "uid": "9f1b5f6ad31b4f6e",
    "type": "character.portrait",
    "path": "characters/alice/portrait/alice.png",
    "sidecar": "characters/alice/portrait/alice.png.asset.json",
    "meta": {"tags": ["hero", "debug"], "license": "CC-BY-4.0"},
    "bytes": 524288,
    "hook_event": "asset_removed",
    "timestamp": 1734806445.003
  }
  ```
- `on_asset_sidecar_written` — emitted every time a sidecar JSON file is written. Useful when scripts need to diff raw sidecar payloads independent of metadata updates:
  ```jsonc
  {
    "uid": "9f1b5f6ad31b4f6e",
    "type": "character.portrait",
    "rel_path": "characters/alice/portrait/alice.png",
    "sidecar": "/abs/path/to/data/assets/characters/alice/portrait/alice.png.asset.json",
    "hook_event": "asset_sidecar_written",
    "timestamp": 1734806432.497
  }
  ```
- `on_policy_enforced` — emitted after the policy enforcer evaluates an import/export action. Automation scripts can watch this event to halt CI pipelines or annotate build dashboards with the enforcement decision:
  ```jsonc
  {
    "event": "on_policy_enforced",
    "ts": 1734806501.512,
    "data": {
      "action": "export.bundle",
      "allow": false,
      "counts": {"info": 0, "warn": 1, "block": 1},
      "blocked": [
        {
          "message": "License 'All Rights Reserved' forbids redistribution.",
          "detail": {"plugin": "spdx_license", "label": "All Rights Reserved"},
          "level": "block"
        }
      ],
      "warnings": [],
      "log_path": "logs/policy/enforcer.jsonl"
    }
  }
  ```

- `on_rating_decision` — emitted for every classifier evaluation when `enable_rating_modder_stream` is enabled. Payload mirrors `/api/rating/classify` (`item_id`, `rating`, `nsfw`, `confidence`, `mode`, `matched`, `ack_status`, `allowed`) so dashboards can surface high-risk content in real time.
- `on_rating_override` — raised after reviewers store or remove overrides; persisted payload includes `{item_id, rating, reviewer, reason, scope, timestamp, removed}` to stay in sync with the override JSON store.
- `on_rating_acknowledged` — published once an acknowledgement token is confirmed via `/api/rating/ack`, carrying `{token, item_id, action, rating, user, acknowledged_at}` for legal/audit dashboards.

### 7.0 Viewer & Ren'Py export hooks

- `on_thumbnail_captured` (viewer Mini-VN thumbnailer)
  - Emitted whenever the deterministic Mini-VN thumbnailer writes or refreshes a cached thumbnail.
  - Payload: `{scene_id, timeline_id, pov, seed, path, filename, digest, width, height, timestamp}`.
  - Token: `viewer.thumbnail_captured` on the WebSocket bus.
- `on_export_started` (Ren'Py export CLI + `/api/export/renpy/*`)
  - Fires before the orchestrator runs. Payload includes `{project, timeline, world, options:{pov_mode,dry_run,bake_weather}, timestamp}`.
- `on_export_completed`
  - Fires after export (success or failure). Payload: `{project, timeline, ok, output_dir, weather_bake, label_manifest, error?, timestamp}`. Dry runs inline the manifest instead of returning a path.

### 7.1 Export publish hooks

- Feature flags: set `enable_export_publish` plus `enable_export_publish_{steam,itch}` to `true` in `config/comfyvn.json` (or patch via `/api/settings`) before calling `POST /api/export/publish`. They default to `false` so local builds remain private by default.
- Dry-run preview (`"dry_run": true`) emits `on_export_publish_preview` with the requested targets, planned platforms, and diff summaries:
  ```jsonc
  {
    "project_id": "demo",
    "timeline_id": "main",
    "targets": ["steam", "itch"],
    "label": "Demo Build",
    "version": "0.1.0",
    "platforms": {
      "steam": ["windows", "linux"],
      "itch": ["windows", "linux"]
    },
    "diffs": {
      "steam": [
        {"path": "exports/publish/steam/demo-build.steam.zip", "status": "new"},
        {"path": "exports/publish/steam/demo-build.steam.manifest.json", "status": "new"}
      ],
      "itch": [
        {"path": "exports/publish/itch/demo-build.itch.zip", "status": "new"}
      ]
    }
  }
  ```
- Successful runs emit `on_export_publish_complete` once per target with checksum, archive, manifest paths, and provenance sidecars so automation can mirror release announcements or kick off upload scripts:
  ```jsonc
  {
    "project_id": "demo",
    "timeline_id": "main",
    "target": "steam",
    "label": "Demo Build",
    "version": "0.1.0",
    "checksum": "2fef…",
    "archive_path": "/abs/.../exports/publish/steam/demo-build.steam.zip",
    "manifest_path": "/abs/.../exports/publish/steam/demo-build.steam.manifest.json",
    "platforms": ["windows", "linux"],
    "provenance": {
      "archive": "/abs/.../exports/publish/steam/demo-build.steam.zip.prov.json",
      "manifest": "/abs/.../exports/publish/steam/demo-build.steam.manifest.json.prov.json"
    }
  }
  ```
- Structured log: the route also appends JSON lines to `logs/export/publish.log` (`steam_publish_{dry_run,created}`, `itch_publish_{dry_run,created}`) so CI bots can tail build activity without parsing FastAPI output.

### 7.2 REST + WebSocket surfaces
- `GET /api/modder/hooks` → returns `{"hooks": [...], "history": [...], "webhooks": [...], "plugin_host": {enabled, root}}` for quick discovery. Each hook entry includes the WebSocket topic and documented payload fields.
- `GET /api/modder/hooks/history?limit=25` → last N envelopes. Use when scripting CLI diagnostics.
- `POST /api/modder/hooks/webhooks` → `{"event": "on_scene_enter", "url": "https://example/hooks", "secret": "optional"}` registers a signed webhook (HMAC SHA-256 in `X-Comfy-Signature`). `DELETE /api/modder/hooks/webhooks` removes registrations.
- `POST /api/modder/hooks/test` → emits a synthetic payload for smoke tests. Override the default event with `{"event": "on_asset_meta_updated", "payload": {...}}`.
- WebSocket: connect to `ws://127.0.0.1:8001/api/modder/hooks/ws` with optional `{"topics": ["on_asset_meta_updated"]}` handshake. Messages stream as `{event, ts, data}`; keep-alive `{"ping": true}` frames arrive every 20 s when idle.
- Structured log mirrors: hook emissions are also logged at DEBUG under `logs/server.log` with logger `comfyvn.studio.core.asset_registry`, making it easy to reconstruct timelines when triaging reports.
- Cloud sync events: `on_cloud_sync_plan` (dry-run summary with `service`, `snapshot`, `uploads`, `deletes`, `bytes`) and `on_cloud_sync_complete` (run summary with `uploads`, `deletes`, `skipped`). Subscribe via `topics: ["on_cloud_sync_plan"]` or `["on_cloud_sync_complete"]` to surface offsite backup telemetry in Studio dashboards or CI bots.
- Asset-focused debug: `GET /assets/debug/hooks` mirrors registry hook registrations; `GET /assets/debug/modder-hooks` filters the Modder Hook Bus to asset payloads; `GET /assets/debug/history?limit=15` returns the latest `{event, ts, data}` envelopes emitted for assets. Pair these with `GET /assets/{uid}` or direct sidecar reads to inspect provenance on disk without cracking open the SQLite registry.

### 7.3 Dev plugins + bridge
- The hook bus auto-loads developer plugins from `dev/modder_hooks/` when `COMFYVN_DEV_MODE=1` (override root via `COMFYVN_MOD_PLUGIN_ROOT`). Plugins implement `def on_scene_enter(payload): ...` style functions and can register logging, custom routing, or automation without touching server code.
- The webhooks bridge reuses `comfyvn/server/core/webhooks.py`; existing webhook consumers automatically receive the new events with timestamped envelopes.

### 7.4 Debug Integrations panel
- Studio → System → **Debug Integrations** opens `comfyvn/gui/panels/debug_integrations.py`. The panel polls `/api/providers/health` and `/api/providers/quota?id=…` every 15 s (toggleable) and renders status/usage columns with masked credentials from the compute registry.
- Use the panel when onboarding new API keys or diagnosing remote providers: red rows highlight failing health checks, and the usage column surfaces credit/quota responses returned by the adapters (RunPod, Unraid, generic HTTP).
- REST parity: the panel mirrors data available via `ComputeProviderRegistry.list()` (masked configs) and `/api/providers/health`; automation scripts should rely on the same endpoints plus the modder hook bus for asset updates.

## 8. Related Docs

- `README.md` — high-level feature overview with modder callouts.
- `architecture.md` — release phase coordination and subsystem owners.
- `docs/development_notes.md` — broader automation and registry guidance.
- `docs/dev_notes_asset_registry_hooks.md` — quickstart for REST/WS asset hook envelopes and sample cURL snippets.
- `docs/PROMPT_PACKS/POV_REWRITE.md` & `docs/PROMPT_PACKS/BATTLE_NARRATION.md` — strict JSON schemas and router hints for narrative prompt packs that pair with `on_scene_enter`/`on_asset_*` events.
- `docs/import_roleplay.md` — roleplay importer staging, provenance, and advisory hooks.
- `SillyTavern Extension/readme.txt` — upstream plugin instructions for bridge users.

Ping the Project Integration chat for additional hook requests or if new endpoints need
sample payloads here.
