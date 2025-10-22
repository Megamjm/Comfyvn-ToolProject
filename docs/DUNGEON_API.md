# Dungeon API — Grid Crawler & DOOM-lite Bridge

Intent: provide a thin runtime so designers can walk a lightweight dungeon (deterministic grid or WebGL “DOOM-lite” stage), trigger encounters, and mint VN snapshots that align with story event anchors.

---

## Feature Flag & Toggle
- Flag: `features.enable_dungeon_api` (default **false**). Flip it in `config/comfyvn.json → features.enable_dungeon_api` or via `feature_flags.load_feature_flags(refresh=True)` when testing interactively.
- Routes are mounted under `/api/dungeon/*` only when the flag is enabled.
- Checker: `python tools/check_current_system.py --profile p3_dungeon --base http://127.0.0.1:8001` verifies the flag default, route presence, and required files.

---

## Runtime Flow
```
+-------+      +------+      +------------------+      +---------+      +------+
| enter | ---> | step | ---> | encounter_start* | ---> | resolve | ---> | leave |
+-------+      +------+      +------------------+      +---------+      +------+
      |             |                |                        |              |
      v             v                v                        v              v
  room_state   movement          encounter                outcome      VN snapshot
  snapshot     snapshot?         snapshot?                snapshot?    (final + hooks)
```
`encounter_start` is optional; when no hazards remain, the call short-circuits.

Each request/response echoes a `snapshot_hooks` block describing the modder hooks available (`on_dungeon_enter`, `on_dungeon_snapshot`, `on_dungeon_leave`).

---

## Request & Response Contracts

### `POST /api/dungeon/enter`
- **Request fields**
  - `backend` (`"grid"`|`"doomlite"`; default `"grid"`)
  - `seed` (positive integer; generated if omitted)
  - `options` (backend-specific; see below)
  - Optional VN context: `scene`, `node`, `pov`, `worldline`, `vars` (object of VN state)
- **Response fields**
  - `room_state` → `{desc, exits[], hazards[], loot[], anchor, coords}`
  - `snapshot` → backend snapshot payload (deterministic for `{seed, vars, pov, worldline}`)
  - `anchors` → mapping: `session`, `backend`, `room`, and any supplied VN context
  - `determinism` → `{seed, backend, steps, encounters}`
  - `snapshot_hooks` → machine-readable hook catalogue for modders

`room_state.hazards[]` include `{id, name, type, severity, status, reward?, outcome?}`. Loot entries expose `{id, name, rarity, collected}`.

### `POST /api/dungeon/step`
- **Request fields**: `session_id`, `direction` (`north|south|east|west` for grid, plus `forward|back|left|right` aliases for DOOM-lite), optional `collect_loot` (list of loot ids), optional `snapshot` (boolean)
- **Response fields**: `movement` (`from`, `to`, `direction`, `blocked`, optional `reason`), updated `room_state`, `anchors`, `determinism`, optional `loot_collected[]`, optional `snapshot`

### `POST /api/dungeon/encounter_start`
- **Request fields**: `session_id`, optional `hazard_id`, optional `snapshot`
- **Response fields**: `encounter` (`{id, anchor, hazard, enemy{name,type,power}, difficulty, seed}`), `room_state`, `anchors`, optional `snapshot`

### `POST /api/dungeon/resolve`
- **Request fields**: `session_id`, `outcome` `{result|outcome: "victory"|"defeat"|"escape"}`, optional `snapshot`
- **Response fields**: `encounter_outcome` (`{encounter_id, outcome, roll, xp}`), `loot[]` (encounter rewards), updated `room_state`, `anchors`, `determinism`, optional `snapshot`

### `POST /api/dungeon/leave`
- **Request fields**: `session_id`
- **Response fields**:
  - `summary` (backend roll-up: rooms/sectors traversed, hazards resolved/remaining, loot ids)
  - `snapshot` (final backend snapshot)
  - `vn_snapshot` (Snapshot→Node/Fork payload):
    ```jsonc
    {
      "tool": "comfyvn.dungeon.snapshot",
      "version": "v1",
      "backend": "grid",
      "seed": 12345,
      "anchors": {...},
      "context": {...},
      "path": [
        {"anchor": "grid://room/2:2", "coords": [2,2], "entered_at": 1733788867.19}
      ],
      "encounters": [
        {"id": "grid://room/2:1hazard/0", "outcome": "victory", "started_at": ..., "completed_at": ...}
      ],
      "summary": {...},
      "payload": {... backend snapshot ...}
    }
    ```

---

## Backends

### Grid Backend (`backend: "grid"`)
- Deterministic 2D grid (3–12 tiles in each dimension, default 5×5).
- Hazards and loot are derived from seeded hashes of `{seed, x, y}`; identical seeds and context always yield the same room description, hazard roster, and encounter enemies.
- Options:
  - `width` / `height` (ints within 3–12)
  - `start` (`{"x": 2, "y": 3}` or `[x, y]`; defaults to centre)
- Loot anchors follow `grid://room/<x>:<y>loot/<index>`; encounter rewards mint deterministic composite ids `.../reward::<template_id>`.

### DOOM-lite Backend (`backend: "doomlite"`)
- Mirrors the Stage 3D WebGL sandbox (sectors with lighting/camera metadata).
- Sector profiles (hazards, loot drops, lighting accents) derive from `{seed, sector_index}`.
- Movement accepts `forward/back/left/right` (plus `north/south/east/west`, `advance/retreat/strafe_*` aliases). `left/right` adjust the camera transform instead of moving sectors.
- Options:
  - `sectors` (3–12, default 6) to control the corridor length

Both backends surface `snapshot` payloads with camera/grid metadata so downstream tooling can render thumbnails, build Storyboard cards, or hand off to Snapshot→Node/Fork unchanged.

---

## Modder Hooks & Debugging
- `on_dungeon_enter` — fired after `enter`; payload mirrors `{session_id, backend, seed, room_state, anchors, context}`.
- `on_dungeon_snapshot` — fired on every automatic or requested snapshot (`enter`, `step` when `snapshot=true`, `encounter_start`/`resolve` with `snapshot=true`, and `leave`). Payload includes `{session_id, backend, reason, anchor, snapshot, anchors, context}`.
- `on_dungeon_leave` — fired after `leave`; mirrors `{session_id, backend, seed, summary, vn_snapshot, context}`.

### Curl Recipes
```bash
# Enable the feature flag (local only)
python - <<'PY'
import json, pathlib
path = pathlib.Path("config/comfyvn.json")
data = json.loads(path.read_text(encoding="utf-8"))
data.setdefault("features", {})["enable_dungeon_api"] = True
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY

# Launch session
curl -s -X POST http://127.0.0.1:8001/api/dungeon/enter \
  -H 'Content-Type: application/json' \
  -d '{"backend":"grid","seed":1337,"scene":"demo.scene","pov":"hero"}' | jq

# Step north and request a snapshot
curl -s -X POST http://127.0.0.1:8001/api/dungeon/step \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"grid-1337-<id>","direction":"north","snapshot":true}' | jq '.snapshot'
```

### Determinism Checklist
- `{seed, pov, worldline, vars}` → same room descriptions, hazard lists, enemy rosters, and snapshot payloads.
- `snapshot.path` embeds ordered room anchors with timestamps so Snapshot→Node/Fork can reconstruct traversal sequences.
- Loot/encounter rewards use deterministic IDs to avoid duplicates when re-running sessions with the same input.

### Verification
- Run `python tools/check_current_system.py --profile p3_dungeon --base http://127.0.0.1:8001` before shipping changes.
- Ensure Windows/Linux smoke tests cover: flag default (off), curl round-trip (`enter → step → resolve → leave`), snapshot files, and hook envelopes.

---

## Related Docs
- `docs/dev_notes_dungeon_api.md` — developer debugging & hook recipes.
- `README.md` — highlights the new dungeon runtime under Systems.
- `architecture.md` / `architecture_updates.md` — architecture positioning and change log.

