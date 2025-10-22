# Local Backups & Restore

Cloud sync ships with a lightweight backup manager that creates timestamped archives of critical project folders before pushing to remote storage. Archives are stored locally under `backups/cloud/` and never leave disk unless you upload them manually.

## Defaults

- **Include paths:** `data`, `data/scenes`, `assets`, `config`. Supply a custom `include` list when calling the API to add or replace directories.
- **Exclude patterns:** inherits the manifest defaults (cache/log/tmp folders, Python bytecode, `.git`, `.venv`, etc.). Append additional globs via the request payload.
- **Rotation:** keeps the most recent five archives by default. Override per request with `max_backups` (1–50).
- **Metadata:** each archive contains `__meta__/cloud_sync/manifest.json` with the manifest snapshot, include/exclude lists, and checksum.

## API

### `POST /api/backup/create`

```bash
curl -X POST "$BASE_URL/api/backup/create" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "pre-release",
    "include": ["assets", "config", "data/scenes"],
    "exclude": ["assets/cache/*"],
    "max_backups": 10
  }'
```

Response:

```jsonc
{
  "backup": {
    "name": "20251215T080530Z-pre-release.zip",
    "path": "backups/cloud/20251215T080530Z-pre-release.zip",
    "files": 142,
    "bytes": 185602344,
    "checksum": "...",
    "removed": ["20251130T210400Z.zip"]
  }
}
```

- Archives are ZIP files with POSIX-style paths; symlinks are ignored.
- Rotation is enforced immediately after the archive is written.

### `POST /api/backup/restore`

```bash
curl -X POST "$BASE_URL/api/backup/restore" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "20251215T080530Z-pre-release.zip",
    "replace_existing": false
  }'
```

The response reports counts for restored and skipped files. Set `"replace_existing": true` to overwrite local files.

- Extraction is sandboxed to the workspace: attempting to restore paths outside the project root raises an error.
- Entries under `__meta__/` are skipped automatically; use them for inspection only.

## Operational Checklist

- Create a backup before toggling `enable_cloud_sync*` flags or rotating remote credentials.
- Keep archives under version control ignores (`backups/` remains local by default).
- Monitor `logs/server.log` for `backup.create`/`backup.restore` structured entries when running in automation.
- Pair backups with manifest dry-runs to ensure the archive matches the planned sync state.

