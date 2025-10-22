# Dev Notes — Dungeon Runtime & Snapshot Hooks

Purpose: give contributors and modders a quick reference for the seeded dungeon runtime, backend hooks, and debug routines.

## Feature Flag & Launch Checklist
- Ensure `features.enable_dungeon_api` is set to `true` in `config/comfyvn.json` for local testing. Default remains `false`.
- Restart the backend (or call `feature_flags.refresh_cache()`) after editing the config so FastAPI picks up the flag.
- Sanity script: `python tools/check_current_system.py --profile p3_dungeon --base http://127.0.0.1:8001` validates flag defaults, route availability, and doc presence.

## Session Helpers (Python REPL)
```python
from comfyvn.dungeon.api import API

session = API.enter({"backend": "grid", "seed": 4242, "scene": "demo.scene"})
sid = session["session_id"]
API.step({"session_id": sid, "direction": "north", "snapshot": True})
API.encounter_start({"session_id": sid})
API.resolve({"session_id": sid, "outcome": {"result": "victory"}})
API.leave({"session_id": sid})
```

The `API` façade is process-wide; routes import the shared instance so hook history and deterministic RNG state live in memory for the lifetime of the server.

## Hooks & Payload Shapes
- `on_dungeon_enter`: emitted after `enter`. Payload includes `{session_id, backend, seed, room_state, anchors, context}`.
- `on_dungeon_snapshot`: emitted for every stored or requested snapshot. Payload includes `{session_id, backend, reason (enter|step|encounter_start|resolve|leave|manual), anchor, snapshot, anchors, context}`.
- `on_dungeon_leave`: emitted after `leave`. Payload includes `{session_id, backend, seed, summary, vn_snapshot, context}`.

Subscribe via:
```bash
curl -N http://127.0.0.1:8001/api/modder/hooks?events=on_dungeon_snapshot
# or WebSocket
websocat ws://127.0.0.1:8001/api/modder/hooks/ws
```

## Backend Notes
- Grid backend (`comfyvn/dungeon/backends/grid.py`):
  - Deterministic hazards/loot derived from `sha256(seed, x, y)`.
  - `collect_loot` accepts room anchor ids (`grid://room/<x>:<y>loot/<index>`).
  - Encounter rewards mint ids `.../reward::<template_id>` so re-runs do not duplicate drops.
- DOOM-lite backend (`comfyvn/dungeon/backends/doomlite.py`):
  - Sector traversal adjusts both index and camera transforms.
  - Hazards/loot derived from `sha256(seed, sector_index)`.
  - `left/right` lean the camera (strafe) without changing sector index.

## Snapshot→Node/Fork Payload
- `API.leave()` returns `vn_snapshot` with `tool="comfyvn.dungeon.snapshot"`, deterministic `path` history, encounter logs, and backend payloads (grid layout or stage camera transforms).
- Downstream tooling can map `anchors.session` (`dungeon://<session_id>`) and `anchors.room` to VN event anchors.

## Determinism Tips
- Always pass explicit `seed` and VN context (`scene`, `node`, `pov`, `worldline`, `vars`) when capturing snapshots for Storyboard nodes. Identical context will reproduce the same room descriptions, hazards, enemy rosters, and loot drops.
- Avoid mutating `vars` mid-session in tests: the `vars` dict is echoed in every hook payload so automation scripts can diff changes.

## Smoke Checklist
- ✅ Flag defaults to `false` in committed configs.
- ✅ `/api/dungeon/{enter,step,resolve,leave}` return 2xx when flag enabled; OPTIONS responds with POST in `Allow`.
- ✅ `on_dungeon_snapshot` fires on initial `enter`, optional snapshotting steps, encounter resolution, and final `leave`.
- ✅ `vn_snapshot.payload` stays deterministic for identical `{seed, backend, scene, node, pov, worldline, vars}`.
- ✅ Grid + DOOM-lite path histories preserve event anchors (`anchors.room`, `encounters[*].anchor`).

