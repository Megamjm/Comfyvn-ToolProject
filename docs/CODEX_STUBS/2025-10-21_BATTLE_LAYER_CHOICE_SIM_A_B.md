# Battle Layer — Choice Mode & Sim Mode (A/B) — 2025-10-21

## Intent
- Choice mode: authors or automation pick the winner manually, set `vars.battle_outcome`, and jump branches deterministically.
- Sim mode: weighted odds with deterministic seeds produce POV-aware narration logs so teams can preview outcomes before committing.
- Ensure Scenario Runner, CLI tools, and external integrations can exercise both flows without editing scenario graphs directly.

## Scope
- Implement `comfyvn/battle/engine.py` (resolve helper + seeded simulator) and expose it via FastAPI router `comfyvn/server/routes/battle.py`.
- Wire `/api/battle/resolve` and `/api/battle/simulate` into the Scenario Runner so simulated narration appears in choice overlays while the branch remains pending.
- Update documentation (README, ARCHITECTURE, CHANGELOG, dev notes) and surface a development note under `docs/development/` for modders.

## Deliverables
- Deterministic resolve API (`POST /api/battle/resolve`, returns applied outcome + vars payload).
- Weighted simulation API (`POST /api/battle/simulate`, returns `{outcome, seed, log[], weights}` with POV-aware narration).
- Scenario Runner hooks that display simulated logs and persist seeds for replay.
- Documentation sweep + dev note capturing payloads, seeding guidance, debug toggles, and asset/SFX integration tips.

## Acceptance
- `/api/battle/resolve` deterministically applies the outcome, stamps `vars.battle_outcome`, and echoes the result payload.
- `/api/battle/simulate` returns a seeded narration log while the runner keeps the branch unresolved until `resolve()` is called.
- Docs and changelog entries highlight the new engine module, routes, debug hooks, and modder guidance.
