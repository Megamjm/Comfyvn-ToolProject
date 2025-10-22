# LLM Registry & Module Recommendations

The public LLM router (Phase 3) exposes feature-flagged metadata and dry-run
plans so modders can pick models without touching production keys. Everything
flows through `/api/providers/llm/*` and keeps traffic OFF unless credentials are
present.

## Router & Diagnostics

| Endpoint | Purpose |
| --- | --- |
| `GET /api/providers/llm/registry` | Returns provider diagnostics, model metadata (tags, pricing), and a tag index for filtering. |
| `GET /api/providers/llm/public/catalog` | Static heuristics from `comfyvn/public_providers/catalog.py`. |
| `POST /api/providers/llm/chat` | Dry-run chat router. Echoes the HTTP dispatch plan (`method`, `url`, `headers`, `json`) without issuing network calls. |

The `feature` field reflects `config/comfyvn.json → features.enable_public_llm`.
Responses include `credentials` snapshots so tooling can expose missing keys.

## Per-Module Presets

| Module | Default Provider / Model | Tags | Notes |
| --- | --- | --- | --- |
| Translate (JSON) | OpenAI – `gpt-4o-mini` | `["general","fast","cost_optimized"]` | Feeds `POST /api/translate/batch`; stays in identity stub mode until `enable_translation_manager` and provider flags are explicitly enabled. When activating real MT, keep `temperature=0.1`, `response_format={"type":"json_object"}`, and pass through TM `meta` (asset/component) so reviewers get full context. |
| VN Chat (Roleplay) | Anthropic – `claude-3-5-sonnet-20241022` | `["reasoning","tool_use"]` | Balanced creativity with large context. Keep `thinking` disabled for consistency. |
| Narrator (Voice-over JSON) | OpenAI – `gpt-4o` | `["vision","tool_use","general"]` | Use schema `{ "narration": str, "beats": [...] }`; dry-run plan previews headers/body. |
| Worldbuild (Structured Lore) | Google Gemini – `gemini-2.0-pro` | `["reasoning","enterprise"]` | High context budget. Add `generationConfig` for JSON arrays + safety tuning. |
| Battle Narration | OpenRouter – `openrouter/meta-llama/llama-3.1-70b-instruct` | `["general","cost_optimized"]` | Works across OpenRouter tiers; dry-run exposes metadata headers for mod integration. |

Presets live in `defaults.modules.*` inside the registry payload. Update those
fields (or the UI) after verifying pricing and credentials.

## Alternate Picks

- **Translate:** DeepL via OpenRouter (`openrouter/deepl/deepl-chatgpt`) for
  glossary support; Gemini `gemini-2.0-flash` for real-time localisation. Pipe
  responses back through `/api/translate/review` so TM versioning stays in
  sync.
- **VN Chat:** OpenRouter `openrouter/perplexity/llama-3.1-sonar-large-128k-chat`
  when retrieval-friendly roleplay is desired.
- **Narrator:** Anthropic `claude-3-5-haiku-20241022` for faster drafts; set
  `max_tokens=800` to maintain pacing.
- **Worldbuild:** OpenAI `gpt-4.1` with JSON schema for multi-region world maps.
- **Battle Narration:** DeepSeek via OpenRouter (`openrouter/deepseek/deepseek-chat`)
  as a budget action summariser.

## Pricing & Credential Reference (Jan 2025)

| Provider | Pricing Link | Sample Rate (USD / 1M tokens) | Environment Keys |
| --- | --- | --- | --- |
| OpenAI | <https://openai.com/api/pricing> | GPT-4o: $5 in / $15 out | `COMFYVN_LLM_OPENAI_KEY`, `OPENAI_API_KEY`, optional `OPENAI_ORG_ID` |
| Anthropic | <https://www.anthropic.com/api#pricing> | Claude 3.5 Sonnet: $3 in / $15 out | `COMFYVN_LLM_ANTHROPIC_KEY`, `ANTHROPIC_API_KEY` |
| Google Gemini | <https://ai.google.dev/pricing> | Gemini 2.0 Pro: $3.50 in / $10.50 out | `COMFYVN_LLM_GEMINI_KEY`, `GOOGLE_API_KEY` |
| OpenRouter | <https://openrouter.ai/pricing> | +10% platform fee on top of upstream cost | `COMFYVN_LLM_OPENROUTER_KEY`, `OPENROUTER_API_KEY` |

Credentials should be stored in `config/comfyvn.secrets.json` (encrypted) or set
via environment variables before toggling `enable_public_llm`.

## Dry-Run Tips

- Use `curl ... /api/providers/llm/chat` with `provider` & `model` to confirm the
  resolved endpoint and headers before enabling live traffic.
- `plan.model_info.tags` mirrors the tag index from the registry—handy for
  filtering UI dropdowns.
- Add `dry_run=true` in client payloads if you want explicit confirmation in logs
  (responses already include the flag).

## Roadmap

- Wire live proxy execution behind per-provider toggles once billing ownership is
  clear.
- Surface latency & quota counters per provider (build atop the existing plan data).
- Expand presets with speech synthesis + translation combos when those adapters
  move past dry-run mode.
