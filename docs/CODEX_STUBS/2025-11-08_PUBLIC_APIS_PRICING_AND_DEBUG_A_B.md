# Public APIs Pricing & Debug Hooks — 2025-11-08 (A/B)

## Intent
- Capture up-to-date pricing heuristics and dev-facing review notes for GPU, image/video, translation/OCR/speech, and LLM providers so Studio operators can make informed routing decisions.
- Provide safe dry-run adapters (`comfyvn/public_providers/*`) plus FastAPI surfaces that honour feature flags, enabling modders to inspect payload shapes without exposing secrets.
- Ensure README/architecture and modder docs flag the new debug surfaces, feature toggles, and secrets file layout so contributors can wire their own tooling without guesswork.

## Touchpoints
- `comfyvn/public_providers/catalog.py` stores category catalogs (pricing, reviews, links) consumed by the new public routes.
- `comfyvn/server/routes/providers_{gpu,image_video,translate_ocr_speech,llm}.py` expose `/api/providers/*/public` endpoints returning catalog data and dry-run helpers.
- `comfyvn/server/routes/pov_worlds.py` and `battle.py` keep POV worldlines + battle scaffolding accessible for Phase 7 workflows.
- `README.md`, `architecture.md`, `docs/POV_DESIGN.md`, `docs/THEME_TEMPLATES.md`, `docs/WEATHER_PROFILES.md`, `docs/BATTLE_DESIGN.md`, `docs/LLM_RECOMMENDATIONS.md`, and `docs/WORKBOARD_PHASE7_POV_APIS.md` summarise pricing anchors, debug hooks, and modder entry points.

## Feature Flags & Config
- Added `enable_public_gpu`, `enable_public_image_video`, `enable_public_translate`, and `enable_public_llm` (default `false`). Pricing endpoints always respond but mark `feature.enabled=false` when disabled.
- Shipping `config/comfyvn.secrets.json` (git-ignored) as the central provider secrets map. Adapters merge runtime payloads with this file before attempting live calls.
- `enable_weather`, `enable_battle`, and `enable_themes` default `true` so Studio surfaces remain available while still allowing operators to suppress them per environment.

## Debug Hooks
- `/api/providers/gpu/public/runpod/*` accepts `{config: {...}}` payloads and returns deterministic dry-run responses for health/submit/poll flows.
- `/api/providers/image-video/public/catalog` & `/runway/price` provide pricing metadata for UI overlays; identical patterns exist for translate/LLM catalogs.
- `/api/pov/worlds/*` exposes list/create/update/activate verbs so modders can script worldline diffs directly against the backend.
- `/api/battle/plan` emits a deterministic stub timeline (setup/engagement/resolution) that downstream UI prototypes can consume until the real simulator lands.
- Docs now call out WebSocket topics + REST endpoints modders can subscribe to when implementing custom tooling (see `docs/dev_notes_modder_hooks.md`).
