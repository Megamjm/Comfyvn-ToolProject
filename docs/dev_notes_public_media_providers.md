# Public Media Provider Hooks (Dry-Run)

Date: 2025-11-10 • Updated: 2025-12-10 • Owner: Project Integration & Docs (Public APIs)

This note captures the current contract for the **public** image/video adapters now shipped with ComfyVN. Calls default to dry-run payloads so Studio and automation tooling can validate request shapes, pricing, and task logging before any external API keys are supplied.

## Feature Flags & Secrets

- Runtime feature flags:
  - `enable_public_gpu`
  - `enable_public_image_providers`
  - `enable_public_video_providers`
  - The legacy `enable_public_image_video` flag remains as a compatibility mirror; the Settings panel keeps it in sync with the new toggles so existing automation scripts stay functional.
- Configuration landing points:
  - `config/comfyvn.json` persists the feature flags.
  - `config/comfyvn.secrets.json` (or `comfyvn.secrets.json`) can include provider-specific credentials under case-insensitive keys (`{"stability": {"api_key": "..."} }`).
- Environment fallbacks:
  - GPU: `RUNPOD_API_KEY`, `RUNPOD_TOKEN`, `HF_API_TOKEN`, `HUGGINGFACEHUB_API_TOKEN`, `REPLICATE_API_TOKEN`, `MODAL_API_TOKEN`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`.
  - Image/Video: `STABILITY_API_KEY`, `FAL_KEY`/`FAL_API_KEY`, `RUNWAY_API_KEY`, `RUNWAY_TOKEN`, `PIKA_API_KEY`, `LUMA_API_KEY`.
  - The adapters resolve environment variables first, then secrets JSON, then return an empty string (forcing dry-run) when nothing is present.

## Endpoints

FastAPI routes live in:

- `comfyvn/server/routes/providers_gpu.py`
- `comfyvn/server/routes/providers_image_video.py`

GPU routes (`/api/providers/gpu/public/*`):

- `GET /catalog`
- `POST /{provider}/health`
- `POST /{provider}/submit`
- `POST /{provider}/poll`

Image/Video routes:

- `GET /api/providers/image/catalog`, `GET /api/providers/video/catalog`
- `POST /api/providers/image/{provider}/health`, `POST /api/providers/video/{provider}/health`
- `POST /api/providers/image/{provider}/submit`, `POST /api/providers/video/{provider}/submit`
- `POST /api/providers/image/{provider}/poll`, `POST /api/providers/video/{provider}/poll`
- Back-compat: `POST /api/providers/image/generate` and `POST /api/providers/video/generate`

Each submit route registers a task-registry item (`public.<kind>.submit` or the legacy `public.<kind>.generate`) so GUI toasts and CLI automation can inspect payloads, cost estimates, and execution flags without waiting for a worker loop. Health responses now include `pricing_url`, `last_checked`, and capability snapshots for dashboards.

## Provider Modules

Adapters remain intentionally narrow to keep dry-run behaviour predictable. All now expose:

- `metadata()` → capability notes + pricing/docs URLs + `last_checked`.
- `health(config)` → credential probe (always dry-run).
- `submit(request, execute, config)` + `poll(job_id, config)` → deterministic dry-run payloads with task-registry registration.
- `prepare_request()` / `estimate_cost()` helpers for modders wanting to reuse heuristics.

### GPU Backends

| Provider | Module | Env keys | Notes |
| --- | --- | --- | --- |
| RunPod | `comfyvn/public_providers/gpu_runpod.py` | `RUNPOD_API_KEY`, `RUNPOD_TOKEN` | Serverless + dedicated pods, secure volumes, websocket streaming. |
| Hugging Face Inference Endpoints | `comfyvn/public_providers/gpu_hf_endpoints.py` | `HF_API_TOKEN`, `HUGGINGFACEHUB_API_TOKEN` | Managed inference, VNet, autoscaling; dry-run acknowledges token presence only. |
| Replicate | `comfyvn/public_providers/gpu_replicate.py` | `REPLICATE_API_TOKEN` | Marketplace models, async jobs, streaming/webhook heuristics. |
| Modal | `comfyvn/public_providers/gpu_modal.py` | `MODAL_API_TOKEN`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | Serverless GPU functions, schedules, volumes. Accepts either API token or token pair. |

### Image & Video Providers

| Provider | Module | Env keys | Notes |
| --- | --- | --- | --- |
| Stability Image API | `comfyvn/public_providers/image_stability.py` | `STABILITY_API_KEY` | Text/image modes, safety presets, style presets. |
| fal.ai (Flux / SDXL) | `comfyvn/public_providers/image_fal.py` | `FAL_KEY`, `FAL_API_KEY` | Async API with webhook callbacks, GPU-minute heuristics. |
| Runway Gen-3 | `comfyvn/public_providers/video_runway.py` | `RUNWAY_API_KEY`, `RUNWAY_TOKEN` | Credits-per-second vary by resolution; includes USD estimates (credits × $0.01). |
| Pika Labs | `comfyvn/public_providers/video_pika.py` | `PIKA_API_KEY` | Rates ($0.05/second @720p, $0.07/second @1080p) baked into cost estimator. |
| Luma Dream Machine | `comfyvn/public_providers/video_luma.py` | `LUMA_API_KEY` | Partner API placeholder with credit heuristics + reference frame support. |

## Sample Flow

```bash
# 1) Inspect GPU & Image provider catalogues.
curl http://127.0.0.1:8000/api/providers/image/catalog | jq
curl http://127.0.0.1:8000/api/providers/gpu/public/catalog | jq

# 2) Probe credentials (dry-run).
curl -X POST http://127.0.0.1:8000/api/providers/gpu/public/runpod/health | jq
curl -X POST http://127.0.0.1:8000/api/providers/image/stability/health | jq

# 3) Perform a dry-run Stability request (no API key needed).
curl -X POST http://127.0.0.1:8000/api/providers/image/generate \
    -H "Content-Type: application/json" \
    -d '{
          "provider": "stability",
          "mode": "text-to-image",
          "prompt": "retro sci-fi city skyline at dusk",
          "parameters": {
            "samples": 2,
            "style_preset": "cinematic"
          }
        }' | jq

# 4) Fetch the recorded job metadata (from the Jobs API or logs).
curl http://127.0.0.1:8000/api/jobs/list | jq '.tasks[] | select(.kind|test("^public\\.(image|video)\\.submit$"))'
```

Sample response envelope:

```json
{
  "provider": "stability",
  "kind": "image",
  "mode": "text-to-image",
  "dry_run": true,
  "payload": {
    "mode": "text-to-image",
    "prompt": "…",
    "parameters": {
      "samples": 2
    }
  },
  "estimates": {
    "unit": "image",
    "count": 2,
    "unit_cost_usd": 0.04,
    "estimated_cost_usd": 0.08
  },
  "execution_allowed": false,
  "warnings": [
    "missing api key; forcing dry-run",
    "feature flag disabled or execution not permitted"
  ],
  "job_id": "4d8249eb-..."
}
```

## Debugging Tips

- Increase verbosity: `COMFYVN_LOG_LEVEL=DEBUG python run_comfyvn.py --server-only` to include provider payload logs (`public.gpu.*`, `public.image.*`, `public.video.*`).
- To simulate “execution allowed” without live calls, set an API key env var and enable the feature flag; the adapters still return dry-run payloads but flag `execution_allowed: true` so callers can branch logic.
- Automation hooks can watch the task registry or subscribe to the job event bus to react when public-provider jobs complete (even though they are instantaneous in dry-run mode).
- Extend cost heuristics by wrapping provider modules; each exports `estimate_cost()` for straightforward monkeypatching during tests. Run `python tools/check_current_system.py --profile p3_providers_gpu_image_video` to validate health + dry-run envelopes end-to-end.

## Follow-Ups

- Wire live SDK calls once compliance + rate-limiting strategies are signed off; update adapters to stream progress/logs into provider-specific log files under `logs/public_providers/`.
- Coordinate with the asset registry so successful executions can auto-register generated stills/clips with provenance sidecars.
- Add quota polling (Runway credits, fal.ai usage) to the catalog responses after verifying API semantics.
