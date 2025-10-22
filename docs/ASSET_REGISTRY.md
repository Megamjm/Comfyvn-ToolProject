# Asset Registry & Gallery

The asset registry is responsible for indexing files under `data/assets`, keeping
sidecar metadata in sync, and feeding the Studio gallery dock. This document
captures the supported workflows, REST endpoints, and debug hooks modders can
lean on when extending or auditing the system.

> Feature flag: `features.enable_asset_gallery` (defaults to `false`). The panel
> can be toggled under **Settings → Debug & Feature Flags** without restarting
> the server.

## Studio Gallery

- Open the **Asset Gallery** dock to browse thumbnails, sort by type, and select
  multiple assets for bulk actions.
- Filters cover **Type**, **Tag**, and **License**. A new search box performs a
dumb substring scan over the asset UID, relative path, and textual metadata so
designers can quickly surface related entries.
- Bulk edits let you add or remove tags and apply or clear a license in a single
pass. Changes persist back to the registry and sidecar files, and the dock
reloads automatically thanks to live registry hooks.
- Debug helpers include `Copy Debug JSON`, which copies the selected registry
records (including metadata) to the clipboard for quick sharing.

## REST API Surface

All routes live under `/api/assets/*` through the FastAPI server. They mirror
the local registry helpers and are safe to call from automation scripts, CI
pipelines, or external tooling.

### `GET /api/assets/search`

Query parameters:

- `type` – optional asset type/folder filter.
- `tags`/`tag` – repeated or comma-separated tag filters (all must match).
- `license` – exact match against the stored license string.
- `text` – case-insensitive substring search across the asset path and metadata.
- `limit` – cap the number of rows returned (1-500).
- `include_debug` – add registry diagnostics to the response.

Response payload:

```json5
{
  "ok": true,
  "total": 12,
  "items": [
    {
      "uid": "5bf9e7ba3f9a42a3",
      "type": "images",
      "path": "images/cyberpunk/runner.png",
      "meta": {
        "tags": ["cyberpunk", "runner"],
        "license": "cc-by-4.0",
        "title": "Runner Promo"
      },
      "thumb": "5bf9e7ba3f9a42a3.png"
    }
  ],
  "filters": {
    "type": "images",
    "tags": ["cyberpunk"],
    "license": "cc-by-4.0",
    "text": "runner",
    "limit": 50
  },
  "debug": {
    "hooks": {
      "asset_registered": ["<bound method AssetGalleryPanel...>"]
    },
    "assets_root": "/abs/path/to/data/assets",
    "thumb_root": "/abs/path/to/cache/thumbs",
    "project_id": "default"
  }
}
```

The `debug` block enumerates currently bound registry hooks (stringified for
safety) so contributors can confirm which listeners are active without looking
inside the process.

### `POST /api/assets/enforce`

Request body:

```json5
{
  "fix_missing": true,
  "overwrite": false,
  "fill_metadata": true
}
```

When `fix_missing` is enabled the call generates any missing sidecars and may
re-write metadata. `fill_metadata` back-fills missing tags/licence fields based
on folder heuristics, while `overwrite` forces a fresh write even if a sidecar
already exists. The response mirrors the `SidecarReport` structure, listing IDs
that were created, repaired, or still require manual attention.

### `POST /api/assets/rebuild`

Request body (all fields optional):

```json5
{
  "assets_root": "data/assets",
  "db_path": "config/comfyvn.sqlite",
  "thumbs_root": "cache/thumbs",
  "project_id": "default",
  "remove_stale": true,
  "wait_for_thumbs": true
}
```

The rebuild scans the provided assets directory, computes SHA-256 digests,
refreshes the SQLite registry, and queues preview generation. `remove_stale`
prunes records whose files vanished from disk, while `wait_for_thumbs` blocks
until queued thumbnail jobs finish so downstream consumers always see a
consistent cache. The response includes the processed/skipped/removed counters
plus the resolved root paths.

## Sidecars, Metadata, and Hooks

- Sidecars use the `.asset.json` suffix and sit beside each asset. They store
  metadata (`tags`, `license`, `origin`, `workflow`) alongside preview pointers.
- `audit_sidecars` (exposed via the enforcer route) reports missing sidecars and
  metadata gaps. When repair flags are passed the helper rewrites both the
  registry record and the on-disk sidecar.
- Asset events emit through the modder hook bus:
  - `asset_registered`
  - `asset_meta_updated`
  - `asset_removed`
  - `asset_sidecar_written`
- Scripts can subscribe via `comfyvn.core.modder_hooks.emit(...)` or query the
  current bindings by calling `GET /api/assets/search?include_debug=true`.

## Validation & Troubleshooting

- Quick smoke test: `python tools/check_current_system.py --profile p5_assets_gallery --base http://127.0.0.1:8001`
- Ensure thumbnails persist across platforms by verifying `_REGISTRY.THUMB_ROOT`
  resolves to `cache/thumbs` on repo checkouts and the user cache directory in
  runtime environments.
- Use the enforcer route before releases to guarantee zero missing sidecars and
  consistent licence coverage.
- Re-run the rebuild when importing external assets, bulk renaming folders, or
  migrating the project to a new machine.
