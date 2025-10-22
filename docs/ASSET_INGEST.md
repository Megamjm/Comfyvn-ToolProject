# Asset Ingest Queue (P7)

Feature flag: `features.enable_asset_ingest` (default **false**)

This document describes the staged asset ingest pipeline that lands community
assets inside the ComfyVN registry while enforcing hashing, deduplication, and
provenance logging. Use it as the canonical reference for Studio feature
development, automation scripts, and modder tooling.

## Pipeline overview

1. **Stage** — `POST /api/ingest/queue` copies a local file (FurAffinity uploads)
   or downloads an approved remote asset (Civitai/Hugging Face when terms are
   acknowledged). The queue writes the file to `data/ingest/staging/`, computes
   a SHA-256 digest, normalises provider metadata, and persists a queue record.
2. **Dedup** — The staged artefact is registered with the shared
   `CacheManager` (`cache/ingest/dedup_cache.json`). Entries are pinned while
   pending so large pulls respect the LRU cap (`max_entries=512`,
   `max_bytes=5 GiB`). If the digest already exists in the queue or asset
   registry the job is marked as `duplicate` and the staging artefact is removed.
3. **Apply** — `POST /api/ingest/apply` copies staged artefacts into the asset
   registry through `AssetRegistry.register_file()`, writing sidecars,
   thumbnails/waveforms, and provenance markers. When a job settles, the
   staging artefact is unpinned and removed.
4. **Inspect** — `GET /api/ingest/status` surfaces queue summaries, recent jobs,
   and (optionally) a snapshot of the dedup cache for debugging.

### Provider rules

| Provider       | Source                          | Notes |
|----------------|---------------------------------|-------|
| FurAffinity    | Local file only                 | Remote pulls are disallowed to stay within ToS. |
| Civitai        | Remote allowed with `terms_acknowledged=true` | Rate-limited (~1 pull every 3s), domain allowlist `.civitai.com`. |
| Hugging Face   | Remote allowed with `terms_acknowledged=true` | Rate-limited, domain allowlist `.huggingface.co` and `.huggingfaceusercontent.com`. |
| Generic/local  | Local file or remote (no allowlist) | Behaves as a pass-through mapper; callers are responsible for provenance. |

Remote pulls honour the runtime flag
`features.require_remote_terms_ack` (default **true**) so operators can loosen
the policy when testing against mirrors.

## API surface

### `POST /api/ingest/queue`

Request body:

```json
{
  "provider": "furaffinity | civitai | huggingface | generic",
  "metadata": { "title": "...", "tags": ["..."] },
  "source_path": "path/to/local/file.png",
  "remote_url": "https://huggingface.co/...",
  "asset_type": "portraits",
  "dest_relative": "portraits/fa/artist_example.png",
  "pin": true,
  "terms_acknowledged": true
}
```

Response:

```json
{
  "job": {
    "id": "abc123def456",
    "status": "staged",
    "provider": "civitai",
    "source_kind": "remote",
    "digest": "4e3a...",
    "asset_type_hint": "models",
    "normalised_metadata": {
      "title": "...",
      "tags": ["style", "artist"],
      "license": "cc-by"
    },
    "provenance": {
      "provider": "civitai",
      "source_url": "https://civitai.com/...",
      "digest": "4e3a...",
      "provider_meta": {
        "model_id": 12345,
        "version_id": 67890
      }
    }
  }
}
```

On success the queue emits the `on_asset_ingest_enqueued` modder hook with the
same identifiers. Duplicate jobs return `status: "duplicate"` with notes that
identify the existing queue record or registry UID.

### `GET /api/ingest/status`

Parameters:

- `job_id` — when supplied, return the specific job (404 if missing).
- `limit` — number of recent jobs (default 25, max 200).
- `include_cache` — include `cache.entries`, `cache.paths`, and `cache.total_size`.

Example response:

```json
{
  "summary": { "counts": { "staged": 2, "duplicate": 1 }, "total": 3 },
  "recent": [
    { "id": "...", "status": "staged", "provider": "furaffinity", ... },
    { "id": "...", "status": "duplicate", "existing_uid": "deadbeefcafe", ... }
  ],
  "cache": { "entries": { "4e3a...": {...} }, "total_size": 9437184 }
}
```

### `POST /api/ingest/apply`

Request body:

```json
{ "job_ids": ["abc123def456"], "asset_type": "portraits" }
```

When `job_ids` is omitted the queue applies every staged entry. Returning body:

```json
{
  "applied": [
    {
      "id": "abc123def456",
      "status": "applied",
      "asset_uid": "4e3a90f2712b66a3",
      "asset_path": "portraits/fa/artist_example.png",
      "thumb_path": "thumbs/4e/4e3a90f2.png",
      "normalised_metadata": {...},
      "provenance": {...}
    }
  ],
  "skipped": ["deadbeefcafe11"],
  "failed": {
    "badfeed00001": {
      "job_id": "badfeed00001",
      "error": "Staging file missing.",
      "status": "failed",
      "digest": "5f1d...",
      "meta": {...},
      "provenance": {...}
    }
  }
}
```

Each applied job triggers `on_asset_ingest_applied`; failures emit
`on_asset_ingest_failed`.

## Metadata mappers

`comfyvn/ingest/mappers.py` translates provider payloads into a stable schema.
Highlights:

- Tag normalisation dedupes and lowercases provider tags/keywords.
- Authors are captured from provider-specific fields (FurAffinity author,
  Civitai creator, Hugging Face maintainers).
- License hints propagate into the asset registry and sidecars.
- Optional `asset_type` hints let callers route portraits/models/audio into
  bespoke registry folders.

`build_provenance_payload()` records digest, source URL, provider metadata, and
the `terms_acknowledged` flag so downstream tools can audit ingest origin.

## Modder hooks

| Event                       | Payload summary |
|-----------------------------|-----------------|
| `on_asset_ingest_enqueued`  | `job_id`, `status`, `provider`, `digest`, `asset_type_hint`, `notes` |
| `on_asset_ingest_applied`   | `job_id`, `asset_uid`, `asset_path`, `thumb_path`, `meta`, `provenance`, `digest` |
| `on_asset_ingest_failed`    | `job_id`, `provider`, `error`, `status`, `digest`, `meta`, `provenance` |

Subscribe via `/api/modder/hooks` (REST or WebSocket) to render dashboards or
drive automation whenever new assets enter the queue.

## Debug & verification

1. Flip the feature flag for local testing:

   ```json
   {
     "features": {
       "enable_asset_ingest": true
     }
   }
   ```

2. Stage a local file:

   ```bash
   curl -X POST http://127.0.0.1:8001/api/ingest/queue \
     -H "Content-Type: application/json" \
     -d '{"provider": "furaffinity", "source_path": "samples/portrait.png"}'
   ```

3. Apply queued jobs:

   ```bash
   curl -X POST http://127.0.0.1:8001/api/ingest/apply \
     -H "Content-Type: application/json" \
     -d '{}'
   ```

4. Confirm documented state:

   ```bash
   python tools/check_current_system.py --profile p7_asset_ingest_cache --base http://127.0.0.1:8001
   ```

The checker validates the feature flag default, route registration, and the
presence of documentation files. Keep this workflow green before closing the
work order.

