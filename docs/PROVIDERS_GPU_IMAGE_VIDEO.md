# Public GPU, Image, and Video Providers

Date: 2025-12-10 • Owner: Public Provider Integrations

This note documents the public GPU workflow adapters and media-generation providers that now ship with dry-run defaults. All surfaces remain **opt-in**; endpoints expose pricing metadata, capability summaries, and deterministic mock payloads so Studio tooling, mods, and CI can exercise flows without incurring third-party charges.

---

## Feature Flags & Credential Flow

- GPU backends obey `features.enable_public_gpu` (default **false**).
- Image and video providers honour `features.enable_public_image_providers`, `features.enable_public_video_providers`, or the legacy umbrella flag `features.enable_public_image_video`.
- Secrets live in `config/comfyvn.secrets.json` (or `comfyvn.secrets.json` in the project root). Entries are case-insensitive per provider:

  ```json
  {
    "runpod": {"api_key": "..."},
    "hf_inference_endpoints": {"api_token": "..."},
    "replicate": {"api_key": "..."},
    "modal": {"token_id": "...", "token_secret": "..."},
    "stability": {"api_key": "..."},
    "fal": {"api_key": "..."},
    "runway": {"api_key": "..."},
    "pika": {"api_key": "..."},
    "luma": {"api_key": "..."}
  }
  ```

- Environment fallbacks remain supported (e.g. `RUNPOD_API_KEY`, `HF_API_TOKEN`, `REPLICATE_API_TOKEN`, `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`, `STABILITY_API_KEY`, `FAL_API_KEY`, `RUNWAY_API_KEY`, `PIKA_API_KEY`, `LUMA_API_KEY`). Missing credentials force dry-run mode.

---

## API Surfaces

### GPU (`/api/providers/gpu/public/*`)

| Endpoint | Description |
| --- | --- |
| `GET /catalog` | Returns curated pricing snapshots and capability notes (`catalog.catalog_for("gpu_backends")`). |
| `POST /{provider}/health` | Merges feature flag state + credential presence and includes `pricing_url`, `last_checked`, and `capabilities`. |
| `POST /{provider}/submit` | Accepts dry-run job sketches (`{"job": {...}, "config": {...}}`) and returns deterministic ids + capability/pricing metadata. |
| `POST /{provider}/poll` | Mirrors RunPod-style job status polling without touching external APIs. |

### Image & Video (`/api/providers/{image,video}/*`)

| Endpoint | Description |
| --- | --- |
| `GET /image/catalog`, `GET /video/catalog` | Catalog metadata with capability tags, pricing links, `last_checked`, feature-flag status, and environment hints. |
| `POST /image/{provider}/health`, `POST /video/{provider}/health` | Credential probes (`config`/`cfg` optional) that stay dry-run and surface opt-in notes. |
| `POST /image/{provider}/submit`, `POST /video/{provider}/submit` | Dry-run generation flows that register task-registry entries (`public.image.submit` / `public.video.submit`) and return estimates + deterministic job ids. |
| `POST /image/{provider}/poll`, `POST /video/{provider}/poll` | Mock poll responses (`status="done"`) for automation scripts. |
| `POST /image/generate`, `POST /video/generate` | Backwards-compatible endpoints that continue to accept `{ "provider": "...", ... }` payloads and call the same submit logic. |

All responses include:

- `feature`: `{ "feature": "<flag>", "enabled": bool }`
- `pricing_url`, `docs_url`, `last_checked`, `capabilities`
- `dry_run: true`
- `execution_allowed`: reflects flag + credential readiness (still `false` until operators opt in)
- `ok`: `true` only when execution could proceed (feature flag **and** credentials present)

---

## Provider Matrices

### GPU Backends

| Provider | Module | Capabilities | Pricing Link | Last Checked |
| --- | --- | --- | --- | --- |
| RunPod | `comfyvn/public_providers/gpu_runpod.py` | Serverless + dedicated pods, secure volumes, websocket streaming. | https://www.runpod.io/pricing | 2025-02-17 |
| Hugging Face Inference Endpoints | `comfyvn/public_providers/gpu_hf_endpoints.py` | Managed inference, autoscaling, private networking. | https://huggingface.co/docs/inference-endpoints/pricing | 2025-02-17 |
| Replicate | `comfyvn/public_providers/gpu_replicate.py` | Marketplace models, async jobs, streaming & webhooks. | https://replicate.com/pricing | 2025-02-17 |
| Modal | `comfyvn/public_providers/gpu_modal.py` | Serverless GPU functions, schedules, volumes, webhooks. | https://modal.com/pricing | 2025-02-17 |

### Image Providers

| Provider | Module | Capabilities | Pricing Link | Last Checked |
| --- | --- | --- | --- | --- |
| Stability Image API | `comfyvn/public_providers/image_stability.py` | Text-to-image, image-to-image, safety presets, style presets. | https://platform.stability.ai/pricing | 2025-02-17 |
| fal.ai (Flux / SDXL) | `comfyvn/public_providers/image_fal.py` | Async jobs, webhook callbacks, custom containers, Flux & SDXL tiers. | https://fal.ai/pricing | 2025-02-17 |

### Video Providers

| Provider | Module | Capabilities | Pricing Link | Last Checked |
| --- | --- | --- | --- | --- |
| Runway Gen-3 | `comfyvn/public_providers/video_runway.py` | Storyboards, multi-prompt blends, 720p/1080p credit tiers. | https://runwayml.com/pricing | 2025-02-17 |
| Pika Labs | `comfyvn/public_providers/video_pika.py` | Style controls, FPS selection, 16 s max duration. | https://pika.art/pricing | 2025-02-17 |
| Luma Dream Machine | `comfyvn/public_providers/video_luma.py` | Partner API placeholder, reference frames, style selection. | https://lumalabs.ai/pricing | 2025-02-17 |

> **No hard-coded rates**: pricing snapshots are heuristics sourced from public vendor pages. Operators must verify current pricing before enabling live traffic.

---

## Opt-In Checklist

1. **Decide on scope**: enable `enable_public_gpu`, `enable_public_image_providers`, `enable_public_video_providers`, or umbrella `enable_public_image_video` inside `config/comfyvn.json`.
2. **Store credentials**: populate `comfyvn.secrets.json` (preferred) or export the relevant environment variables. Avoid committing secrets—`.gitignore` already covers the secrets file.
3. **Smoke test**:
   ```bash
   python tools/check_current_system.py \
     --profile p3_providers_gpu_image_video \
     --base http://127.0.0.1:8001
   ```
   The checker asserts that health endpoints stay structured, pricing URLs are present, and dry-run payloads register tasks without reaching external APIs.
4. **Monitor hooks**: public submit routes register tasks under `public.<kind>.submit` and log lines `public.{image,video,gpu}.*` with payload summaries. Subscribe to the modder hook stream or tail `logs/server.log` while enabling providers.
5. **Gate production traffic**: keep feature flags off in production until compliance, rate-limiting, and budgeting policies are finalised. Dry-run payloads allow GUI/CLI tooling to integrate safely beforehand.

---

## Debug & Integration Notes

- Health endpoints accept optional `{"config": {...}}` payloads so contributors can validate credential formats without touching `comfyvn.secrets.json`.
- Submit responses surface `execution_allowed` and `warnings`; CI can assert that provisioning is complete (flag + credential) before attempting real workloads.
- Poll endpoints return deterministic job ids (`mock-<provider>-1`) so automation scripts may cache/mock workflows without hitting provider SDKs.
- Use the task registry (`/api/jobs/list`) or the event bus to watch for `public.{gpu,image,video}.*` completions and feed downstream automation (asset cataloguing, provenance scaffolding, etc.).
- Developer deep-dive: `docs/dev_notes_public_media_providers.md` captures extended examples, hook surfaces, and debugging recipes. Update that note when introducing additional providers or toggling live execution paths.

---

## Change Log

- Added GPU adapters (`gpu_hf_endpoints`, `gpu_modal`, `gpu_replicate`) with metadata + dry-run helpers.
- Extended image/video adapters with health/submit/poll entry points and capability metadata.
- Unified GPU and media routes so every provider exposes `health`, `submit`, `poll`, and consistent dry-run envelopes with pricing snapshots.
- Updated README, architecture notes, developer docs, and `CHANGELOG.md`; new checker profile `p3_providers_gpu_image_video` covers the end-to-end flow.

