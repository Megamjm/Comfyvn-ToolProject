# Civitai Provider (Phase 7)

The Civitai connector surfaces catalog information for models without enabling
binary downloads. Health, search, and metadata endpoints power Studio tooling
and modder workflows while the download route stays gated behind Phase-7
license enforcement.

- **Feature flag:** `enable_public_model_hubs` (defaults to `false`)
- **API base:** `https://civitai.com/api/v1`
- **Docs:** https://github.com/civitai/civitai/wiki/API-Reference
- **Pricing / quota:** https://civitai.com/pricing (public REST ≈60 req/min/IP)
- **Terms / license:** https://civitai.com/terms-of-service
- **Last reviewed:** 2025-02-20

Environment variables (optional, for private assets or higher quotas):
`COMFYVN_CIVITAI_TOKEN`, `CIVITAI_API_TOKEN`. Secrets resolved through the
standard provider vault keys `api_key`, `token`, `key`.

Downloads stay disabled until users acknowledge license terms **and** have
available storage quota. The API currently returns dry-run plans only.

- **License snapshot:** Call `POST /api/advisory/license/snapshot` with the resolved
  model/version/file metadata before offering download. Once the user accepts the
  normalised text, record it via `POST /api/advisory/license/ack` and gate pull
  attempts through `POST /api/advisory/license/require`. See
  `docs/ADVISORY_LICENSE_SNAPSHOT.md` for payload shapes and automation notes.

---

## Endpoints

### `GET /api/providers/civitai/health`

Returns upstream reachability, latency, and rate-limit notes. Includes a sample
catalog entry for quick UI debugging.

```json
{
  "provider": "civitai",
  "ok": true,
  "dry_run": true,
  "latency_ms": 185,
  "pricing_url": "https://civitai.com/pricing",
  "docs_url": "https://github.com/civitai/civitai/wiki/API-Reference",
  "terms_url": "https://civitai.com/terms-of-service",
  "last_checked": "2025-02-20",
  "rate_limit_notes": "Public REST endpoints allow ~60 requests/minute per IP; API tokens can raise quotas.",
  "sample": {
    "id": 257749,
    "name": "Pony Diffusion V6 XL",
    "model_type": "Checkpoint",
    "nsfw": false,
    "license": {
      "credit_required": true,
      "allow_commercial_use": [
        "Image",
        "RentCivit"
      ],
      "allow_derivatives": true,
      "allow_relicense": false
    }
  },
  "feature": {
    "flag": "enable_public_model_hubs",
    "enabled": false
  }
}
```

### `GET /api/providers/civitai/search`

Parameters:

- `q` (required): search query (matches name, tags, description).
- `limit` (optional, default 20, max 50).
- `type` (optional, repeatable): Civitai model types such as `Checkpoint`,
  `LORA`, `TextualInversion`, `Embedding`.
- `nsfw` (optional, default `false`): include NSFW-tagged entries.

Response items normalize model type, NSFW flags, license summary, and the latest
version’s size estimate.

```json
{
  "provider": "civitai",
  "query": "flux",
  "limit": 10,
  "count": 3,
  "allow_nsfw": false,
  "items": [
    {
      "id": 308691,
      "name": "FLUX Dev Merge",
      "model_type": "Checkpoint",
      "nsfw": false,
      "license": {
        "credit_required": true,
        "allow_commercial_use": false,
        "allow_derivatives": true,
        "allow_relicense": false
      },
      "version": {
        "id": 352812,
        "name": "v1.1",
        "size_mb": 6985.21,
        "nsfw_level": "None",
        "files": [
          {
            "name": "flux-dev-fp16.safetensors",
            "size_mb": 6985.21,
            "format": "SafeTensor",
            "primary": true
          }
        ]
      }
    }
  ],
  "feature": {
    "flag": "enable_public_model_hubs",
    "enabled": false
  }
}
```

### `GET /api/providers/civitai/metadata/{model_id}`

Fetch full metadata for a model (all versions, files, license controls). Optionally
set `?version={id}` to focus on a specific version.

```json
{
  "id": 308691,
  "name": "FLUX Dev Merge",
  "model_type": "Checkpoint",
  "license": {
    "credit_required": true,
    "allow_commercial_use": false,
    "allow_derivatives": true,
    "allow_relicense": false
  },
  "versions": [
    {
      "id": 352812,
      "name": "v1.1",
      "size_mb": 6985.21,
      "files": [
        {
          "id": 1010767,
          "name": "flux-dev-fp16.safetensors",
          "size_mb": 6985.21,
          "format": "SafeTensor",
          "download_url": "https://civitai.com/api/download/models/352812",
          "primary": true
        }
      ],
      "stats": {
        "downloadCount": 12345,
        "rating": 4.95
      }
    }
  ],
  "selected_version": {
    "id": 352812,
    "name": "v1.1",
    "size_mb": 6985.21
  },
  "dry_run": true,
  "download_requires_ack": true,
  "feature": {
    "flag": "enable_public_model_hubs",
    "enabled": false
  }
}
```

### `POST /api/providers/civitai/download`

Returns a dry-run download plan and enforces license acknowledgement. Provide:

- `model_id` (required)
- `version_id` (optional)
- `license_ack` (required, boolean)
- `available_mb` / `quota_mb` (optional) – for storage checks

Sample response when the feature flag is disabled (default):

```json
{
  "provider": "civitai",
  "model_id": 308691,
  "version_id": 352812,
  "total_size_mb": 6985.21,
  "files": [
    {
      "name": "flux-dev-fp16.safetensors",
      "size_mb": 6985.21,
      "primary": true
    }
  ],
  "quota": {
    "available_mb": 4096.0,
    "required_mb": 6985.21,
    "ok": false
  },
  "download_allowed": false,
  "license_ack_required": true,
  "acknowledged": true,
  "reason": "insufficient_storage_quota",
  "dry_run": true,
  "feature": {
    "flag": "enable_public_model_hubs",
    "enabled": false
  },
  "terms_url": "https://civitai.com/terms-of-service"
}
```

When the storage check passes and the feature flag is enabled, the route still
returns `download_allowed: false` with reason `phase7_download_gate_active`.
Actual downloads remain blocked until the Phase-7 license enforcer ships.

---

## Debug Hooks for Modders

- The search payload exposes `license`, NSFW flags, and size estimates so modders
  can pre-filter models before requesting metadata.
- Metadata responses list every file (with hash, format, and approximate size)
  for asset manifest tooling.
- Download plans expose per-file details without streaming binaries, enabling
  CLI tooling to stage consent prompts and quota checks.
- Health output includes a sample model stub for UI smoke tests and links to
  current pricing/terms.

Remember to keep `enable_public_model_hubs` disabled in production until legal
sign-off and storage quota enforcement are complete. Studio environments can
toggle the flag locally for dry-run tooling only.
