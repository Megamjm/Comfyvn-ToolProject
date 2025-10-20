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
4. Generates a sidecar JSON payload describing the asset and its provenance hooks.
5. Attempts to build a thumbnail (requires Pillow; otherwise skipped with a log message).

### Future Enhancements

- Thumbnail worker to process assets asynchronously.
- Provenance writer to connect registry entries with metadata stamps.
- CLI command to batch-import assets and rebuild thumbnails.
