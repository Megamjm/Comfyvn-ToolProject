## ComfyVN Studio Asset Workflow

### Registry Overview

- Assets live under `assets/` by default (per-type subdirectories). The location can be overridden via `COMFYVN_ASSETS_ROOT`.
- Sidecar metadata is written alongside each asset as `<filename>.asset.json` and mirrored to `assets/_meta/<asset>.json` for legacy tooling.
- Thumbnails (and waveform previews for WAV audio) are written to the thumbnail cache (defaults to `cache/thumbs/`) and referenced in the registry.

### Registering an Asset

```python
from comfyvn.studio.core import AssetRegistry

registry = AssetRegistry()
info = registry.register_file("/path/to/image.png", "characters")
print(info)
```

The helper performs the following actions:
1. Copies the source file into the project assets directory (set `copy_file=false` or legacy `copy=false` to skip copying).
2. Computes a SHA-256 hash to derive a stable asset `uid`.
3. Writes/updates the `assets_registry` table with the file metadata and byte size.
4. Records a provenance row (`provenance` table) capturing the source workflow, inputs, and commit hash.
5. Generates a sidecar JSON payload describing the asset (including provenance and preview metadata).
6. Attempts to build a thumbnail for images (requires Pillow) or a lightweight waveform preview for WAV audio files.
7. When Pillow is available and the asset is a PNG, embeds a `comfyvn_provenance` marker directly into the image metadata for downstream tooling.

### Rebuilding the Registry

Use the CLI helper to re-index everything under `assets/`, regenerate sidecars, and refresh previews:

```bash
python tools/rebuild_asset_registry.py --assets-dir assets --db-path comfyvn/data/comfyvn.db
```

Pass `--verbose` to inspect individual registrations. The utility also removes stale database rows for files that no longer exist on disk.

### Future Enhancements

- Background worker service to process thumbnails outside the main thread.
- Broader audio support (MP3/OGG waveform snapshots) when optional dependencies are available.
- Import adapters that annotate assets with richer metadata during bulk ingestion.

### Debugging Tips

- Sidecars live beside each asset (`<name>.asset.json`) and include a `provenance` object (`id`, `source`, `workflow_hash`, inputs).
- Provenance ledger rows can be inspected via SQLite:
  ```bash
  sqlite3 comfyvn/data/comfyvn.db "
    SELECT p.id, a.uid, p.source, p.workflow_hash, p.created_at
    FROM provenance p JOIN assets_registry a ON a.id = p.asset_id
    ORDER BY p.id DESC LIMIT 10;
  "
  ```
- Use `identify -verbose <image>` (ImageMagick) or reopen the asset in Pillow to confirm the `comfyvn_provenance` PNG text chunk is present.
