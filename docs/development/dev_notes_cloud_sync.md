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

- `POST /api/sync/dry-run`
  ```bash
  curl -X POST "$BASE_URL/api/sync/dry-run" \
    -H 'Content-Type: application/json' \
    -d '{
      "service": "s3",
      "snapshot": "nightly",
      "paths": ["assets", "config"],
      "credentials_key": "cloud_sync.s3",
      "service_config": {"bucket": "studio-nightly", "prefix": "dev"}
    }'
  ```
  Response excerpt:
  ```jsonc
  {
    "plan": {"service": "s3", "snapshot": "nightly", "uploads": [...], "deletes": [...]},
    "manifest": {"name": "nightly", "entries": 128, "created_at": "..."},
    "summary": {"uploads": [...], "deletes": [], "skipped": [...]}
  }
  ```
  - Remote manifests are fetched read-only. If the provider SDK is unavailable the planner falls back to cached manifests and still returns the delta summary.
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
  - Applies the plan, uploads the refreshed manifest to the provider, and saves the manifest locally under `cache/cloud/manifests/<service>/<snapshot>.json` (unless `commit_manifest=false`).
  - Summary payload mirrors the counts returned by the adapter (`uploads`, `deletes`, `skipped`).

## Modder Hooks & Logs

- `on_cloud_sync_plan` — emitted after dry-runs with `{service, snapshot, uploads, deletes, bytes}`.
- `on_cloud_sync_complete` — emitted after successful runs with `{service, snapshot, uploads, deletes, skipped}`.
- Subscribe via REST (`/api/modder/hooks`) or WebSocket (`/api/modder/hooks/ws`).
- Structured logs (`sync.dry_run`, `sync.run`) appear in `logs/server.log` with provider, snapshot, and counts; secrets never enter the log stream.

## Provider SDKs

- S3 uploads rely on `boto3`/`botocore`. Install via `pip install boto3` if you plan to run syncs. Dry-runs fall back to the cached manifest when the SDK is missing.
- Google Drive uploads rely on `google-api-python-client` and `google-auth`. Service accounts are recommended; drop the JSON under `cloud_sync.gdrive.credentials` in the vault.

## Manifest Internals

- Shared helpers live in `comfyvn/sync/cloud/manifest.py` — each entry records `path`, `size`, `mtime`, and `sha256`.
- Local cache directory: `cache/cloud/manifests/<service>/<snapshot>.json` (includes a checksum for corruption detection).
- Delta planning is handled by `diff_manifests(...)`, which flags uploads when hashes differ and deletes when local entries disappear.

## Tests & Tooling

- `pytest tests/test_cloud_sync.py` covers manifest diffing and vault rotation semantics.
- When provider SDKs are installed, add an integration smoke test that seeds the vault, calls `/api/sync/dry-run`, and asserts hook emission/counts before enabling CI automation.

## Debug & Verification Checklist

- [ ] **Docs updated** — README Cloud Sync section, `architecture.md`, `architecture_updates.md`, this note.
- [ ] **Feature flags** — `config/comfyvn.json` stores `enable_cloud_sync*` (default `false`).
- [ ] **API surfaces** — `/api/sync/dry-run`, `/api/sync/run` documented with curl samples.
- [ ] **Modder hooks** — `on_cloud_sync_plan`, `on_cloud_sync_complete` payloads documented.
- [ ] **Logs** — `logs/server.log` entries `sync.dry_run` / `sync.run`; manifests cached under `cache/cloud/manifests/`.
- [ ] **Provenance** — manifests record hashes/timestamps; reruns remain idempotent once remote and local digests match.
- [ ] **Determinism** — identical manifests + provider state → zero uploads on the next dry-run.
- [ ] **Windows/Linux** — manifest builder relies on pathlib; no platform-specific logic.
- [ ] **Security** — secrets sourced exclusively from the encrypted vault; backups stay in the same encrypted envelope.
- [ ] **Dry-run mode** — dry-run endpoint performs read-only planning even when provider SDKs are missing.
