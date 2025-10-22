# Advisory License Snapshot & Ack Gate

Phase 7 introduces a license/EULA snapshot gate for external model hubs. Every
hub download now flows through a deterministic snapshot + acknowledgement step
so Studio and CLI automation can block risky pulls by default.

## Surface Overview

- **Snapshot helper:** `comfyvn/advisory/license_snapshot.py`
  - Fetches/normalises license text (direct HTTP or caller supplied).
  - Writes `license_snapshot.json` next to the asset (fallback:
    `data/license_snapshots/<slug>/`).
  - Persists source URL, timestamp, SHA-256 hash, metadata, and audit history.
  - Records acknowledgements per user, hash, and provenance payload.
  - Emits `on_asset_meta_updated` modder hooks when snapshots/acks change.
- **API routes:** `comfyvn/server/routes/advisory_license.py`
  - `POST /api/advisory/license/snapshot`
  - `POST /api/advisory/license/ack`
  - `POST /api/advisory/license/require`
  - `GET  /api/advisory/license/{asset_id}`
- **Feature flag:** piggybacks on `features.enable_advisory` (default `false`);
  routes remain available so automation can capture/ack licenses even while the
  rest of the advisory stack stays dark.

## Snapshot Lifecycle

1. Connector resolves the upstream license endpoint or text blob.
2. Call `POST /api/advisory/license/snapshot` with:
   - `asset_id` (stable identifier: `hub:model/version/file` suggested)
   - `asset_path` (local file path or intended destination)
   - `source_url` *or* `text`
   - Optional metadata (`provider`, `version`, `license_id`, etc.)
3. API fetches/normalises text when needed, writes/refreshes
   `<asset_dir>/license_snapshot.json`, and resets per-user acknowledgements if
   the hash changes.
4. Clients present the normalised text to the user and collect a per-hash
   acknowledgement via `POST /api/advisory/license/ack`.
5. Before downloading assets, connectors call `POST /api/advisory/license/require`
   (or `license_snapshot.require_ack(...)`) to enforce the gate.

> When `asset_path` points to a file, the snapshot lands next to it. For staged
> downloads (no local file yet) the helper stores under
> `data/license_snapshots/<asset_id_slug>/license_snapshot.json` and reports the
> absolute path so automation can mirror the file later.

### Snapshot Schema

```json
{
  "asset_id": "hub:civitai:308691:v352812:flux-dev-fp16.safetensors",
  "asset_path": "models/civitai/flux-dev-fp16.safetensors",
  "snapshot_path": "models/civitai/license_snapshot.json",
  "source": {
    "url": "https://civitai.com/api/download/models/352812/license"
  },
  "hash": {
    "algorithm": "sha256",
    "value": "0f9a9e5b7f7a3d6d..."
  },
  "captured_at": "2025-12-22T04:35:11.124216+00:00",
  "text": "... normalised license text ...",
  "metadata": {
    "provider": "civitai",
    "model_id": 308691,
    "version_id": 352812,
    "file": "flux-dev-fp16.safetensors",
    "original_license": "CC-BY-NC-4.0"
  },
  "acknowledgements": [
    {
      "user": "qa.bot",
      "hash": "0f9a9e5b7f7a3d6d...",
      "acknowledged_at": "2025-12-22T04:36:02.558903+00:00",
      "notes": "QA dry-run approval",
      "source_url": "https://civitai.com/api/download/models/352812/license",
      "provenance": {
        "workflow": "qa.p7.license_check",
        "ticket": "P7-142"
      }
    }
  ]
}
```

Acknowledgements are keyed by user; recording a new snapshot hash clears prior
acks to force a re-read when upstream terms change.

## REST API Reference

### `POST /api/advisory/license/snapshot`

Request body (`SnapshotRequest`):

```json
{
  "asset_id": "hub:civitai:308691:v352812:flux-dev-fp16.safetensors",
  "asset_path": "models/civitai/flux-dev-fp16.safetensors",
  "source_url": "https://civitai.com/api/download/models/352812/license",
  "metadata": {
    "provider": "civitai",
    "model_id": 308691,
    "version_id": 352812
  },
  "user": "qa.bot"
}
```

Response (`SnapshotResponse`):

```json
{
  "ok": true,
  "asset_id": "hub:civitai:308691:v352812:flux-dev-fp16.safetensors",
  "hash": "0f9a9e5b7f7a3d6d...",
  "captured_at": "2025-12-22T04:35:11.124216+00:00",
  "snapshot_path": "models/civitai/license_snapshot.json",
  "requires_ack": true,
  "acknowledgements": {},
  "text": "...",
  "source_url": "https://civitai.com/api/download/models/352812/license",
  "metadata": {
    "provider": "civitai",
    "model_id": 308691,
    "version_id": 352812
  }
}
```

### `POST /api/advisory/license/ack`

Request body (`AckRequest`):

```json
{
  "asset_id": "hub:civitai:308691:v352812:flux-dev-fp16.safetensors",
  "user": "qa.bot",
  "notes": "QA dry-run approval",
  "provenance": {
    "workflow": "qa.p7.license_check",
    "ticket": "P7-142"
  }
}
```

Response (`AckResponse`):

```json
{
  "ok": true,
  "asset_id": "hub:civitai:308691:v352812:flux-dev-fp16.safetensors",
  "hash": "0f9a9e5b7f7a3d6d...",
  "requires_ack": false,
  "acknowledgements": {
    "qa.bot": {
      "user": "qa.bot",
      "hash": "0f9a9e5b7f7a3d6d...",
      "acknowledged_at": "2025-12-22T04:36:02.558903+00:00",
      "notes": "QA dry-run approval",
      "source_url": "https://civitai.com/api/download/models/352812/license",
      "provenance": {
        "workflow": "qa.p7.license_check",
        "ticket": "P7-142"
      }
    }
  },
  "snapshot_path": "models/civitai/license_snapshot.json",
  "source_url": "https://civitai.com/api/download/models/352812/license",
  "captured_at": "2025-12-22T04:35:11.124216+00:00"
}
```

### `POST /api/advisory/license/require`

Verifies the acknowledgement before downloads proceed. On failure the route
returns HTTP `423 Locked` with a descriptive error. Successful calls echo the
stored snapshot status.

```json
{
  "ok": true,
  "acknowledged": true,
  "asset_id": "hub:civitai:308691:v352812:flux-dev-fp16.safetensors",
  "hash": "0f9a9e5b7f7a3d6d...",
  "requires_ack": false,
  "acknowledgements": {
    "qa.bot": {
      "...": "..."
    }
  }
}
```

### `GET /api/advisory/license/{asset_id}`

Returns the stored status (optionally including the normalised license text via
`?include_text=true`). Handy for dashboards, CLI scripts, or modder tooling that
needs to display the stored copy without touching the filesystem.

## Modder Hooks & Automation

- `on_asset_meta_updated` fires whenever a snapshot is captured or an
  acknowledgement changes, carrying a payload with:
  - `meta.license_snapshot` → `{hash, captured_at, source_url}`
  - `meta.license_ack` → `{user, hash, acknowledged_at, provenance}`
- Hooks appear in `/api/modder/hooks` and the existing WebSocket topic
  `modder.on_asset_meta_updated`, mirroring asset registry behaviour.
- Settings persisted in `config/config.json` under
  `advisory_licenses.{asset_id}` expose quick summaries for bots without
  reloading huge license blobs.

## CLI & Testing Notes

- Use `python tools/check_current_system.py --profile p7_license_eula_enforcer`
  to verify flag defaults, route wiring, and doc coverage.
- Smoke script snippet:

```bash
curl -X POST http://127.0.0.1:8001/api/advisory/license/snapshot \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"demo:model","text":"Demo License","user":"dev"}'

curl -X POST http://127.0.0.1:8001/api/advisory/license/ack \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"demo:model","user":"dev"}'

curl -X POST http://127.0.0.1:8001/api/advisory/license/require \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"demo:model"}'
```

- Unit coverage is pending; integration harnesses rely on REST flows plus
  `license_snapshot` helpers for future connectors/tests.

## Open Follow-Ups

- Wire Civitai/HF connectors to call `/require` prior to downloading once PAT
  flow is stabilised.
- Add snapshot diffing + notification hook for upstream license changes.
- Extend provenance capture so export manifests embed the acknowledgement hash
  for fully traceable release pipelines.
