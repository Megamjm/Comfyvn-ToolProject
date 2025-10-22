# Battle Layer Hooks & Debug Notes

Updated: 2025-11-06 • Scope: Scenario battle choice vs simulation workflows  
Owner: Project Integration & Narrative Systems

The battle layer introduces a REST surface that lets authors pick outcomes manually
(`resolve` mode) or run weighted simulations (`sim` mode) before committing to a
branch. Both routes sit on top of `comfyvn/battle/engine.py`, which keeps combat
decisions deterministic, surfaces component breakdowns, and exposes optional seeded
narration logs for downstream tooling.

---

## 1. Entry Points

- Python engine helpers live at `comfyvn/battle/engine.py`.
  - `resolve(winner: str, *, stats=None, seed=None, pov=None, rounds=1, narrate=True)` stamps the outcome, returns verbose metadata, and (optionally) generates narration.
  - `simulate(stats: dict, *, seed=None, rng_state=None, pov=None, rounds=3, narrate=True)` returns a `BattleSimulationResult` (outcome, weights, breakdown, rng state, provenance, optional narration).
- FastAPI router: `comfyvn/server/routes/battle.py`
  - `POST /api/battle/resolve`
  - `POST /api/battle/sim` (feature gated; legacy `/api/battle/simulate` alias remains)
- Scenario Runner consumes both routes. Simulation logs appear in the choice overlay;
  resolving a winner updates the underlying scenario state and advances the branch.

---

## 2. API Contracts

### 2.1 Resolve (Choice Mode)

Endpoint: `POST /api/battle/resolve`  
Payload:

```jsonc
{
  "winner": "team_a",
  "persist_state": true,
  "rounds": 2,
  "narrate": true,
  "stats": {
    "team_a": {"base": 12, "str": 4, "agi": 3, "weapon_tier": 2},
    "team_b": {"base": 10, "str": 5, "agi": 2, "weapon_tier": 1}
  },
  "seed": 404,
  "pov": "narrator"
}
```

- `winner` (**required**): branch identifier, typically matching a choice ID or label.
- `persist_state` (optional, default `true`): when `false`, the API returns the outcome
  without mutating the runner state (useful for dry runs).
- `rounds` (optional, default `1`): narration beats to emit when `narrate=true`.
- `narrate` (optional, default `true`): set to `false` to skip narration/log generation while still receiving breakdown/provenance.
- `stats`, `seed`, `pov` (optional): enable seeded narration and predicted outcome analysis.

Response:

```jsonc
{
  "outcome": "team_a",
  "vars": {"battle_outcome": "team_a"},
  "persisted": true,
  "editor_prompt": "Pick winner",
  "formula": "base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)",
  "seed": 404,
  "rng": {"seed": 404, "value": 2376242568, "uses": 2},
  "weights": {"team_a": 0.61, "team_b": 0.39},
  "breakdown": [
    {"name": "team_a", "total": 19.5, "components": {"base": 12, "strength": 4, "agility": 1.5, "weapon_tier": 1.5, "status_mod": 0, "rng": 0.5}},
    {"name": "team_b", "total": 12.3, "components": {"base": 10, "strength": 5, "agility": 1, "weapon_tier": 0.75, "status_mod": 0, "rng": -4.45}}
  ],
  "predicted_outcome": "team_a",
  "log": [
    {"turn": 1, "pov": "narrator", "text": "Team A seizes the initiative."},
    {"turn": 2, "pov": "narrator", "text": "Team B scrambles under the assault."}
  ],
  "narration": "Team A seizes the initiative.",
  "provenance": {
    "formula": "base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)",
    "seed": 404,
    "rng": {"seed": 404, "value": 2376242568, "uses": 2},
    "weights": {"team_a": 0.61, "team_b": 0.39},
    "predicted_outcome": "team_a",
    "resolved_outcome": "team_a"
  }
}
```

The runner broadcasts the `vars.battle_outcome` update so Studio panels and external
automation can sync immediately. When `narrate=false`, the response omits `log`/`narration`
but still includes `rng`, `breakdown`, `weights`, and `provenance`.

### 2.2 Sim (Deterministic Mode)

Endpoint: `POST /api/battle/sim` *(feature gated; `/api/battle/simulate` aliases here)*  
Payload:

```jsonc
{
  "stats": {"team_a": 55, "team_b": 45},
  "seed": 1337,
  "pov": "narrator",
  "rounds": 3,
  "narrate": false
}
```

- `stats` (**required**): weight map for contenders. Scalars are coerced to `{base: value}`; objects may include `base`, `str`, `agi`, `weapon_tier`, `status_mod`, and optional `rng` variance.
- `seed` / `rng` (optional): supply for deterministic replays; omit both to let the engine generate a seed. The response always echoes the actual seed and RNG state.
- `pov` (optional): informs narration wording (`"narrator"`, `"team_a"`, `"villain"`, etc.).
- `rounds` (optional, default `3`): number of narration beats to emit when `narrate=true`.
- `narrate` (optional, default `true`): disable to receive a silent roll sheet (no `log`/`narration`) while keeping determinism data.
- `persist_state` + `state` (optional): when both are supplied and `persist_state=true`, the response writes the updated RNG state back into `state["rng"]`.

Response:

```jsonc
{
  "outcome": "team_a",
  "seed": 1337,
  "rng": {"seed": 1337, "value": 991728512, "uses": 2},
  "weights": {"team_a": 0.55, "team_b": 0.45},
  "breakdown": [
    {"name": "team_a", "total": 22.1, "components": {"base": 55, "strength": 0, "agility": 0, "weapon_tier": 0, "status_mod": 0, "rng": -32.9}},
    {"name": "team_b", "total": 18.9, "components": {"base": 45, "strength": 0, "agility": 0, "weapon_tier": 0, "status_mod": 0, "rng": -26.1}}
  ],
  "formula": "base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)",
  "provenance": {
    "formula": "base + STR*1.0 + AGI*0.5 + weapon_tier*0.75 + status_mod + rng(seed)",
    "seed": 1337,
    "rng": {"seed": 1337, "value": 991728512, "uses": 2},
    "weights": {"team_a": 0.55, "team_b": 0.45},
    "predicted_outcome": "team_a"
  },
  "log": [],
  "narration": null,
  "persisted": false
}
```

When `narrate=true`, `log[]` and `narration` appear with the requested number of beats.
Pair the payload with Timeline overlays, VO/SFX triggers, DVRs, or QA harnesses while
keeping the underlying scenario state untouched until `resolve()` is called.

---

## 3. Determinism & Seeding

- Scenario Runner passes its deterministic RNG seed in by default. Use the `seed` field
  to force deterministic replays across machines or CI jobs.
- Environment variable `COMFYVN_BATTLE_SEED` overrides the initial seed that Studio will
  supply when none is provided; useful for integration tests or demo recordings.
- Set `COMFYVN_LOG_LEVEL=DEBUG` (or `comfyvn.battle.engine`-specific logger) to trace:
  - Normalized weights
  - Drawn random value
  - Selected outcome
  - Narration template picks
- Logs land in `logs/server.log` by default and are mirrored inside the Studio Log Hub.

---

## 4. Scenario Runner Integration

- Battle nodes flag their metadata via `{"battle": true}` on the choice definition.
- Runner behaviour:
  1. Calls `engine.simulate` (surfaced as `/api/battle/sim`) when the node is first focused.
  2. Displays the returned `breakdown`/`weights` and, when enabled, the `log[]` (with POV tinting) alongside odds and branch labels.
  3. Keeps the node pending until the author clicks “Lock Outcome” (or the automation
     client calls `/api/battle/resolve`).
- The `vars.battle_outcome` variable is written to the scenario state so scripts can
  build conditional expressions (`if vars.battle_outcome == "team_a": ...`).
- Seeds from `simulate` are stored with the runner session; re-opening the session
  replays the same narration unless a new `simulate` request is issued.

---

## 5. Modder & Automation Hooks

- Use the simulation payload to drive bespoke SFX/VFX pipelines:
  - Feed `log[]` into TTS or Foley generators.
  - Trigger ComfyUI render jobs or animation cues via `/api/schedule/enqueue`.
  - Register resulting assets with `AssetRegistry.register_file` and reference them in
    downstream battle aftermath scenes.
- Subscribe to runner events (Studio emits `battle.simulated` and `battle.resolved`
  notifications) to keep external dashboards in sync.
- CLI example:

```bash
curl -s -X POST http://127.0.0.1:8001/api/battle/sim \
  -H 'Content-Type: application/json' \
  -d '{"stats": {"hero": 70, "villain": 30}, "pov": "hero", "narrate": true}' | jq
```

Take the returned seed and outcome, then issue:

```bash
curl -s -X POST http://127.0.0.1:8001/api/battle/resolve \
  -H 'Content-Type: application/json' \
  -d '{"winner": "hero"}' | jq
```

- For tests, assert that `vars.battle_outcome` matches and that the `log[]` length meets
  expectations when `narrate=true` and `rounds` is specified.

---

## 6. Troubleshooting

- Missing `stats`: the API returns HTTP 422 validation errors. Ensure keys are strings and
  values are numeric.
- Determinism drift: confirm both endpoints receive the same `seed` and that no custom
  RNG is being used before/after the call.
- Narration templates are stubbed for now; enrich them under `comfyvn/battle/narration.py`
  (planned) or by injecting custom log entries in automation scripts.
- If Studio overlays do not refresh, check that `/api/battle/sim` responses include the expected `breakdown` and (when `narrate=true`) populated `log[]`; empty logs indicate narration was disabled or filtered (enable DEBUG logs for detail).

---

Related docs: `README.md` (Battle Layer section), `architecture.md`, `architecture_updates.md`,
`docs/dev_notes_modder_hooks.md`. The CODEX work order describing scope lives at
`docs/CODEX_STUBS/2025-10-21_BATTLE_LAYER_CHOICE_SIM_A_B.md`.
