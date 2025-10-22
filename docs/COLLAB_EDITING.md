# Collaboration Editing — CRDT + Presence

> The collaboration stack exposes a Lamport-clock CRDT document, room-level
> presence with cursors and selections, and a soft locking workflow (“request
> control”) that keeps contributors coordinated under latency.

## Feature flags

- `features.enable_collaboration` (default `true`) gates the WebSocket service.
- `features.enable_collab` is treated as an alias for tooling profiles; if it is
  set explicitly it will override `enable_collaboration`.
- Toggle flags via **Settings → Debug & Feature Flags** or edit
  `config/comfyvn.json`, then call `feature_flags.refresh_cache()` in long-lived
  processes.

When the flag is disabled every route under `/api/collab/*` responds with HTTP
403 (`collaboration_disabled`).

## Document model (CRDT)

`comfyvn/collab/crdt.py` provides `CRDTDocument`, a scene-oriented CRDT that
tracks:

- Scene fields (`title`, `start`) through last-writer-wins registers.
- `meta` entries keyed by string, also LWW.
- Graph nodes (`graph.node.upsert`/`graph.node.remove`) with LWW payloads per
  node id.
- Script lines stored via LWW registers and a deterministic order list.

Every operation (`CRDTOperation`) carries:

| Field       | Description                                   |
| ----------- | --------------------------------------------- |
| `op_id`     | Globally unique id (`actor:monotonic`)        |
| `actor`     | Client identifier                             |
| `clock`     | Actor Lamport timestamp (int)                 |
| `kind`      | Handler key (`scene.field.set`, …)            |
| `payload`   | Handler-specific data                         |
| `timestamp` | Wall clock (seconds) provided by the emitter  |

`CRDTDocument.apply_operation` deduplicates ops, advances the server Lamport
clock, and increments `version` only when the underlying register changes. Use
`apply_many` for batches: ≤ 64 ops per bundle keeps latency low while preventing
op storms.

Snapshots (`document.snapshot()`) include `nodes`, `lines`, `order`, and `meta`
ready for WebSocket delivery or persistence. `operations_since(version)` returns
logged operations for incremental replay.

## Collaboration rooms

`comfyvn/collab/room.py` orchestrates `CollabRoom` instances:

- Lazy bootstrap from storage through `comfyvn/server/core/collab.get_room`.
- Presence bookkeeping (`CollabPresence`) with per-client cursor, selection,
  focus, typing, capability set, and heartbeat timestamps.
- Soft lock queue (`request_control` / `release_control`) with 30 s default TTL
  and automatic promotion when owners disconnect or expire.
- Persistence hook (`flush`) that writes the CRDT snapshot when dirty.
- `CollabRoom.register_headless_client()` provisions clients for HTTP tooling by
  creating a no-op websocket shim, marking the participant as `headless`, and
  reusing the same join/leave bookkeeping as WebSocket clients.

Room methods are idempotent: multiple `apply_operations` calls with the same
`op_id` do not mutate state; repeated `join` calls refresh the client heartbeat
without duplicating entries.

## WebSocket flow (`/api/collab/ws`)

1. Clients connect with `?scene_id=<scene>` and optional headers
   `X-ComfyVN-User`, `X-ComfyVN-Name`.
2. Server replies with `room.joined` payload:
   - `snapshot`, `version`, `clock`
   - Current `presence`
   - Feature flags echoed for the session.
3. Client messages:
   - `ping` → `pong`
   - `presence.update` `{cursor, selection, focus, typing, capabilities}`
   - `doc.pull` to fetch a fresh snapshot
   - `doc.apply` `{operations: [...], since?: version, include_snapshot?: bool}`
   - `control.request` / `control.release`
   - `feature.refresh`
4. Server broadcasts:
   - `doc.update` to all clients (`operations`, optional `history`, optional
     `snapshot`)
   - `presence.update` when participants change
   - `control.state` updates addressing individual requesters
   - `error` envelopes for unknown message types or exceptions

Dropped packets are tolerated: clients can resend operations (ids must remain
stable) or issue `doc.pull` on reconnect to resynchronise.

## REST helpers

While WebSockets power real-time editing, a thin REST surface exists for
scripts, health checks, and HTTP-only tooling (`comfyvn/server/routes/collab.py`).

| Endpoint                         | Method | Purpose                                                   |
| -------------------------------- | ------ | --------------------------------------------------------- |
| `/api/collab/health`             | GET    | Basic health/feature-flag probe                           |
| `/api/collab/room/create`        | POST   | Preload or create a room and fetch snapshot + presence    |
| `/api/collab/room/join`          | POST   | Register/refresh a client without a WebSocket connection  |
| `/api/collab/room/leave`         | POST   | Remove previously joined HTTP clients and release locks   |
| `/api/collab/room/apply`         | POST   | Apply CRDT ops over HTTP (broadcast + modder hook mirror) |
| `/api/collab/room/cache`         | GET    | Hub statistics (rooms/clients/dirty)                      |
| `/api/collab/presence/{scene}`   | GET    | Presence snapshot (same payload as WebSocket)             |
| `/api/collab/snapshot/{scene}`   | GET    | Full CRDT snapshot                                         |
| `/api/collab/history/{scene}`    | GET    | Logged operations since version                           |
| `/api/collab/flush`              | POST   | Explicit persistence trigger                               |

`room/join` accepts:

```json
{
  "scene_id": "demo_scene",
  "client_id": "http:editor",
  "user_name": "Assistant",
  "clock": 42,
  "cursor": {"node": "intro", "offset": 3},
  "selection": {"node": "intro", "range": [0, 10]},
  "focus": "timeline",
  "typing": true,
  "capabilities": ["viewer", "script-edit"],
  "since": 10,
  "request_control": true,
  "control_ttl": 45.0
}
```

The handler mirrors WebSocket semantics: presence updates propagate to other
participants, optional control requests enqueue the client, and passing `since`
returns `history` for offline diffing. Responses echo `headless` and include a
`ws` block (endpoint + headers) for clients that later upgrade to a socket.

`room/apply` accepts the same operation envelopes as WebSocket `doc.apply`, emits
`on_collab_operation`, can broadcast to connected clients (default), and supports
`history_since` / `include_snapshot` for deterministic state reconstruction.

`room/leave` optionally clears soft locks by supplying `{"release_control": true}`.

## Recovery & reconnect strategy

1. Re-establish the WebSocket (or call `room/join`) to refresh presence.
2. Issue `doc.pull` to receive the authoritative snapshot.
3. Compare local version with server `version`:
   - If behind: request `history` (`doc.apply` with `since`) and replay missing
     operations.
   - If ahead (optimistic local edits): resend pending operations; duplicates
     will be ignored, keeping the document convergent.
4. Reapply cursor/selection state via `presence.update`.

Recommended op batch size: 32 – 64 operations. Larger bundles increase latency
and the risk of partial retries.

## Debugging checklist

- Confirm flag state:

  ```bash
  python - <<'PY'
  from comfyvn.config import feature_flags
  print(feature_flags.load_feature_flags().get("enable_collaboration"))
  PY
  ```

- Probe health:

  ```bash
  curl -fsS http://127.0.0.1:8001/api/collab/health | jq
  ```

- Join via REST (headless smoke):

  ```bash
  curl -fsS -X POST http://127.0.0.1:8001/api/collab/room/join \
    -H "Content-Type: application/json" \
    -d '{"scene_id":"demo_scene","client_id":"cli","user_name":"CLI"}'
  ```

- Fetch history after automated edits:

  ```bash
  curl -fsS "http://127.0.0.1:8001/api/collab/history/demo_scene?since=0" | jq '.history | length'
  ```

- Flush before shutting down a test server:

  ```bash
  curl -fsS -X POST http://127.0.0.1:8001/api/collab/flush
  ```

## Modder & debug hooks

- WebSocket broadcasts mirror `emit_modder_hook("on_collab_operation", …)` so
  modders can observe the same envelopes.
- Presence payloads include `caps` (sorted list) and `headless` markers for capability-aware overlays and HTTP-tooling badges.
- Logs emit `collab.op applied scene=<id> version=<n> ops=[...]` whenever an
  operation mutates state.
- Developers can inspect the in-memory hub with
  `/api/collab/room/cache` (rooms, clients, dirty counters).

## Convergence demo (LAN, <200 ms target)

1. Launch two clients (Windows & Linux recommended) pointing at the same server.
2. Client A opens a scene and connects via the WebSocket UI.
3. Client B joins via UI or `room/join` REST helper (then upgrades to WebSocket).
4. Both edit the same script node alternately:
   - Insert lines with increasing counters.
   - Move cursor selections around the timeline.
5. Observe:
   - Both timelines stay in sync (no duplicate or missing lines).
   - Presence overlays update under 200 ms (watch `last_seen` and cursor markers).
6. Drop Client B’s network connection temporarily, then reconnect:
   - Client B requests `doc.pull` on reconnect and resumes editing without
     losing Client A’s changes.
7. Grant control to Client B (`control.request`); Client A sees the queued state
   and can request control back when B releases.

Document these steps (with screenshots or terminal captures) in the internal
docs channel as part of the smoke verification checklist.

## Windows/Linux smoke notes

- Windows: verify WebSocket upgrades work when the firewall prompt appears; add
  the executable to the private network allow list.
- Linux: ensure the server is reachable on `127.0.0.1:8001` with no SELinux
  denials; `journalctl -u comfyvn` helps trace connection drops.
- Both platforms: confirm timezone alignment—presence timestamps are wall clock
  seconds, so mismatched system clocks will skew the UI until NTP resyncs.

---

For architecture diagrams and deeper internals see `architecture.md` section
“Collaboration service”. The change log entry for this phase lives in
`CHANGELOG.md` under the P4 collaboration milestone.
