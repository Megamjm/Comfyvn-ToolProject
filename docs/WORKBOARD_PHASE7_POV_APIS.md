# Phase 7 — POV + Public APIs

## Tracks & Owners
1. **POV Worldlines & Timelines** — Sync `POVManager` with `WORLDLINES`, export per-world manifests, surface `/api/pov/worlds` CRUD for automation. _Owner: POV Integration._
2. **Theme & World Changer** — Update theme presets, document overrides, expose `/api/themes/{templates,apply}` debug flows. _Owner: Theme Chat._
3. **Weather/Lighting/Transitions** — Maintain `/api/weather/state`, document presets, add modder debugging recipes. _Owner: World FX._
4. **Battle Layer** — Stub battle planner + REST until simulator arrives; document plan payloads. _Owner: Battle Systems._
5. **GPU & Workflow APIs** — Catalog RunPod/HF/Replicate/Modal pricing, wire `/api/providers/gpu/public/*`. _Owner: Providers Chat._
6. **Image/Video APIs** — Pricing + review notes for Runway/Pika/Luma/fal.ai, `/api/providers/image-video/public/catalog`. _Owner: Media Lab._
7. **Translate/OCR/Speech** — Google/DeepL/Amazon/Deepgram/AssemblyAI catalog and dry-run hooks. _Owner: Localization._
8. **LLM Router + Top-10** — OpenAI/Anthropic/Gemini/OpenRouter/Azure pricing + recommendations, `/api/providers/llm/public/catalog`. _Owner: LLM Ops._
9. **Remote Installer Orchestrator** — Reconfirm `comfyvn/server/routes/remote_orchestrator.py`, ensure docs point to `/api/remote/{modules,install}`. _Owner: Remote Ops._
10. **Modder Hooks & Debug** — Update docs on `/api/modder/*`, WebSocket topics, secrets layout. _Owner: Tooling & Docs._

## Definition of Done (Global)
- All new surfaces behind feature flags; defaults `false` for external providers, `true` for weather/battle/themes to keep Studio panels live.
- README, architecture.md, THEME_TEMPLATES.md, WEATHER_PROFILES.md, BATTLE_DESIGN.md, POV_DESIGN.md, LLM_RECOMMENDATIONS.md reference pricing anchors, debug hooks, and modder entry points.
- CHANGELOG entry published (2025-11-08) covering catalog endpoints, feature flags, docs updates.
- `config/comfyvn.secrets.json` documented as the canonical provider secret map (git-ignored default with placeholders).

## Pricing Snapshot (2025-11)
- **GPU/Workflow** — RunPod 4090 $0.34/hr, H100 80GB $1.99/hr; Hugging Face Endpoints T4 $0.60/hr, A10G $1.20/hr; Modal per-second GPU (A10G $1.32/hr); Replicate Flux Pro Ultra ≈ $0.06/image.
- **Image/Video** — Runway API $0.01/credit (~12–30 credits/sec); Pika API $0.05–$0.07/sec; Luma Dream Machine Lite $9.99/mo (120 fast credits); fal.ai H100 $1.89/hr, Flux Pro $0.12/image.
- **Translate/OCR/Speech** — Google Translate $20/M chars (500k free tier); DeepL API Free 500k chars, Pro €4.99/mo + €0.00002/char; Amazon Translate $15/M chars; Google Vision OCR $1.50/1K units; AWS Rekognition image $1/1K; Deepgram Nova-2 $0.004/sec; AssemblyAI STT $0.015/min.
- **LLM** — OpenAI GPT-4o $5/$15 per 1M tokens, GPT-4o mini $0.15/$0.60; Anthropic Claude 3.5 Haiku $1/$5, Sonnet $3/$15; Google Gemini 2.0 Flash $0.10/$0.40, Pro $3.50/$10.50; OpenRouter adds 10% platform fee; Azure OpenAI matches OpenAI base rates per region.

## Debug & API Hooks
- `/api/providers/gpu/public/runpod/{health,submit,poll}` → deterministic dry-run responses, logging `feature.enabled` + `dry_run` state for GUI overlays.
- `/api/providers/image-video/public/catalog` → table for Runway/Pika/Luma/fal.ai; `/runway/price` returns timestamped snapshot.
- `/api/providers/translate/public/google/translate` → echoes input until API key present; ensure docs highlight this for modders writing tooling.
- `/api/providers/llm/public/catalog` → feed `docs/LLM_RECOMMENDATIONS.md` with latest rates + usage notes.
- `/api/pov/worlds` → list/create/update/activate; recommended to pair with `/api/pov/get` for live state overlays.
- `/api/battle/plan` → deterministic stub; front-end should mark responses with `plan.meta.dry_run` until simulator wired.
- `/api/modder/history` + WebSocket `/ws/modder` → document event payloads for tooling authors; tie to new provider/adaptor events.

## Outstanding Follow-ups
- Replace battle stub with simulation engine (seeded narration, resolve endpoints) — Q1 roadmap.
- Implement live provider SDK calls once API key management is approved (RunPod/HF/Replicate/Modal + translation/LLM providers).
- Expand catalog auto-refresh pipeline (pull pricing JSON weekly) to avoid stale data.
- Surface provider feature flags + secrets status inside Studio Settings → Providers panel.
