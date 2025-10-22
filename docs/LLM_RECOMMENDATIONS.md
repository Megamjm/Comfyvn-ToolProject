# LLM Registry & Adapter Recommendations

## Current Implementation Snapshot
- Discovery & dry-runs live under `/api/llm/{registry,runtime,test-call}`; the production `/api/llm/chat` proxy and prompt-pack routes are still pending.
- Provider metadata originates from `comfyvn/models/registry.json`. Each provider includes `name`, `adapter`, `base`, `models[].tags`, optional `settings`, and human-readable `metadata`.
- Runtime adapters register in-memory via `POST /api/llm/runtime/register`, letting modders point at proxies or local sandboxes without mutating the on-disk registry.
- `POST /api/llm/test-call` accepts `{ "registry_id": "<provider>", "model": "<id>", "messages": [...] }` (mirrors OpenAI schema). When a provider is missing or `registry_id` is `stub`, the response echoes the last user message to keep CI/panels deterministic.
- Prompt-pack schemas live in `docs/PROMPT_PACKS/` (POV rewrite, battle narration); pair them with the templates in `comfyvn/models/prompt_packs/` until the public prompt-pack router ships.

```bash
curl -s http://127.0.0.1:8000/api/llm/registry | jq '.providers[] | {name, models}'
curl -s -X POST http://127.0.0.1:8000/api/llm/runtime/register \
  -H "Content-Type: application/json" \
  -d '{"id": "lmstudio-dev", "provider": "lmstudio_local", "label": "LM Studio Dev", "modes": ["chat"]}'
curl -s -X POST http://127.0.0.1:8000/api/llm/test-call \
  -H "Content-Type: application/json" \
  -d '{"registry_id": "stub", "messages": [{"role": "user", "content": "Ping"}]}' | jq '.data'
```

## Registry Structure & Overrides
- `defaults.provider` / `defaults.model` supply global fallbacks.
- `defaults.modules.<module>` stores per-module `{provider, model, options}`; expand this map when introducing new presets.
- Environment overrides:
  - `COMFYVN_LLM_<PROVIDER>_BASE_URL`, `_API_KEY`, `_HEADERS`, `_TIMEOUT`
  - `COMFYVN_LLM_DEFAULT_TIMEOUT`
- Feature flags: keep any future public connectors disabled by default (`config/comfyvn.json → features.*`). External services should also support a dry-run mode to avoid involuntary billing.

## Debug & API Hooks
- Logs: adapter requests bubble through `requests` exceptions—run with `COMFYVN_LOG_LEVEL=DEBUG` to capture request URLs and status codes (written to `logs/server.log`).
- Modder hooks:
  - `comfyvn.models.registry.iter_providers()` for offline introspection.
  - `comfyvn.models.adapters.stub.StubAdapter` ensures GUI smoke tests never require network access.
  - `comfyvn/emulation/engine.py` consumes registry defaults when dispatching persona modules; keep module tags up to date.
- Dry-run safety: rely on `/api/llm/test-call` or the stub adapter inside tests/CI to guarantee deterministic replies.

## Module Preset Shortlists (Top 10 Each)

### Translate (JSON-first)
1. **OpenAI `gpt-4.1-mini`** — temp 0.1, top_p 0.8, JSON schema enforcing `{detected_language, translation}`; balanced cost/quality.
2. **OpenAI `gpt-4o-mini`** — temp 0.15, top_p 0.85; fast UI localisation.
3. **Anthropic `claude-3-haiku-20240307`** — temp 0.2, top_p 0.8; disable thinking, enforce JSON blocks.
4. **Anthropic `claude-3.5-sonnet-20240620`** — temp 0.2, top_p 0.85; long context with deterministic output.
5. **Google `gemini-1.5-flash`** — temp 0.15, top_p 0.6; set `response_mime_type="application/json"`.
6. **Google `gemini-1.5-pro`** — temp 0.1, top_p 0.4; suited for large docs.
7. **Azure OpenAI `gpt-4o-mini` (deployment)** — temp 0.15, top_p 0.85; include `api-version=2024-06-01`.
8. **Azure OpenAI `gpt-35-turbo`** — temp 0.1, top_p 0.7; budget translation batches.
9. **OpenRouter `google/gemini-flash-1.5`** — temp 0.15, top_p 0.6; requires `X-Title` header.
10. **OpenRouter `mistralai/mistral-large-2`** — temp 0.2, top_p 0.75; deterministic fallback.

### VN Chat (Roleplay)
1. **OpenAI `gpt-4o`** — temp 0.65, top_p 0.95; expressive dialogue.
2. **OpenAI `gpt-4.1`** — temp 0.6, top_p 0.9; strong reasoning.
3. **OpenAI `gpt-4.1-mini`** — temp 0.7, top_p 0.95; budget-friendly.
4. **Anthropic `claude-3.5-sonnet-20240620`** — temp 0.65, top_p 0.95; long coherent turns.
5. **Anthropic `claude-3-opus-20240229`** — temp 0.55, top_p 0.9; narrative consistency.
6. **Google `gemini-1.5-pro`** — temp 0.7, top_p 0.95; supply safety tuning.
7. **Azure OpenAI `gpt-4o`** — temp 0.65, top_p 0.95; enterprise compliance.
8. **OpenRouter `meta-llama/llama-3.1-70b-instruct`** — temp 0.75, top_p 0.95; open-weight fallback.
9. **OpenRouter `perplexity/llama-3.1-sonar-large-128k-chat`** — temp 0.6, top_p 0.9; retrieval-friendly.
10. **OpenRouter `qwen/qwen-2.5-72b-instruct`** — temp 0.7, top_p 0.92; multilingual roleplay.

### Narrator (Voice-over JSON payloads)
1. **OpenAI `gpt-4.1`** — temp 0.6, top_p 0.92; output `{ "narration": "..." }`.
2. **OpenAI `gpt-4o`** — temp 0.7, top_p 0.94; add `presence_penalty=0.6`.
3. **OpenAI `gpt-4.1-mini`** — temp 0.7, top_p 0.95; rapid drafts.
4. **Anthropic `claude-3.5-opus-20240808`** — temp 0.65, top_p 0.9; disable thinking.
5. **Anthropic `claude-3.5-sonnet`** — temp 0.7, top_p 0.95; lyrical tone.
6. **Google `gemini-1.5-pro`** — temp 0.75, top_p 0.96; set `response_mime_type`.
7. **Google `gemini-1.5-ultra`** — temp 0.65, top_p 0.9; extended context.
8. **Azure OpenAI `gpt-4o`** — temp 0.7, top_p 0.94; telemetry integration.
9. **OpenRouter `meta-llama/llama-3.1-405b-instruct`** — temp 0.62, top_p 0.9; premium quality.
10. **OpenRouter `nousresearch/hermes-3-llama-3.1-70b`** — temp 0.72, top_p 0.95; descriptive prose.

### Worldbuild (Structured Lore)
1. **OpenAI `gpt-4.1`** — temp 0.45, top_p 0.75; schema with `regions`, `factions`, `hooks`.
2. **OpenAI `gpt-4o`** — temp 0.5, top_p 0.8; extend `max_tokens` to 2048.
3. **OpenAI `gpt-4.1-mini`** — temp 0.5, top_p 0.82; budget world notes.
4. **Anthropic `claude-3.5-sonnet`** — temp 0.45, top_p 0.78; tool schema required.
5. **Anthropic `claude-3-opus`** — temp 0.4, top_p 0.75; consistency focus.
6. **Google `gemini-1.5-pro`** — temp 0.5, top_p 0.7; output arrays for biomes/events.
7. **Google `gemini-1.5-flash`** — temp 0.55, top_p 0.75; iterative ideation.
8. **Azure OpenAI `gpt-4o`** — temp 0.48, top_p 0.78; enterprise use.
9. **OpenRouter `perplexity/sonar-medium-chat`** — temp 0.5, top_p 0.8; retrieval-enhanced lore.
10. **OpenRouter `mistralai/mixtral-8x22b-instruct`** — temp 0.52, top_p 0.82; deterministic long outputs.

### Battle Narration (Action summaries)
1. **OpenAI `gpt-4o`** — temp 0.75, top_p 0.94; schema `{summary, next_hooks[]}`.
2. **OpenAI `gpt-4.1`** — temp 0.7, top_p 0.9; add `frequency_penalty=0.2`.
3. **OpenAI `gpt-4.1-mini`** — temp 0.8, top_p 0.96; quick recaps.
4. **Anthropic `claude-3.5-sonnet`** — temp 0.78, top_p 0.96; balanced creativity.
5. **Anthropic `claude-3.5-haiku-20241001`** — temp 0.82, top_p 0.97; streaming friendly.
6. **Google `gemini-1.5-flash`** — temp 0.85, top_p 0.98; low-latency overlays.
7. **Google `gemini-1.5-pro`** — temp 0.8, top_p 0.95; tactical detail focus.
8. **Azure OpenAI `gpt-4o`** — temp 0.78, top_p 0.94; telemetry ready.
9. **OpenRouter `meta-llama/llama-3.1-70b-instruct`** — temp 0.82, top_p 0.96; long combat logs.
10. **OpenRouter `deepseek/deepseek-chat`** — temp 0.85, top_p 0.97; cost-effective action beats.

## Pricing & Credential Notes (Oct 2024)
- **OpenAI**: GPT‑4.1 ≈ $60/$120 (in/out) per 1M tokens, GPT‑4o $5/$15, GPT‑4o-mini $0.15/$0.60. Use `COMFYVN_LLM_OPENAI_PUBLIC_API_KEY`.
- **Anthropic**: Claude 3.5 Sonnet $3/$15, Claude 3.5 Haiku $1/$5. Requires `COMFYVN_LLM_ANTHROPIC_PUBLIC_API_KEY` + `anthropic-version` header.
- **Google Gemini**: 1.5 Flash $0.35/$1.05, 1.5 Pro $3.50/$10.50 (per 1M). Mirror `GOOGLE_API_KEY` into `COMFYVN_LLM_GOOGLE_GEMINI_API_KEY`.
- **Azure OpenAI**: Region-specific (e.g., GPT‑4o $5/$15). Configure `COMFYVN_LLM_AZURE_OPENAI_BASE_URL`, `_API_KEY`, and deployment name in provider settings.
- **OpenRouter**: Adds ~15 % platform fee; include `COMFYVN_LLM_OPENROUTER_API_KEY` and set optional `COMFYVN_LLM_OPENROUTER_HEADERS` for referer/title metadata.

## Roadmap & Next Steps
- Implement `/api/llm/chat` with schema validation, module-aware defaults, mock mode, and request IDs for logging.
- Expose `/api/llm/prompt-pack/{module}` once schema support lands, reusing the markdown + specs already tracked in `docs/PROMPT_PACKS/` and `comfyvn/models/prompt_packs/`.
- Extend `comfyvn/public_providers/` with adapters for OpenAI, Anthropic, Google Gemini, Azure OpenAI, and OpenRouter, including health checks for `/api/llm/registry?diagnostics=1`.
- Update `config/comfyvn.json` feature flags and documentation when public connectors ship; ensure dry-run toggles are present for all paid integrations.
