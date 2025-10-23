# P5 Advisory & Studio Bundle Export

This document captures the liability gate, advisory scanning, and Studio bundle export flow introduced for the P5 milestone.

## Feature Flags

- `features.enable_advisory` (default: `false`) — exposes the advisory scan API and enforcement surface.
- `features.enable_export_bundle` (default: `false`) — unlocks the Studio bundle exporter (API and CLI).

Enable both flags in `comfyvn.json` before exposing the workflow to contributors.

## Advisory Disclaimer Workflow

1. Operator reads `GET /api/advisory/disclaimer` to surface the current disclaimer text, acknowledgement status, and policy links.
2. `POST /api/advisory/ack` records the acknowledgement (user, optional display name, optional notes) and mirrors it into persisted settings + provenance logs.
3. Advisory scanning always runs via `policy_enforcer`, even if the disclaimer is pending, so teams can review findings before sharing outputs or assets.

The workflow now warns instead of blocking. Automation should continue to surface warnings prominently and request human sign-off on blocker-level findings, but REST APIs and the CLI will not raise HTTP 423 when the disclaimer is outstanding.

## API Surface

### Bundle Status

```
GET /api/export/bundle/status
```

Payload:

- `enabled` — `true` when `enable_export_bundle` flag is on.
- `gate` — latest evaluation for the supplied action (defaults to `export.bundle`).
- `status` — persisted acknowledgement state (`ack_disclaimer_v1`, timestamp, override toggle).
- `disclaimer` — helper metadata (message, version, links) mirroring `policy_gate.evaluate_action`.

### Advisory Disclaimer

```
GET /api/advisory/disclaimer
POST /api/advisory/ack
```

- `GET` returns the disclaimer text, acknowledgement metadata, and quick links to policy docs.
- `POST` stores the acknowledgement (`user`, optional `name` + `notes`) and returns the refreshed payload.

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

- `acknowledged` — current disclaimer status.
- `disclaimer` — helper object with message, version, links, and acknowledgement flag.
- `counts` — totals grouped by `license`, `sfw`, and `unknown` categories.
- `findings` — normalized list with `{category, severity, message, target, detail}` entries.
- `gate` — latest policy evaluation snapshot (`requires_ack` remains `true` while the disclaimer is pending).
- `log_path` (optional) — JSONL log for deep dives.

The route no longer raises HTTP 423. Downstream tools should inspect `findings` and `counts` to decide whether human review is required.

### Studio Bundle Export

The existing route in `comfyvn.server.modules/export_api` continues to handle bundle assembly (`POST /api/export/bundle`). A public mirror now lives at `POST /export/bundle` (`comfyvn/server/routes/export_public.py`), defaulting bundles to `exports/bundles/<project>_<timeline>_<timestamp>.zip` and returning provenance paths plus asset validation counts. The status/scanner routes above provide pre-flight checks before invoking the heavy exporter.

## CLI Workflow

`scripts/export_bundle.py` provides a deterministic Studio bundle export:

```
python scripts/export_bundle.py --project demo --timeline main --out build/demo_bundle.zip
```

Exit codes:

- `0` — success (warnings and blocker summaries printed to `stderr` when present).
- `3` — feature flag disabled (`enable_export_bundle=false`).
- `1` — other errors (project/timeline lookup, filesystem issues).

The CLI emits a JSON payload containing:

- `findings` (each entry includes `category`, `severity`, `message`, `detail`, `target`),
- `enforcement` (full `policy_enforcer` snapshot, including counts and `log_path`),
- `provenance` — abbreviated view (`generated_at`, `project`, `timeline`, Ren'Py snippet),
- `gate` — acknowledgement evaluation payload (now always `allow=true`),
- `disclaimer` — helper object mirroring the REST acknowledgement payload.

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
