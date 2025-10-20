## ComfyVN Studio Asset Workflow

### Registry Overview

- Assets live under `data/assets/` (per type directories).
- Sidecar metadata is written to `data/assets/_meta/<asset>.json`.
- Thumbnails (when Pillow is available) are stored in `cache/thumbs/` and referenced in the registry.

### Registering an Asset

```python
from comfyvn.studio.core import AssetRegistry

registry = AssetRegistry()
info = registry.register_file("/path/to/image.png", "characters")
print(info)
```

The helper performs the following actions:
1. Copies the source file into the project assets directory (unless `copy=False`).
2. Computes a SHA-256 hash to derive a stable asset `uid`.
3. Writes/updates the `assets_registry` table with the file metadata and byte size.
4. Records a provenance row (`provenance` table) capturing the source workflow, inputs, and commit hash.
5. Generates a sidecar JSON payload describing the asset, including the provenance entry.
6. Attempts to build a thumbnail (requires Pillow; otherwise skipped with a log message).
7. When Pillow is available and the asset is a PNG, embeds a `comfyvn_provenance` marker directly into the image metadata for downstream tooling.

### Future Enhancements

- Thumbnail worker to process assets asynchronously.
- Audio/voice assets: embed provenance markers in sidecars & waveform headers.
- CLI command to batch-import assets and rebuild thumbnails.

### Debugging Tips

- Sidecars live under `data/assets/_meta/<asset>.json` and now include a `provenance` object (`id`, `source`, `workflow_hash`, inputs).
- Provenance ledger rows can be inspected via SQLite:
  ```bash
  sqlite3 comfyvn/data/comfyvn.db "
    SELECT p.id, a.uid, p.source, p.workflow_hash, p.created_at
    FROM provenance p JOIN assets_registry a ON a.id = p.asset_id
    ORDER BY p.id DESC LIMIT 10;
  "
  ```
- Use `identify -verbose <image>` (ImageMagick) or reopen the asset in Pillow to confirm the `comfyvn_provenance` PNG text chunk is present.
