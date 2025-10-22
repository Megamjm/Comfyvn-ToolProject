# Dev Notes — Battle UX & Sim v0

Updated: 2025-12-08 • Owner: Project Integration & Narrative Systems

Battle flows now share a deterministic core so editors, automation, and QA receive identical roll sheets, provenance, and optional narration regardless of mode.

## Feature Flags & Files
- Feature flag: `features.enable_battle_sim` (default `false`) gates `/api/battle/sim` while `/api/battle/resolve` remains always-on.
- Core code: `comfyvn/battle/engine.py` (formula helpers, provenance builder), `comfyvn/server/routes/battle.py` (REST wiring, modder hooks).
- Prompt pack: `docs/PROMPT_PACKS/BATTLE_NARRATION.md` — skipped whenever `narrate=false`.

## Endpoint Summary
- `POST /api/battle/resolve`
  - Required: `winner`.
  - Optional: `stats`, `seed`, `pov`, `rounds` (≥1), `narrate` (default `true`), `state`, `persist_state`.
  - Returns: `{outcome, vars, persisted, editor_prompt, formula, seed?, rng?, weights?, breakdown?, predicted_outcome?, log?, narration?, provenance?, state?}`.
- `POST /api/battle/sim` *(feature gated; `/simulate` alias remains)*
  - Required: `stats` (scalar or object per contender).
  - Optional: `seed`, `rng`, `pov`, `rounds`, `narrate`, `state`, `persist_state`.
  - Returns: `{outcome, seed, rng, weights, breakdown[], formula, provenance, log?, narration?, persisted, state?}`.

### Provenance Block
Every response includes `provenance`:
```
{
  "formula": "base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)",
  "seed": <int>,
  "rng": {"seed": <int>, "value": <int>, "uses": <int>},
  "weights": {...},
  "predicted_outcome": "<engine winner>",
  "resolved_outcome": "<editor winner>" // resolve only
}
```

## Hooks & Automation
- `on_battle_resolved` payload now includes `weights`, `breakdown`, `rng`, `provenance`, `predicted_outcome`, plus optional `log`/`narration`, alongside `narrate` and `rounds`.
- `on_battle_simulated` mirrors the sim response and forwards the `narrate` flag even when narration is disabled (log array empty).
- Subscribe via REST: `curl http://127.0.0.1:8001/api/modder/hooks/subscribe?topics=on_battle_resolved,on_battle_simulated`.

## Debug & QA Checklist
- Set `COMFYVN_BATTLE_SEED=<int>` to stabilise seeds in local runs; responses still echo actual seeds.
- Enable granular logging with `COMFYVN_LOG_LEVEL=DEBUG` or `COMFYVN_LOG_LEVEL=DEBUG comfyvn.battle.engine` to review per-contender components and template picks.
- Determinism test: hit `/api/battle/sim` twice with identical payloads (including `seed`) and confirm `weights`, `breakdown`, and `rng` match byte-for-byte.
- Narration opt-out: send `"narrate": false` to keep payloads silent—`log` returns `[]` and `narration` is omitted, but provenance/breakdown remain.
- State persistence: pass `{ "state": {"rng": {...}},"persist_state": true }` to chain RNG draws across multiple sims; verify returned `state.rng` matches `response.rng`.

## Curl Quickstart
```bash
curl -s -X POST http://127.0.0.1:8001/api/battle/sim \
  -H 'Content-Type: application/json' \
  -d '{
        "stats": {"alpha": {"base": 10, "str": 2}, "beta": 7},
        "seed": 123,
        "pov": "alpha",
        "rounds": 2,
        "narrate": true
      }' | jq
```

```bash
curl -s -X POST http://127.0.0.1:8001/api/battle/resolve \
  -H 'Content-Type: application/json' \
  -d '{
        "winner": "alpha",
        "stats": {"alpha": {"base": 10, "str": 2}, "beta": 7},
        "seed": 123,
        "rounds": 1,
        "narrate": false
      }' | jq
```

## Verification Steps
1. Ensure `enable_battle_sim` is `false` by default in `config/comfyvn.json`.
2. Toggle the flag, restart (or reload), and call `/api/battle/sim` to confirm it returns `403` when disabled and `200` when enabled.
3. Run `pytest tests/test_battle_engine.py tests/test_battle_routes.py` for determinism and payload coverage.
4. Execute the system checker: `python tools/check_current_system.py --profile p2_battle --base http://127.0.0.1:8001`.
5. Document seed/outcome pairs in project changelogs when locking story milestones (use `provenance.resolved_outcome` for audit trails).
