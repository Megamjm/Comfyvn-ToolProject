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

### Rebuilding & Enforcing Sidecars

Two complementary CLIs keep the registry in sync with disk:

```bash
python -m comfyvn.registry.rebuild --from-disk --assets-dir assets \\
    --db-path comfyvn/data/comfyvn.db --enforce-sidecars --fix-metadata

python tools/assets_enforcer.py --dry-run --json
```

- `--enforce-sidecars` regenerates missing sidecars after the rebuild pass.
- `--fix-metadata` derives fallback tags/licences from folder structure when data is
  missing.
- `--overwrite-sidecars` forces a rewrite even when files already exist.
- `--metadata-report` / `--json` emit machine-readable reports for CI pipelines.

The shared `audit_sidecars()` helper powers both commands, so automation scripts and
developers see consistent results.

### Bulk Editing & Gallery Panel

- Open **Panels → Asset Gallery** to filter by type/tag/licence, multi-select assets,
  and apply tag or licence updates in bulk.
- Use **Copy Debug JSON** to capture the full registry payload for the current
  selection (handy when sharing repros or crafting mod metadata).
- The panel listens to registry hook events; external scripts that touch metadata or
  sidecars will appear without manual refreshes.

### Future Enhancements

- Provenance drill-down and “open in file manager” shortcuts inside the gallery.
- Richer preview widgets (animated thumbnails, waveform previews for more formats).
- Import adapters that annotate assets with bespoke metadata during bulk ingestion.

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

### API Hooks for Modders & Tooling

- REST endpoints under `/assets` expose registry operations:
  - `GET /assets?type=<kind>` → list registered assets (returns provenance-rich metadata).
  - `GET /assets/{uid}` → fetch a single asset record; `GET /assets/{uid}/download` streams the file.
  - `POST /assets/upload` (requires `python-multipart`) → upload new files with JSON metadata; provenance is recorded automatically.
- Scriptable helper:
  ```python
  from comfyvn.studio.core import AssetRegistry

  registry = AssetRegistry()
  snapshot = registry.list_assets("backgrounds")
  registry.register_file("tmp/city.png", "backgrounds", metadata={"source": "modkit"})
  ```
- Registry hooks: `registry.add_hook(event, callback)` supports
  `asset_registered`, `asset_meta_updated`, `asset_removed`, and
  `asset_sidecar_written`. Pair with `bulk_update_tags()` to orchestrate metadata
  migrations programmatically—the hook bus ensures sidecars stay in sync.
- To inspect thumbnails or regenerate previews, call
  `AssetRegistry.resolve_thumbnail_path(uid)` and the rebuild/enforcer utilities
  above.
- Modders can bundle debug dumps by serialising `registry.list_assets()` alongside sidecars; each entry includes the hash, thumbs, and provenance pointers for external tools.
