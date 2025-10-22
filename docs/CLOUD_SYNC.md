# Cloud Sync Overview

Cloud sync keeps project assets mirrored to external storage (Amazon S3 or Google Drive) using deterministic manifests and resumable delta plans. The feature is gated by `features.enable_cloud_sync` plus provider-specific flags (`features.enable_cloud_sync_s3`, `features.enable_cloud_sync_gdrive`). All default to **false** so deployments must opt in explicitly.

## Architecture

- **Manifest builder** — `comfyvn/sync/cloud/manifest.py` walks configured include paths, filters out known cache/log/tmp folders, and records `{path, size, mtime, sha256}` per entry. Defaults come from `config/comfyvn.json → sync` (`include`, `exclude`, `snapshot_prefix`, `default_root`).
- **Manifest cache** — persisted to `cache/cloud/manifests/<service>/<snapshot>.json`, letting dry-runs compute deltas even if the remote manifest fetch fails.
- **Secrets vault** — `config/comfyvn.secrets.json` stores provider credentials in an AES-GCM envelope managed by `comfyvn.sync.cloud.SecretsVault`. Unlock by exporting `COMFYVN_SECRETS_KEY=<passphrase>` before running the backend. Each write keeps up to five encrypted backups inline; the format is versioned and validated on load.
- **Provider adapters** — `comfyvn/sync/cloud/s3.py` (Amazon S3 via `boto3`) and `comfyvn/sync/cloud/gdrive.py` (Drive v3 with a service account). Both implement dry-run summaries, resumable run execution, per-operation error tracking, and upload the refreshed manifest only when no failures occurred.
- **FastAPI surface** — `comfyvn/server/routes/sync_cloud.py` exposes `/api/sync/manifest`, `/api/sync/dry_run`, `/api/sync/run`, plus `/api/backup/{create,restore}` for local archive rotation. Modder hooks `on_cloud_sync_plan` and `on_cloud_sync_complete` broadcast plan/run telemetry to tooling.

```
                 ┌────────────────────┐            ┌─────────────────┐
   include/exclude config ──▶ Manifest builder ──▶ │ Manifest cache  │
                 └─────▲──────────────┘            └───────▲─────────┘
                       │                                    │
                       │                                    │
        SecretsVault ──┴─────▶ Provider config ──▶ Provider clients ─┐
                                                                     │
                   /api/sync/{manifest,dry_run,run}                  │
                                                                     ▼
                                                  Remote bucket / Drive folder
```

## API Reference

### `GET /api/sync/manifest`

Generates the current manifest without touching remote storage.

```bash
curl "$BASE_URL/api/sync/manifest?snapshot=nightly&include=assets,config"
```

Response:

```jsonc
{
  "manifest": {"name": "nightly", "root": "/abs/workspace", "created_at": "...", "entries": 214, "checksum": "..."},
  "include": ["assets", "config"],
  "exclude": ["cache", "cache/*", "logs", "logs/*", "tmp", "tmp/*", ...],
  "checksum": "..."
}
```

### `POST /api/sync/dry_run`

Computes the delta plan and returns provider summaries without issuing writes. Works even when the provider SDK is missing; the adapter falls back to cached manifests.

```bash
curl -X POST "$BASE_URL/api/sync/dry_run" \
  -H "Content-Type: application/json" \
  -d '{
    "service": "s3",
    "snapshot": "nightly",
    "paths": ["assets", "config"],
    "credentials_key": "cloud_sync.s3",
    "service_config": {
      "bucket": "studio-nightly",
      "prefix": "dev"
    }
  }'
```

Returns `{manifest, plan, summary, remote_manifest}`. `summary.status` is always `"dry_run"`, and uploads/deletes/skipped entries are expanded as dictionaries for downstream tooling. The modder hook `on_cloud_sync_plan` fires with `{service, snapshot, uploads, deletes, bytes}`.

### `POST /api/sync/run`

Applies the plan. The provider client continues after individual upload/delete errors, aggregates them, and only uploads the refreshed manifest when every operation succeeds. Failures surface as `summary.status: "partial"` with an `errors` array (`{action, path, error}`).

```bash
curl -X POST "$BASE_URL/api/sync/run" \
  -H "Content-Type: application/json" \
  -d '{
    "service": "gdrive",
    "snapshot": "milestone-12",
    "credentials_key": "cloud_sync.gdrive",
    "service_config": {
      "parent_id": "<drive-folder>",
      "manifest_parent_id": "<manifest-folder>"
    }
  }'
```

Successful runs emit `on_cloud_sync_complete` including counts and summary status. Set `"commit_manifest": false` when you need to inspect the result before updating the local cache.

## Provider Configuration

### Amazon S3 (`service: "s3"`)

- Create an IAM user/role with the minimal policy:

```jsonc
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::<bucket>"},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": "arn:aws:s3:::<bucket>/<prefix>/*"}
  ]
}
```
- Store credentials under `cloud_sync.s3` in the secrets vault and opt into the feature flags.
- Optional fields: `region`, `profile`, `endpoint_url`, `aws_session_token`.

### Google Drive (`service: "gdrive"`)

- Use a service account with Drive API access and share the target folders with the service account address.
- Store credentials JSON under `cloud_sync.gdrive.credentials`.
- Required config keys: `parent_id` (file storage folder) and `manifest_parent_id` (manifest folder). `scopes` defaults to `https://www.googleapis.com/auth/drive.file`.

## Local Backups

Use `/api/backup/create` and `/api/backup/restore` to manage on-disk archives under `backups/cloud/`.

```bash
# Create an archive with default paths (data, data/scenes, assets, config)
curl -X POST "$BASE_URL/api/backup/create" \
  -H "Content-Type: application/json" \
  -d '{"label": "pre-cloud-sync", "max_backups": 7}'

# Restore the most recent archive without overwriting existing files
curl -X POST "$BASE_URL/api/backup/restore" \
  -H "Content-Type: application/json" \
  -d '{"name": "20251215T080530Z-pre-cloud-sync.zip", "replace_existing": false}'
```

Archives embed a manifest in `__meta__/cloud_sync/manifest.json` and honour rotation limits (`max_backups` defaults to 5).

## Debug & Verification

- Flags remain OFF by default: confirm `enable_cloud_sync`, `enable_cloud_sync_s3`, and `enable_cloud_sync_gdrive` stay false in `config/comfyvn.json`.
- Logs: structured entries (`sync.dry_run`, `sync.run`, `backup.create`, `backup.restore`) land in `logs/server.log`. Secrets are never written to logs.
- Hooks: subscribe to `/api/modder/hooks` or the WebSocket variant to observe `on_cloud_sync_plan` and `on_cloud_sync_complete`.
- Smoke check: `python tools/check_current_system.py --profile p4_cloud_sync --base http://127.0.0.1:8001` verifies flags, routes, and docs (`README.md`, `docs/CLOUD_SYNC.md`, `docs/BACKUPS.md`, `CHANGELOG.md`).

## Automation Tips

- Call `GET /api/sync/manifest` in CI to confirm the local manifest and checksum after significant asset changes.
- Use dry-run summaries to gate deploy pipelines (e.g., fail builds when uploads exceed expected thresholds).
- When S3/GDrive SDKs are absent on a build agent, dry-runs still produce actionable plans thanks to cached manifests.
- Secrets Vault helpers (`comfyvn.sync.cloud.SecretsVault`) expose `unlock`, `store`, `get`, and `set` for programmatic updates; never commit plaintext credentials.

