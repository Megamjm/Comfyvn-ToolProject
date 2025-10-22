2025-10-21 — Weather, Lighting & Transitions (Parts A/B)
=======================================================

Intent
------
- Track world state (`time_of_day`, `weather`, `ambience`) so previews and exports share the same lighting recipe.
- Compile layered backgrounds, light rig overrides, particle payloads, and exposure shifts for every scene transition.
- Surface the plan through a lightweight API so background baking/export pipelines can pull without blocking the UI.

Implementation Highlights
-------------------------
- `comfyvn/weather/engine.py` — deterministic planner with presets + alias handling, exposes `WeatherPlanStore` for thread-safe snapshots.
- `comfyvn/weather/__init__.py` — exports the shared `WEATHER_PLANNER` singleton used by routes/tests.
- `comfyvn/server/routes/weather.py` — FastAPI router (`/api/weather/state`) that merges partial updates and returns the compiled plan.
- Tests: `tests/test_weather_engine.py` (planner + store) and `tests/test_weather_routes.py` (API contract).

API Contract
------------
```
GET  /api/weather/state   -> current compiled plan
POST /api/weather/state
{
  "time_of_day": "dusk",   # optional
  "weather": "rain",       # optional
  "ambience": "tense"      # optional
  // or put the same keys under "state": {}
}
```

Response payload (both endpoints):
```
{
  "state": {"time_of_day": "dusk", "weather": "rain", "ambience": "tense"},
  "scene": {
    "background_layers": [
      {"id": "base_dusk", "role": "base", "texture": "backgrounds/dusk_default.png", ...},
      {"id": "rain_dusk", "role": "weather", "texture": "weather/rain_dusk.png", ...},
      {"id": "rain_depth", "role": "depth_mask", ...} // fog/storm depth masks
    ],
    "light_rig": {"key": 0.57, "fill": 0.42, "rim": 0.41, "temperature": 4030, "exposure": -0.28},
    "summary": {"background": "...", "overlay": "..."}
  },
  "transition": {"type": "crossfade", "duration": 0.9, "exposure_shift": -0.4, "sfx_fade": 1.0, ...},
  "particles": {"type": "rain", "spawn_rate": 240, "intensity": 0.72, ...} | null,
  "sfx": {"loop": "ambience/rain_loop.ogg", "gain_db": -3.3, "tags": ["rain","tense","dusk"], ...},
  "meta": {"hash": "d52df7e1b9f4", "version": 2, "updated_at": "...", "warnings": []}
}
```

Planner Notes
-------------
- Presets live in `_TIME_PRESETS`, `_WEATHER_PRESETS`, and `_AMBIENCE_PRESETS`; synonyms (e.g. `sunset`, `stormy`, `dramatic`) map automatically.
- Light rig blends time-of-day defaults with weather contrast/exposure deltas, then ambience bias (clamped to sane ranges).
- Overlays always include a base layer plus weather overlay; fog/storm add depth masks for parallax-aware blending.
- Particle payloads only emit for weather types that define them; ambience can boost/reduce intensity.
- Meta hash is the first 12 chars of SHA1 over canonical state, letting exporters detect no-op updates cheaply.

Export & Background Baking
--------------------------
- `WEATHER_PLANNER.update()` stores the compiled plan with version + timestamp, so exporters just call `WEATHER_PLANNER.snapshot()` before baking.
- Plan `scene.background_layers` can be fed straight into compositing workflows or Ren'Py exporters to queue required background assets.
- `transition.exposure_shift` pairs with crossfades; export pipelines can drive post-processing (e.g. CRF ramps) without recomputing presets.

Testing
-------
- `pytest tests/test_weather_engine.py tests/test_weather_routes.py`
- Engine tests cover alias resolution, warning handling, particle payloads, and version bookkeeping; route tests cover merge semantics + warnings.
