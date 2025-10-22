# P5 Advisory & Studio Bundle Export

This document captures the liability gate, advisory scanning, and Studio bundle export flow introduced for the P5 milestone.

## Feature Flags

- `features.enable_advisory` (default: `false`) — exposes the advisory scan API and enforcement surface.
- `features.enable_export_bundle` (default: `false`) — unlocks the Studio bundle exporter (API and CLI).

Enable both flags in `comfyvn.json` before exposing the workflow to contributors.

## Policy Gate Workflow

1. Operator submits `POST /api/policy/ack` with their user id (optional notes stored in the settings blob).
2. `GET /api/policy/ack` or `GET /api/export/bundle/status` returns gate state; `requires_ack = true` blocks bundle exports.
3. Advisory scanning always runs via `policy_enforcer`, even when the gate blocks execution, so teams can review findings.

If the gate is not acknowledged `policy_enforcer` raises `HTTP 423` and the payload includes `result.gate.requires_ack = true`.

## API Surface

### Bundle Status

```
GET /api/export/bundle/status
```

Payload:

- `enabled` — `true` when `enable_export_bundle` flag is on.
- `gate` — latest evaluation for the supplied action (defaults to `export.bundle`).
- `status` — persisted acknowledgement state (`ack_legal_v1`, timestamp, override toggle).

### Policy Acknowledgement

```
GET /api/policy/ack
POST /api/policy/ack
```

- `GET` returns gate status and guidance message.
- `POST` stores the acknowledgement (`user`, optional `notes`) and returns the refreshed status.

### Advisory Scanner

```
POST /api/advisory/scan
```

Body (schema `ScanRequest`):

- `action` — policy action (`export.bundle.preview` by default).
- `bundle` — scenes/assets/licenses payload to analyse.
- `override` — request a logged override (still blocked if warnings escalate to `block`).
- `include_debug` — when true, returns `bundle` descriptor and `log_path`.

Response (HTTP 200):

- `allow` — `false` when advisory findings blocked the action or gate not acknowledged.
- `counts` — informational/warning/block totals.
- `findings` — normalized list with `level = info|warn|block`.
- `status` — current gate status.
- `log_path` (optional) — JSONL log for deep dives.

On failure the route raises `HTTP 423` with a `result` payload mirroring the response structure; the caller still receives full advisory findings.

### Studio Bundle Export

The existing route in `comfyvn.server.modules.export_api` continues to handle bundle assembly (`POST /api/export/bundle`). The new status/scanner routes above provide pre-flight checks before invoking the heavy exporter.

## CLI Workflow

`scripts/export_bundle.py` provides a deterministic Studio bundle export:

```
python scripts/export_bundle.py --project demo --timeline main --out build/demo_bundle.zip
```

Exit codes:

- `0` — success (warnings printed to `stderr` when present).
- `2` — blocked due to advisory findings.
- `3` — feature flag disabled (`enable_export_bundle=false`).
- `1` — other errors (project/timeline lookup, policy gate failure).

The CLI emits a JSON payload containing:

- `findings` (`level = info|warn|block`),
- `enforcement` (full `policy_enforcer` snapshot, including counts and `log_path`),
- `provenance` — abbreviated view (`generated_at`, `project`, `timeline`, Ren'Py snippet),
- `gate` — acknowledgement evaluation payload.

## Determinism Notes

- Advisory findings are sorted by `issue_id` (with stable fallbacks) to keep `provenance.json.findings` deterministic.
- Bundle archive contents are written in a fixed order; identical scene/timeline inputs produce identical manifests aside from the timestamp captured by the Ren'Py snapshot (`generated_at`).

## Modder Hooks & Debugging

- `policy_enforcer` emits `on_policy_enforced` for API and CLI runs (payload includes counts, blocked findings, bundle descriptor, and log path).
- The advisory scan API exposes `include_debug` to capture bundle descriptors used for enforcement.
- CLI output exposes `log_path`, enabling tooling to tail enforcement JSONL records.

## Development Notes

- Server route module: `comfyvn/server/routes/advisory.py`
- Feature flag probe: `GET /api/export/bundle/status`
- CLI helper: `scripts/export_bundle.py`

See `docs/dev_notes_advisory_export.md` for contributor-focused implementation notes.
