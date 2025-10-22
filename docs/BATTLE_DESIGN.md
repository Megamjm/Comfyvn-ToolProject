# Battle UX & Simulation v0

## Overview
Battles now ship with two coordinated flows:

- **Editor picks** call `/api/battle/resolve` to stamp `vars.battle_outcome` and surface an always-on "Pick winner" prompt so authors stay in control of branching previews. Optional stat payloads trigger a seeded narration beat pulled from the Battle Narration prompt pack for instant copy previews.
- **Game simulations** use `/api/battle/sim` (legacy `/simulate` remains for backward compatibility) when automation needs a deterministic result. The engine applies a transparent formula and returns a full roll breakdown plus a provenance block (`seed`, `rng`, `weights`, predicted winner) so modders can reproduce the outcome offline. Narration is opt-in via the `narrate` flag.

`enable_battle_sim` gates the simulation route and defaults to `false`. Toggle it in `comfyvn.json` when QA or tooling needs access to the formula.

## Deterministic Formula v0
For each contender `C` we compute:

```
score(C) = base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)
```

- The RNG jitter is a deterministic draw in `[-1, 1)` scaled by the optional `rng` variance supplied per contender (defaults to `1.0`).
- Totals are normalised to weights so downstream tools can keep displaying odds.
- Ties fall back to alphabetical order after the totals are rounded to keep behaviour reproducible across backends.

## API Surface

### `POST /api/battle/resolve`
Payload fields:
- `winner` (str, required) – branch identifier to commit.
- `state` (object, optional) – scenario state; when provided and `persist_state=true` the winner is deep-copied into `state.variables` before returning.
- `stats` (object, optional) – contender map (same schema as `simulate`) to enable seeded narration.
- `seed` (int, optional) – reused for narration RNG when `stats` supplied.
- `pov` (str, optional) – POV used to pick narration templates; defaults to `narrator`.
- `rounds` (int, optional, ≥ 1) – number of narration beats when narration is enabled (defaults to `1`).
- `narrate` (bool, optional, default `true`) – disable to skip narration/log generation even when stats are supplied.
- `persist_state` (bool, default `true`).

Response fields:
- `outcome`, `vars`, `persisted` (unchanged from the previous engine).
- `editor_prompt` – always `"Pick winner"` to keep Studio overlays consistent.
- `formula` – identifier for the active battle formula (`base + STR*...`).
- `seed`, `rng`, `weights`, `breakdown` – supplied when stats were analysed so modders can reuse the roll sheet.
- `predicted_outcome` – engine-picked winner based on stats before the editor override. Useful for QA notes.
- `log`, `narration` – present when narration was generated.
- `provenance` – `{formula, seed, rng, weights, predicted_outcome, resolved_outcome}` for audit trails.
- `state` – deep copy when `state` supplied.

Emits `on_battle_resolved` with the full payload plus `weights`, `breakdown`, `rng`, `provenance`, `predicted_outcome`, `narrate`, and `rounds` for automation dashboards.

### `POST /api/battle/sim` *(feature gated by `enable_battle_sim`)*
Payload fields:
- `stats` – map of contenders. Each contender accepts either a single number (treated as `base`) or an object with keys `base`, `str`, `agi`, `weapon_tier`, `status_mod`, and optional `rng` (variance multiplier).
- `seed` (int, optional), `rng` (state object, optional), `rounds` (int ≥ 1), `pov` (str), `narrate` (bool, default `true`), `persist_state` (bool), `state` (object with `rng` inside).

Response fields:
- `outcome`, `seed`, `weights`, `rng`, `breakdown`, `formula`.
- `log` / `narration` – only when `narrate=true`.
- `provenance` – matches the resolve payload (omits `resolved_outcome` because simulation outcome is authoritative).
- `persisted` – mirrors whether RNG state was written back to the supplied state.

Emits `on_battle_simulated` with `weights`, `breakdown`, `rng`, `provenance`, `narrate`, `rounds`, and optional `log`/`narration` so automation pipelines can display the roll sheet.

## Stats Schema
Example contender payload:

```
"team_a": {
  "base": 12,
  "str": 8,
  "agi": 3,
  "weapon_tier": 2,
  "status_mod": 0.5,
  "rng": 1.0
}
```

All values are coerced to floats; negative numbers are allowed but the engine shifts totals to keep weights normalised.

## Testing & Debugging
- Use `COMFYVN_BATTLE_SEED=<int>` to set the default seed for both `resolve` narration and simulations.
- Supply `"narrate": false` when you only need the deterministic breakdown/provenance without the seeded narration beats.
- `pytest tests/test_battle_engine.py tests/test_battle_routes.py` exercises determinism, breakdown payloads, hook wiring, and feature flag behaviour.
- Subscribe to `on_battle_resolved` / `on_battle_simulated` through `/api/modder/hooks/subscribe` to feed overlays or telemetry dashboards.
- Quick reference (flags, payload fields, curl samples) lives in `docs/dev_notes_battle_sim.md`.

## Prompt Packs & Narration
- Battle narration beats live in `docs/PROMPT_PACKS/BATTLE_NARRATION.md`. Keep new templates aligned with the formula components so rolls and story beats stay in sync.
- Visual styling guidance for props and overlays references `docs/VISUAL_STYLE_MAPPER.md`; pair winners with appropriate prop sets when bridging battle outcomes into scene dressing.

## Roadmap Notes
- v1 will expose expanded component weights (DEF, LCK, traits) once the combat analyser lands.
- WebSocket push of simulation logs will follow after the runner bus moves to AsyncIO.
