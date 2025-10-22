# Cloud Sync & Secrets Vault Notes

Updated: 2025-11-18 • Scope: Cloud manifests, S3/Drive transports, encrypted vault

## Feature Flags

- `features.enable_cloud_sync` gates the `/api/sync/*` surface.
- `features.enable_cloud_sync_s3` and `features.enable_cloud_sync_gdrive` toggle individual providers.
- Flags live in `config/comfyvn.json` (all default to `false`). Use your preferred editor or invoke the feature flag helper script to flip them locally.

## Secrets Vault

- Location: `config/comfyvn.secrets.json` (git-ignored).
- Encryption: AES-GCM (256-bit) with PBKDF2-HMAC-SHA256 (390k iterations). The envelope retains up to five encrypted backups inline whenever content changes.
- Unlock by exporting `COMFYVN_SECRETS_KEY="<passphrase>"` before starting the server. Tests/scripts can pass `passphrase=` directly to the helper.
- Example payload:
  ```jsonc
  {
    "cloud_sync": {
      "s3": {
        "bucket": "studio-nightly",
        "prefix": "dev",
        "region": "us-east-1",
        "aws_access_key_id": "...",
        "aws_secret_access_key": "..."
      },
      "gdrive": {
        "parent_id": "<drive-folder>",
        "manifest_parent_id": "<manifest-folder>",
        "credentials": { /* service account JSON */ }
      }
    }
  }
  ```
- Rotating secrets:
  ```python
  from comfyvn.sync.cloud import SecretsVault

  vault = SecretsVault()
  secrets = vault.unlock(passphrase="...")
  secrets["cloud_sync"]["s3"]["prefix"] = "prod"
  vault.store(secrets, passphrase="...")
  ```
- Vault backups are embedded in the same JSON file under `"backups"`. The newest backup is index 0; copy an entry back to the root to restore an older ciphertext before re-encrypting.

## REST API

- `GET /api/sync/manifest` — returns the current manifest summary (name, root, entries, checksum) for the requested snapshot. Accepts optional `include`, `exclude`, and `follow_symlinks` query parameters.
- `POST /api/sync/dry_run`
  ```bash
  curl -X POST "$BASE_URL/api/sync/dry_run" \
    -H 'Content-Type: application/json' \
    -d '{
      "service": "s3",
      "snapshot": "nightly",
      "paths": ["assets", "config"],
      "credentials_key": "cloud_sync.s3",
      "service_config": {"bucket": "studio-nightly", "prefix": "dev"}
    }'
  ```
  - Returns `{manifest, plan, summary, remote_manifest}`. `summary.status` is `"dry_run"`, `summary.errors` is always an empty list, and the modder hook `on_cloud_sync_plan` fires after the response is assembled.
  - Remote fetch failures fall back to cached manifests; missing SDKs yield a stub summary instead of raising.
- `POST /api/sync/run`
  ```bash
  curl -X POST "$BASE_URL/api/sync/run" \
    -H 'Content-Type: application/json' \
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
  - Applies the plan. Adapter loops continue after per-file errors, aggregate them into `summary.errors`, and only publish the refreshed manifest/upload when no failures occurred. Runs report `summary.status: "ok"` or `"partial"`.
  - `commit_manifest=false` skips writing the local cache when you need to review results first.
- `POST /api/backup/create`
  ```bash
  curl -X POST "$BASE_URL/api/backup/create" \
    -H 'Content-Type: application/json' \
    -d '{"label": "pre-release", "max_backups": 10}'
  ```
  - Writes a ZIP archive under `backups/cloud/`, embeds the manifest in `__meta__/cloud_sync/manifest.json`, and enforces rotation. The response echoes `{name, path, files, bytes, checksum, removed}`.
- `POST /api/backup/restore`
  ```bash
  curl -X POST "$BASE_URL/api/backup/restore" \
    -H 'Content-Type: application/json' \
    -d '{"name": "20251215T080530Z-pre-release.zip", "replace_existing": false}'
  ```
  - Restores files relative to the workspace, skipping metadata entries and refusing to extract outside the root. The response returns `{name, restored, skipped}`.

## Modder Hooks & Logs

- `on_cloud_sync_plan` — emitted after dry-runs with `{service, snapshot, uploads, deletes, bytes}`.
- `on_cloud_sync_complete` — emitted after runs with `{service, snapshot, uploads, deletes, skipped, status}`. `status` mirrors `summary.status` (`ok` or `partial`).
- Subscribe via REST (`/api/modder/hooks`) or WebSocket (`/api/modder/hooks/ws`).
- Structured logs (`sync.dry_run`, `sync.run`, `backup.create`, `backup.restore`) appear in `logs/server.log` with provider/paths/counts. Secrets never enter the log stream; errors redact remote payloads down to message strings.

## Provider SDKs

- S3 uploads rely on `boto3`/`botocore`. Install via `pip install boto3` if you plan to run syncs. Dry-runs fall back to the cached manifest when the SDK is missing.
- Google Drive uploads rely on `google-api-python-client` and `google-auth`. Service accounts are recommended; drop the JSON under `cloud_sync.gdrive.credentials` in the vault.

## Manifest Internals

- Shared helpers live in `comfyvn/sync/cloud/manifest.py` — each entry records `path`, `size`, `mtime`, and `sha256`.
- Local cache directory: `cache/cloud/manifests/<service>/<snapshot>.json` (includes a checksum for corruption detection).
- Delta planning is handled by `diff_manifests(...)`, which flags uploads when hashes differ and deletes when local entries disappear.

## Tests & Tooling

- `pytest tests/test_cloud_sync.py` covers manifest diffing and vault rotation semantics.
- When provider SDKs are installed, add an integration smoke test that seeds the vault, calls `/api/sync/dry_run`, and asserts hook emission/counts before enabling CI automation.

## Debug & Verification Checklist

- [ ] **Docs updated** — README Cloud Sync section, `docs/CLOUD_SYNC.md`, `docs/BACKUPS.md`, `architecture.md`, `architecture_updates.md`, this note.
- [ ] **Feature flags** — `config/comfyvn.json` stores `enable_cloud_sync*` (default `false`).
- [ ] **API surfaces** — `/api/sync/manifest`, `/api/sync/dry_run`, `/api/sync/run`, `/api/backup/{create,restore}` documented with curl samples.
- [ ] **Modder hooks** — `on_cloud_sync_plan`, `on_cloud_sync_complete` payloads (including `status`) documented.
- [ ] **Logs** — `logs/server.log` entries `sync.dry_run`, `sync.run`, `backup.create`, `backup.restore`; manifests cached under `cache/cloud/manifests/`.
- [ ] **Provenance** — manifests record hashes/timestamps; reruns remain idempotent once remote and local digests match.
- [ ] **Determinism** — identical manifests + provider state → zero uploads on the next dry-run.
- [ ] **Windows/Linux** — manifest builder relies on pathlib; no platform-specific logic.
- [ ] **Security** — secrets sourced exclusively from the encrypted vault; backups stay in the same encrypted envelope.
- [ ] **Dry-run mode** — dry-run endpoint performs read-only planning even when provider SDKs are missing.
