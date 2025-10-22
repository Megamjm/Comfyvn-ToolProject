2025-10-21 — POV Render Pipeline & LoRA (Parts A/B)
==================================================

Intent
------
- Switching POV should automatically backfill missing portraits/poses for the active character.
- Renders must flow through the hardened ComfyUI bridge so per-character LoRA stacks and overrides stay consistent.
- Cache policy: dedupe by `(character, style, pose)`; cache hits must short-circuit further renders while surfacing the existing asset + sidecars.

Implementation Highlights
-------------------------
- `comfyvn/pov/render_pipeline.py` — orchestrates renders, copies ComfyUI sidecars, registers assets, and writes cache metadata.
- `comfyvn/bridge/comfy_hardening.py` — exposes `character_loras()` and `build_overrides()` for callers that need explicit LoRA payloads.
- `comfyvn/server/routes/pov_render.py` — new FastAPI entrypoint (`POST /api/pov/render/switch`) that updates POV state *and* triggers render staging.
- Tests: `tests/test_pov_render_pipeline.py` covers cache hits/misses and force re-render behaviour with a fake bridge.

API Contract
------------
```
POST /api/pov/render/switch
{
  "character_id": "alice",
  "style": "hero",
  "poses": ["neutral", "smile"],
  "force": false,
  "workflow_path": "comfyvn/workflows/scene_still.json"
}
```

Response mirrors the POV state plus `results[]`:

- `character_id`, `style`, `pose`
- `asset_path`, `asset_sidecar`, `bridge_sidecar`
- `loras[]` (LoRA path/weight metadata)
- `cached` (`false` on fresh render, `true` on cache hit)
- `cache_key` for downstream tooling

Rendering & Caching Notes
-------------------------
- Hardened bridge injects LoRA payloads via `character_loras()`, guaranteeing parity with character metadata.
- Assets register under `portrait` with sidecars storing `workflow_id`, `prompt_id`, `loras`, and mirrored ComfyUI provenance (`<pose>.png.bridge.json`).
- Cache file lives at `cache/pov/render_cache.json` with entries validated before reuse (missing artifacts/sidecars trigger a re-render automatically).
- Force re-render by supplying `{"force": true}`; the registry row is updated in place so asset UIDs remain stable.

Debugging & Hooks
-----------------
- Enable `LOG_LEVEL=DEBUG` or target `comfyvn.pov.render` to trace cache decisions, payloads, and sidecar copies.
- Asset registry hooks (`asset_registered`, `asset_sidecar_written`) fire after each render, making it easy to chain thumbnails or pack exports.
- CLI modders can hit the endpoint manually, then inspect `assets/characters/<char>/<style>/` for the registered PNG, `.asset.json`, and `.bridge.json` payloads.
- Tests run via `pytest tests/test_pov_render_pipeline.py` to confirm cache/force behaviour without a live ComfyUI instance.
