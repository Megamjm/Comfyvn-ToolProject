# ComfyVN Narrator Rails

## Overview
- Observe → Propose → Apply loop managed entirely on the server.
- Deterministic offline planner drives proposals; no network required unless feature flags are flipped.
- Ring-buffer history (12 frames) enables stop, resume, and rollback of applied proposals.
- Three-turn safety cap per node prevents runaway automation.

## Feature Flags
- `enable_narrator` — gate for all `/api/narrator/*` endpoints (default: OFF).
- `enable_llm_role_mapping` — required for narrator/role orchestration, defaults to OFF.
- UI callers may pass `force: true` when developing locally, but production flows must honour the flags.

## Modes & Turn Lifecycle
- **Observe**: Snapshot canonical node state (`variables`, `context`, `pov`). Queue cleared unless explicitly preserved.
- **Propose**: Offline planner drafts JSON proposals, but never mutates session state. Each draft enters the apply queue.
- **Approve / Apply**: Approvals pop proposals off the queue, merge their `vars_patch`, and increment the node turn counter.
- **Continue**: Optional post-apply acknowledgement if additional automation should kick off.
- **Stop**: Halts further proposals; queue is retained for audit.
- **Rollback (N)**: Restores the session to a previous snapshot, tagging rolled-back proposals.

Turn limit: `applied_turns + pending_turns ≤ 3` per `scene_id + node_id`. Additional propose calls after the limit return HTTP 409.

## Session State Model
- Keyed by `scene_id`. Each session tracks:
  - `node_id`, `mode`, `role`, `pov`
  - `variables` (dict, cloned deep before mutations)
  - `queue` (ordered list of proposal ids)
  - `proposals` (map of id → payload)
  - `turn_counts` per node
  - `history` deque of [`NarratorSnapshot`] capturing state before every apply
- History window size: 12 snapshots. Rollbacks replay `history.pop()` and mark proposals as `rolled_back`.

### Snapshot Structure
```json
{
  "node_id": "scene_a.node_3",
  "variables": {"stats": {"courage": 3}},
  "turn_counts": {"scene_a.node_3": 2},
  "last_choice": "choice_continue",
  "proposal_id": "p0002",
  "created_at": 1731262200.12
}
```

## API Reference (`/api/narrator/*`)
- `GET /status?scene_id=SCENE`
  - Returns the active session state.
- `POST /mode`
  ```json
  {
    "scene_id": "scene_a",
    "node_id": "scene_a.node_3",
    "mode": "observe",
    "variables": { "stats": {"courage": 3} },
    "context": [{"speaker":"MC","text":"I can do this."}],
    "pov": "mc001",
    "reset_queue": false
  }
  ```
- `POST /propose`
  ```json
  {
    "scene_id": "scene_a",
    "node_id": "scene_a.node_3",
    "prompt": "Resolve cliffhanger while preserving player choice.",
    "context": [{"speaker":"Antagonist","text":"Jump!"}],
    "choices": [{"id":"choice_confront","priority":0}],
    "role": "Narrator"
  }
  ```
  - Response contains `state.queue[]` with enriched proposals.
- `POST /apply`
  ```json
  {"scene_id":"scene_a", "proposal_id":"p0001"}
  ```
- `POST /stop`
  ```json
  {"scene_id":"scene_a"}
  ```
- `POST /rollback`
  ```json
  {"scene_id":"scene_a","steps":2}
  ```
- `POST /chat`
  ```json
  {
    "scene_id": "scene_a",
    "node_id": "scene_a.node_3",
    "role": "Narrator",
    "pov": "mc001",
    "message": "Summarise the previous beat for the player.",
    "context": [{"speaker":"MC","text":"I am still breathing."}]
  }
  ```

All endpoints honour feature flags. Error codes:
- `403` when flags disabled (unless `force: true` present).
- `404` when session or proposal missing.
- `409` for turn-cap violations or duplicate applies.

## Proposal Schema
```json
{
  "id": "p0003",
  "scene_id": "scene_a",
  "node_id": "scene_a.node_3",
  "mode": "propose",
  "role": "Narrator",
  "turn_index": 2,
  "message": "Offer player a moment to reflect.",
  "narration": "[offline:7ea891aa] Narrator reflects...",
  "rationale": "Offline planner suggested choice 'choice_confront'.",
  "choice_id": "choice_confront",
  "vars_patch": {
    "$narrator": {
      "scene_id": "scene_a",
      "node_id": "scene_a.node_3",
      "turn": 2,
      "choice_id": "choice_confront",
      "digest": "7ea891aa"
    }
  },
  "plan": {
    "adapter": "offline.local",
    "model": "codex/offline-narrator",
    "device": "cpu",
    "budget": {
      "limit": 0,
      "spent": 0,
      "remaining": 0,
      "would_spend": 44,
      "would_remaining": 0,
      "permitted": true
    },
    "context": {"digest":"7ea891aa","summary":"...","roster":"MC"}
  },
  "status": "pending",
  "created_at": 1731262212.4,
  "metadata": {"adapter":"offline.local","model":"codex/offline-narrator"}
}
```

## Hooks
- `on_narrator_proposal` — fires on proposal enqueue.
- `on_narrator_apply` — fires on apply and on rollback replay (`rolled_back: true`).
- Hooks emit through the existing modder bus; they respect webhooks and plugin listeners.

## Determinism & Safety
- Offline adapter produces stable outputs keyed by `(role, message, context digest)`.
- No state mutations happen during `propose` or `chat`; only `apply` mutates session variables.
- `vars_patch` supports `$replace` and `$delete` helper keys; patches are shallow-merged.
- Ring buffer ensures rollback is idempotent; repeated rollback without new applies is a no-op.
- Logs contain digests and role identifiers but never raw secrets. Pricing links (when supplied by adapters) remain opaque.

## Debugging & Testing Checklist
- ✅ `/api/narrator/mode` returns status with queue, history size, and variables copy.
- ✅ `/api/narrator/propose` respects three-turn cap and enqueues deterministic IDs.
- ✅ `/api/narrator/apply` merges `vars_patch`, updates `turn_counts`, and replays hook.
- ✅ `/api/narrator/stop` flips `halted` while preserving the queue for inspection.
- ✅ `/api/narrator/rollback` replays history frames and emits rollback hooks.
- ✅ `/api/narrator/chat` surfaces offline replies (`adapter = offline.local`).
- Use `enable_narrator` flag when integrating with GUI; tests can include `"force": true`.
- Smoke integration by running `python tools/check_current_system.py --profile p2_narrator --base http://127.0.0.1:8001`; the profile asserts flags (`enable_narrator`, `enable_llm_role_mapping`), routes, and docs are available before promotion.
