# Battle Layer Hooks & Debug Notes

Updated: 2025-11-06 • Scope: Scenario battle choice vs simulation workflows  
Owner: Project Integration & Narrative Systems

The battle layer introduces a REST surface that lets authors pick outcomes manually
(`resolve` mode) or run weighted simulations (`simulate` mode) before committing to a
branch. Both routes sit on top of `comfyvn/battle/engine.py`, which keeps combat
decisions deterministic and exposes seeded narration logs for downstream tooling.

---

## 1. Entry Points

- Python engine helpers live at `comfyvn/battle/engine.py`.
  - `resolve(winner: str) -> dict` returns `{"outcome": winner, "vars": {"battle_outcome": winner}}`.
  - `simulate(stats: dict, seed: int | None, pov: str | None) -> dict` rolls weighted odds,
    emits POV-aware narration (`log[]`), and always echoes the seed it used.
- FastAPI router: `comfyvn/server/routes/battle.py`
  - `POST /api/battle/resolve`
  - `POST /api/battle/simulate`
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
  "persist_state": true
}
```

- `winner` (**required**): branch identifier, typically matching a choice ID or label.
- `persist_state` (optional, default `true`): when `false`, the API returns the outcome
  without mutating the runner state (useful for dry runs).

Response:

```jsonc
{
  "outcome": "team_a",
  "vars": {"battle_outcome": "team_a"},
  "persisted": true
}
```

The runner broadcasts the `vars.battle_outcome` update so Studio panels and external
automation can sync immediately.

### 2.2 Simulate (Weighted Mode)

Endpoint: `POST /api/battle/simulate`  
Payload:

```jsonc
{
  "stats": {"team_a": 55, "team_b": 45},
  "seed": 1337,
  "pov": "narrator",
  "rounds": 3
}
```

- `stats` (**required**): weight map for contenders. Values are normalized during the roll.
- `seed` (optional): supply for deterministic replays; omit to let the engine draw from
  the scenario RNG. The response always includes the actual seed used.
- `pov` (optional): informs narration wording (`"narrator"`, `"team_a"`, `"villain"`, etc.).
- `rounds` (optional, default `1`): number of narration beats to emit in the log.

Response:

```jsonc
{
  "outcome": "team_a",
  "seed": 1337,
  "log": [
    {"turn": 1, "pov": "narrator", "text": "Team A seizes the initiative."},
    {"turn": 2, "pov": "narrator", "text": "Team B falters under the assault."},
    {"turn": 3, "pov": "narrator", "text": "Victory tilts decisively toward Team A."}
  ],
  "weights": {"team_a": 0.55, "team_b": 0.45}
}
```

Pair this payload with Timeline overlays, VO/SFX triggers, or custom UI while keeping the
underlying scenario state untouched until `resolve()` is called.

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
  1. Calls `simulate` when the node is first focused.
  2. Displays the returned `log[]` (with POV tinting) alongside odds and branch labels.
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
curl -s -X POST http://127.0.0.1:8001/api/battle/simulate \
  -H 'Content-Type: application/json' \
  -d '{"stats": {"hero": 70, "villain": 30}, "pov": "hero"}' | jq
```

Take the returned seed and outcome, then issue:

```bash
curl -s -X POST http://127.0.0.1:8001/api/battle/resolve \
  -H 'Content-Type: application/json' \
  -d '{"winner": "hero"}' | jq
```

- For tests, assert that `vars.battle_outcome` matches and that the `log[]` length meets
  expectations when `rounds` is specified.

---

## 6. Troubleshooting

- Missing `stats`: the API returns HTTP 422 validation errors. Ensure keys are strings and
  values are numeric.
- Determinism drift: confirm both endpoints receive the same `seed` and that no custom
  RNG is being used before/after the call.
- Narration templates are stubbed for now; enrich them under `comfyvn/battle/narration.py`
  (planned) or by injecting custom log entries in automation scripts.
- If Studio overlays do not refresh, check that `/api/battle/simulate` responses include
  `log[]`; empty logs indicate templates were filtered out (inspect DEBUG logs for detail).

---

Related docs: `README.md` (Battle Layer section), `architecture.md`, `architecture_updates.md`,
`docs/dev_notes_modder_hooks.md`. The CODEX work order describing scope lives at
`docs/CODEX_STUBS/2025-10-21_BATTLE_LAYER_CHOICE_SIM_A_B.md`.
