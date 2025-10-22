# Collaboration Debug & Verification Checklist

- [ ] **Docs updated** — README, architecture.md, architecture_updates.md, CHANGELOG.md, docs/development_notes.md, docs/dev_notes_modder_hooks.md describe the collab CRDT, endpoints, GUI overlay, and modder hook.
- [ ] **Feature flag** — `config/comfyvn.json → features.enable_collaboration` defaults `true` and toggles take effect after `feature_flags.refresh_cache()`; Settings panel shows the new switch.
- [ ] **API surfaces** — `GET /api/collab/{health,presence/<scene>,snapshot/<scene>,history/<scene>?since=n}` respond with the documented payloads; `POST /api/collab/flush` forces disk persistence; WebSocket `/api/collab/ws?scene_id=...` returns the `room.joined` snapshot + presence roster.
- [ ] **Modder hooks** — subscribing to `modder.on_collab_operation` (REST `/api/modder/hooks/subscribe` or WebSocket) streams the same operations broadcast to clients; payload matches the CRDT envelope (`operations`, `applied`, `version`, `clock`).
- [ ] **Logs** — `logs/server.log` contains structured `collab.op applied scene=<id> version=<n> ops=[...]` entries for each mutating batch; DEBUG level traces presence + lock churn.
- [ ] **GUI overlay** — TimelineView displays the collab status badge (participants, lock owner/queue). Node edits propagate between two clients without conflicts; remote snapshots rehydrate in the editor.
- [ ] **Determinism** — Replaying the same operations (via `/api/collab/history?since=0`) on a fresh CRDT instance yields an identical snapshot (nodes, lines, lamport/version).
- [ ] **Provenance** — `data/scenes/<id>.json` stores `{version, lamport}` after collab edits; history entries include timestamps for audit trails.
- [ ] **Windows/Linux** — Collab persistence honours runtime paths (scene files under `runtime_paths.data_dir / "scenes"`); GUI/WebSocket continue to operate on both platforms.
- [ ] **Security** — No secrets leave the host; headers (`X-ComfyVN-User`, `X-ComfyVN-Name`) are optional and never persisted; `/api/collab/*` is guarded by the feature flag.
- [ ] **Dry-run** — Disable the flag or call `/api/collab/flush` during CI to ensure no writes occur; WebSocket attempts return HTTP 403 payload `{"detail": "collaboration_disabled"}` when the surface is off.
- [ ] **Tests** — `pytest tests/test_collab_crdt.py::test_operations_converge tests/test_collab_api.py::test_collab_history_endpoint` pass locally.
