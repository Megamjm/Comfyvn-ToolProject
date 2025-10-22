# Battle Design Stub & Roadmap

## Overview
Phase 7 introduces a lightweight battle planner stub so UI teams and modders can prototype combat flows before the full simulator ships. The stub lives in `comfyvn/battle/__init__.py` and surfaces via `/api/battle/plan` (feature-gated by `enable_battle`).

`plan(payload)` accepts optional keys:
- `id` — unique identifier (defaults to `battle-local`).
- `mode` — `turn`, `sim`, or other custom labels (default `turn`).
- `seed` — integer seed (default `42`) recorded to keep RNG decisions deterministic when the simulator arrives.
- `pov` / `world` — metadata persisted in `plan.meta` for downstream narration or export tooling.

The response contains:
- `timeline` — three deterministic phases (`setup`, `engagement`, `resolution`) with placeholder summaries and timestamps.
- `meta` — includes `dry_run=true`, `pov`, `world`, and notes instructing callers to treat the payload as a stub.

## API surface
- `POST /api/battle/plan` — returns `{ "ok": true, "plan": {...}, "feature": "enable_battle" }`. When the feature flag is disabled, the route returns HTTP 403.

Planned additions (tracked in `docs/WORKBOARD_PHASE7_POV_APIS.md`):
1. `POST /api/battle/resolve` — accept a winner/outcome and persist to state.
2. `POST /api/battle/simulate` — run deterministic RNG with log output.
3. WebSocket push events so Studio panels and modder overlays receive live combat updates.

## Debugging tips
- Enable `COMFYVN_LOG_LEVEL=DEBUG` to trace incoming battle payloads and stub output.
- Combine `plan.meta.pov` with `/api/pov/worlds` to keep combat narration aligned with active worldlines.
- Pair battle plans with weather/theme outputs to maintain ambience and SFX coherence.

## Testing checklist
1. Ensure `features.enable_battle=true` (default) and call `/api/battle/plan` with empty payload → expect deterministic stub timeline.
2. Send payload with custom `id`, `mode`, `seed`, `pov`, `world`; verify response echoes values in `plan.meta`.
3. Toggle `enable_battle=false` in `config/comfyvn.json` and confirm the API returns 403 and Studio hides battle UI modules.

## Roadmap alignment
- Simulator integration: bring in weighted outcome calculations, narration logs, and asset triggers.
- Asset coupling: link battle phases to SFX/VFX/animation jobs once stub replaced.
- QA instrumentation: record battle seeds/outcomes for replay harnesses.

## Related docs
- `docs/POV_DESIGN.md` — ensures battle decisions reference consistent worldlines/POVs.
- `docs/WEATHER_PROFILES.md` — recommended cues for pairing battle scenes with ambience.
- `docs/WORKBOARD_PHASE7_POV_APIS.md` — tracker for simulator follow-up tasks.
