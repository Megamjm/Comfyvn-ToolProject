# Public Image & Video APIs — 2025-10-21 (A/B)

## Intent
- Expose “public” image/video generation through a safe server facade so Studio operators can audition Stability, fal.ai, Runway, Pika, and Luma outputs without wiring bespoke scripts.
- Default every outbound call to a dry-run that only logs payload shape; real executions stay opt-in behind feature flags and environment-provided API keys.
- Surface per-provider metadata (models, quotas, credit burn) to the GUI so the Studio can explain why a request failed, succeeded, or remained a dry-run.
- Capture a uniform provenance payload that downstream asset registries can stash alongside generated stills/clips when the flags eventually flip on.

## Touchpoints
- `comfyvn/public_providers/image_stability.py` — Stability Image API adapter (txt2img/img2img variants, style presets, safety settings).
- `comfyvn/public_providers/image_fal.py` — fal.ai wrapper for Flux/SDXL models, handles queue polling vs. low-latency endpoints.
- `comfyvn/public_providers/video_runway.py`, `video_pika.py`, `video_luma.py` — credit/seconds accountors plus payload coercion for prompt, duration, aspect, and reference frames.
- `comfyvn/server/routes/providers_image_video.py` — FastAPI router exposing `POST /api/providers/{image,video}/generate` and `GET /api/providers/{image,video}/catalog`.
- `comfyvn/config/feature_flags.py` + `config/comfyvn.json` — add `enable_public_image_providers` and `enable_public_video_providers` so real calls are gated per environment.

## Feature Flags & Config
- Flags default false; when disabled the adapters short-circuit to `{ "dry_run": true, "payload": … }` without touching the network.
- Settings panel should surface toggles with a guarded tooltip (“API key required; dry-run only by default”) and persist choices under `features`.
- Expect API keys via environment (`STABILITY_API_KEY`, `FAL_KEY`, `RUNWAY_API_KEY`, `PIKA_API_KEY`, `LUMA_API_KEY`) or `config/secrets.json`; missing keys downgrade to dry-run irrespective of flag state.
- Loggers: use `LOGGER.info("public-image.dry-run", extra={"provider": …, "payload": …})` so ops can trace request shapes without dumping secrets.

## Route Behavior
- `GET /api/providers/image/catalog` and `/video/catalog` aggregate available adapters, supported modes (txt2img, image2image, video, storyboard), and whether they are active, dry-run, or missing credentials.
- `POST /api/providers/image/generate` accepts `{provider, mode, prompt, parameters, webhook?}`; responses include `{"dry_run": bool, "job_id": str, "estimates": {"credits": …}}`.
- `POST /api/providers/video/generate` mirrors the pattern with `duration_seconds`, `resolution`, reference frames (optional), and returns credit burn estimates plus provider-specific queue ids.
- Every generate call records a `public_job` entry via the task registry (same shape as compute providers) so GUI toasts can reflect pending vs. finalised renders.
- When flags are on, adapters should call the real API asynchronously, stream logs to `logs/public_providers/<provider>/<job>.log`, and stash responses under `data/public_exports/`.

## Provider Reference

### Image (A)
- **Stability API**: Support `/v2beta/stable-image/sd3` and `/image-to-image` with style, clip guidance, and safety settings; respect account rate limits, include `organization` header when provided.
- **fal.ai**: Offer Flux (v0.1 Pro) and SDXL pipelines; detect whether the selected model requires queue polling vs. synchronous result; honour GPU-type metadata (`H100`, `A100`), exposing cost multipliers.
- **Adobe Firefly (optional)**: Document licence gates—warn that API usage requires enterprise entitlements; treat it as disabled unless `FIREFLY_API_KEY` is set and workspace flagged for compliance.

### Video (B)
- **Runway**: Internally convert prompt + storyboard frames to `/v1/ai/content/video` payloads; map plan tiers to credit burn (1 credit ≈ $0.01); provide quota fetch (`GET /usage`) when API key present.
- **Pika**: Duration-based billing ($0.05/sec @720p, $0.07/sec @1080p); adaptor should cap maximum duration by tier, and expose an overridable `max_duration_seconds` guard.
- **Luma Dream Machine**: Treat as “best effort” — API commonly proxied; include metadata fields for access broker, plan tier (Lite/Pro), and fallback note when credentials missing.

## Pricing & Policy Notes
- Include static references and doc URLs in the catalog payload so Studio can link out (`pricing_url`, `docs_url`).
- Credit estimators should multiply base price by prompt duration/steps; surface the numbers in dry-run responses even when the provider call is skipped.
- Log when accounts approach soft limits (Runway’s credit balance, Pika’s usage seconds) and flag them in catalog responses as `{"status": "low-quota"}`.
- Respect per-provider content policies; enforce opt-out toggles for nsfw content and warn if Safety settings would be bypassed.

## QA & Dry-Run Strategy
- Unit tests should assert dry-run payloads per provider, cover missing-key scenarios, and validate credit calculators.
- Integration smoke: enable flags in a sandbox with fake adapters (monkeypatch HTTP clients) so task registry + log writers are exercised without external calls.
- CLI helper `python -m comfyvn.server.routes.providers_image_video --dry-run` can replay saved payloads to confirm logging/estimation logic.
- Document manual verification steps in `docs/production_workflows_v0.7.md` once real calls are cleared for release environments.

## Follow-ups
- Coordinate with Asset Registry once real renders are allowed so generated stills/clips register provenance sidecars automatically.
- Consider caching catalog responses and quota checks for a short TTL (e.g., 5 minutes) to avoid hammering provider metadata endpoints.
- Track outstanding compliance reviews for Firefly/Luma; if procurement blocks API usage, leave adapters in dry-run-only mode with clear messaging.
