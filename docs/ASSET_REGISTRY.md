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
pipelines, or external tooling. Assets are deduplicated by the SHA-256 hash of
their file contents, so repeated registrations of the same file return the
original asset ID while merging metadata (tags, license, origin, provenance).

### `POST /api/assets/register`

Register an existing file on disk or copy it into the managed assets folder.

Request body:

```json5
{
  "path": "/absolute/or/relative/path/to/image.png",
  "asset_type": "images",
  "dest_path": "images/gallery/image.png",
  "metadata": {
    "tags": ["gallery", "promo"],
    "license": "CC-BY-4.0",
    "origin": "studio-script"
  },
  "copy": true
}
```

- `path` can be absolute or relative to the current working directory.
- `asset_type` controls the default destination bucket if `dest_path` is omitted.
- `dest_path`, when present, must be relative to the asset root and can point to
  a folder (the filename will be appended) or an explicit file.
- `metadata` accepts either an object or a JSON string; tags are normalised, and
  the first registration defaults the metadata version to `1`.
- `copy` of `false` registers the file in-place (it must already live under the
  asset root).

Response payload:

```json5
{
  "ok": true,
  "asset_id": "7bc457a63d7d82ba",
  "asset": {
    "id": "7bc457a63d7d82ba",
    "type": "images",
    "path": "images/gallery/image.png",
    "hash": "7bc457a63d7d82bafe18302d0f10d646...",
    "bytes": 42355,
    "tags": ["gallery", "promo"],
    "license": "CC-BY-4.0",
    "origin": "studio-script",
    "version": 1,
    "metadata": {
      "tags": ["gallery", "promo"],
      "license": "CC-BY-4.0",
      "origin": "studio-script",
      "preview": {
        "kind": "thumbnail",
        "paths": {
          "256": "cache/thumbs/7bc457a63d7d82ba_256.png",
          "512": "cache/thumbs/7bc457a63d7d82ba_512.png"
        },
        "default": "cache/thumbs/7bc457a63d7d82ba_256.png"
      },
      "thumbnails": {
        "256": "cache/thumbs/7bc457a63d7d82ba_256.png",
        "512": "cache/thumbs/7bc457a63d7d82ba_512.png"
      }
    },
    "links": {
      "file": "images/gallery/image.png",
      "sidecar": "images/gallery/image.png.asset.json",
      "thumbnail": "cache/thumbs/7bc457a63d7d82ba_256.png",
      "thumbnails": {
        "256": "cache/thumbs/7bc457a63d7d82ba_256.png",
        "512": "cache/thumbs/7bc457a63d7d82ba_512.png"
      }
    },
    "sidecar": "images/gallery/image.png.asset.json",
    "preview": {
      "kind": "thumbnail",
      "paths": {
        "256": "cache/thumbs/7bc457a63d7d82ba_256.png",
        "512": "cache/thumbs/7bc457a63d7d82ba_512.png"
      },
      "default": "cache/thumbs/7bc457a63d7d82ba_256.png"
    }
  }
}
```

Image assets queue two thumbnails (256 px and 512 px square), while audio assets
generate waveform previews (`*.waveform.json`). A `preview` entry is included in
both the metadata and top-level response for convenience, and the `links`
section exposes the relative paths to the asset, sidecar, and cached previews.

### `GET /api/assets/{id}`

Return the normalised registry payload (same shape as above) for the specified
asset ID. This is useful after a register call when downstream tooling only
persists the ID.

### `GET /api/assets/search`

Query parameters:

- `type` – optional asset type/folder filter.
- `tags`/`tag` – repeated or comma-separated tag filters (all must match).
- `license` – exact match against the stored license string.
- `q` (alias `text`) – case-insensitive substring search across the asset path and metadata.
- `limit` – cap the number of rows returned (1-500).
- `include_debug` – add registry diagnostics to the response.

Response payload:

```json5
{
  "ok": true,
  "total": 12,
  "items": [
    {
      "id": "5bf9e7ba3f9a42a3",
      "type": "images",
      "path": "images/cyberpunk/runner.png",
      "hash": "5bf9e7ba3f9a42a3b906cf7c3525e1fe...",
      "bytes": 42811,
      "tags": ["cyberpunk", "runner"],
      "license": "cc-by-4.0",
      "origin": "render-pipeline",
      "metadata": {
        "tags": ["cyberpunk", "runner"],
        "license": "cc-by-4.0",
        "origin": "render-pipeline",
        "preview": {
          "kind": "thumbnail",
          "paths": {
            "256": "cache/thumbs/5bf9e7ba3f9a42a3_256.png",
            "512": "cache/thumbs/5bf9e7ba3f9a42a3_512.png"
          },
          "default": "cache/thumbs/5bf9e7ba3f9a42a3_256.png"
        },
        "thumbnails": {
          "256": "cache/thumbs/5bf9e7ba3f9a42a3_256.png",
          "512": "cache/thumbs/5bf9e7ba3f9a42a3_512.png"
        }
      },
      "links": {
        "file": "images/cyberpunk/runner.png",
        "sidecar": "images/cyberpunk/runner.png.asset.json",
        "thumbnail": "cache/thumbs/5bf9e7ba3f9a42a3_256.png",
        "thumbnails": {
          "256": "cache/thumbs/5bf9e7ba3f9a42a3_256.png",
          "512": "cache/thumbs/5bf9e7ba3f9a42a3_512.png"
        }
      },
      "sidecar": "images/cyberpunk/runner.png.asset.json"
    }
  ],
  "filters": {
    "type": "images",
    "tags": ["cyberpunk"],
    "license": "cc-by-4.0",
    "q": "runner",
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
consistent cache. The response includes the processed/skipped/removed counters,
the resolved roots, and (starting with the hash/dedupe refresh) counts for
orphaned sidecars and missing thumbnails. The CLI wrapper
`tools/rebuild_asset_registry.py` mirrors this behaviour and logs the first few
problem files so you can triage drift.

## Sidecars, Metadata, and Hooks

- Sidecars use the `.asset.json` suffix and sit beside each asset. They store
  metadata (`tags`, `license`, `origin`, `version`, `bytes`, `preview/thumbnails`)
  alongside the top-level fields (`id`, `hash`, `created_at`). Each write also
  mirrors the payload under `assets/_meta/...` for backwards compatibility.
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
