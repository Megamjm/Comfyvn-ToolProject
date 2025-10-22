Weather Planner & Transition Guide
==================================

Updated: 2025-11-09 • Owner: World State & Transitions Chat  
Scope: Weather/lighting pipeline feeding Studio previews, automation scripts, and export baking.

---

1. Overview
-----------

- Planner lives at `comfyvn/weather/engine.py`. `compile_plan(state)` normalises `{time_of_day, weather, ambience}` (aliases respected), then returns:
  - `scene.background_layers` — base + overlay (and optional depth mask) textures with intensity/blend data.
  - `scene.light_rig` — derived key/fill/rim ratios, temperature, exposure, contrast, saturation overrides.
  - `transition` — crossfade duration, easing, exposure shift, SFX/particle fade durations.
  - `particles` — optional emitter payloads (`type`, `spawn_rate`, `intensity`, etc.).
  - `sfx` — ambience loop path, gain, tags, optional one-shot list.
  - `meta` — canonical hash, warning list (unknown values), version, and UTC timestamp when stored in the shared planner.
- `WeatherPlanStore` (exported via `comfyvn/weather/__init__.py` as `WEATHER_PLANNER`) keeps the latest compiled plan in memory with thread-safe `.update()` and `.snapshot()` helpers for Studio, exporters, and automation scripts.
- Feature flag: `enable_weather_planner` under `config/comfyvn.json → features` (default `true`). Disable to hide the REST surface while retaining legacy background workflows. Studio exposes the toggle under **Settings → Debug & Feature Flags** and honours changes without restart.

---

2. Preset tables (summary)
--------------------------

| Dimension     | Aliases (→ canonical)                             | Notes                                                                 |
|---------------|---------------------------------------------------|-----------------------------------------------------------------------|
| `time_of_day` | `sunrise/sunset/evening/twilight → dawn/dusk`     | Controls base background texture, key/fill/rim ratios, colour temp.   |
| `weather`     | `rainy → rain`, `stormy/heavy_rain → storm`, `mist/haze → fog` | Sets overlay texture, contrast/exposure deltas, particle payloads, one-shot SFX. |
| `ambience`    | `dramatic/anxious → tense`, `serene → calm`, `arcane → mystic` | Adjusts transition duration, overlay gain, exposure bias, particle gain.        |

- Full JSON preset tables live in `comfyvn/weather/engine.py` (`_TIME_PRESETS`, `_WEATHER_PRESETS`, `_AMBIENCE_PRESETS`). Add new presets by extending those dictionaries; alias mapping sits in `_TIME_ALIASES`, `_WEATHER_ALIASES`, `_AMBIENCE_ALIASES`.
- Warnings surface under `plan["meta"]["warnings"]` whenever unknown values are supplied; callers receive the fallback canonical state plus a message (e.g., `"weather: unrecognized value 'volcanic' (fell back to 'clear')"`).

---

3. API contract
---------------

- Endpoint: `/api/weather/state`
  - `GET` → returns the current compiled plan (`WeatherPlanStore.snapshot()`).
  - `POST` → accepts partial state updates. Payload may include top-level keys or nested `{"state": {...}}`. The planner merges the payload with the previous canonical state and compiles a fresh plan.
  - Example request:
    ```bash
    curl -s -X POST http://127.0.0.1:8000/api/weather/state \
      -H 'Content-Type: application/json' \
      -d '{"state": {"time_of_day": "night", "weather": "fog", "ambience": "mystic"}}' | jq '.scene.summary'
    ```
  - Feature flag disabled → `404 {"detail": "Weather planner disabled"}`.
- Structured logging: `comfyvn.server.routes.weather` logs `"Weather plan updated"` with extras:
  ```jsonc
  {
    "weather_state": {"time_of_day": "dusk", "weather": "rain", "ambience": "tense"},
    "weather_meta": {"hash": "c1c5e2d9a0ef", "version": 2, "updated_at": "2025-11-09T21:14:55.120394+00:00"},
    "weather_transition": {"duration": 0.9, "exposure_shift": -0.4},
    "weather_particles": "rain"
  }
  ```
  Tail `logs/server.log` (or scope to `comfyvn.server.routes.weather`) when debugging automation.

---

4. Modder hook & automation
---------------------------

- Every snapshot/update emits `on_weather_plan` through `comfyvn.core.modder_hooks`. Payload:
  ```jsonc
  {
    "state": {"time_of_day": "dawn", "weather": "rain", "ambience": "tense"},
    "summary": {"background": "backgrounds/dawn_default.png", "overlay": "weather/rain_dawn.png"},
    "transition": {"type": "crossfade", "duration": 0.9, "exposure_shift": -0.35, "ease": "easeInOutQuad"},
    "particles": {"type": "rain", "spawn_rate": 240, "intensity": 0.72, "emitter": "rain_dawn"},
    "sfx": {"loop": "ambience/rain_loop.ogg", "gain_db": -3.5, "tags": ["rain", "tense", "dawn"]},
    "meta": {"hash": "70f91b4a2c80", "version": 4, "updated_at": "2025-11-09T21:16:03.482Z", "warnings": []},
    "trigger": "api.weather.state.post",
    "timestamp": "2025-11-09T21:16:03.482Z"
  }
  ```
- Subscribe via REST:
  ```bash
  curl -N -H 'Accept: text/event-stream' \
    'http://127.0.0.1:8000/api/modder/hooks/subscribe?topics=on_weather_plan'
  ```
  (Falls back to GET polling if SSE unsupported.) For in-process extensions call `modder_hooks.register_listener(listener, events=("on_weather_plan",))`.
- Suggested automations:
  - Start/stop rain/snow particle emitters in custom render pipelines using the event payload.
  - Bake background composites by fetching `scene.background_layers` and queuing renderer jobs whenever the hash changes.
  - Sync ambience mixes: pair `sfx.loop` with `/api/audio/mix` or remote SFX registries; warnings indicate fallback states worth flagging in dashboards.

---

5. Export & testing checklist
-----------------------------

- Export pipelines (`RenPyOrchestrator`, bundle exporters) should call `WEATHER_PLANNER.snapshot()` during staging to capture the latest hash alongside render manifests. Store the hash in provenance sidecars so rebuilds can skip unchanged weather states.
- Tests:
  - `pytest tests/test_weather_engine.py` — covers alias mapping, warnings, particle payloads, version increments, and `WeatherPlanStore.clear()`.
  - `pytest tests/test_weather_routes.py` — ensures feature flag gating, REST behaviour, and `on_weather_plan` emission.
- When extending preset tables, update:
  - `docs/CODEX_STUBS/2025-10-21_WEATHER_LIGHTING_TRANSITIONS_A_B.md`
  - `README.md` highlight section
  - `docs/dev_notes_modder_hooks.md` → Section 2.7 (API + hook notes)
  - This guide (`docs/WEATHER_PROFILES.md`) with new texture ids, SFX assets, or particle schema changes.

---

6. Troubleshooting
------------------

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `404 {"detail": "Weather planner disabled"}` | Feature flag off | Enable `enable_weather_planner` in `config/comfyvn.json`, then call `feature_flags.refresh_cache()` or restart the server. |
| `warnings` list contains fallback messages | Alias table missing entry or typo in payload | Update `_TIME/_WEATHER/_AMBIENCE_ALIASES` for new synonyms or ensure callers pass canonical values. |
| Particle intensity too high/low | Ambience preset `particle_gain` offset | Adjust `_AMBIENCE_PRESETS` entry or supply new ambience profile. |
| Automation missed update | `on_weather_plan` not subscribed | Verify listener registration or SSE subscription; check `logs/server.log` to confirm event emission. |

For additional hook requests or payload changes ping Project Integration in `CHAT_WORK_ORDERS.md`.
