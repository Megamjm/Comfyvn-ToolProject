# Public LLM Router & Top-10 Module Presets — 2025-10-21

## Intent
- Expose a public-friendly LLM router that can fan out to OpenAI, Anthropic, Google Gemini, Azure OpenAI, and OpenRouter while keeping adapters pluggable and mockable.
- Curate per-module presets (Translate, VN Chat, Narrator, Worldbuild, Battle narration) with JSON-first schemas, sensible temperatures, and clear provenance so Studio tooling can swap providers without code edits.
- Align `docs/LLM_RECOMMENDATIONS.md` and future release notes with up-to-date pricing/practical guidance for the selected public endpoints.

## Current Wiring
- `comfyvn/server/routes/llm.py` only exposes registry/runtime helpers (`/registry`, `/runtime/*`, `/test-call`) and lacks the documented `/api/llm/chat` or prompt-pack endpoints (`@router.post("/chat")` never landed). `docs/development/emulation_and_llm.md#L21` and README claims are out-of-sync with code.
- Providers are materialised from `comfyvn/models/registry.json`, which today seeds LM Studio, Ollama, and Anthropic samples. Tags already drive module dispatch through `comfyvn/emulation/engine.py:178`, but defaults only cover `translate`, `worldbuild`, `persona`, and `narrator`.
- Adapter coverage lives under `comfyvn/models/adapters/` (OpenAI-compatible, Anthropic, LM Studio, Ollama, proxy, stub). There is no dedicated public-provider namespace (`comfyvn/public_providers/**/*.py`) yet; Google Gemini, Azure, and OpenRouter require bespoke request/response handling.
- The registry API already returns runtime metadata: `/api/llm/registry` emits provider descriptors plus `runtime_registry.snapshot()`. That is sufficient for discovery once new providers/models are registered.
- `docs/LLM_RECOMMENDATIONS.md` is a high-level note without per-module tables, JSON schema examples, or cost guidance, so teams currently guess defaults when wiring new modules.

## Gaps & TODO Highlights
- Implement a production `/api/llm/chat` router that mirrors the acceptance criteria (payload validation, adapter dispatch, mock-mode fallback) and reconciles the documentation promises.
- Break provider-specific HTTP plumbing out into `comfyvn/public_providers/llm_<provider>.py` so we can share auth/header helpers, price metadata, and discovery logic without bloating the neutral adapter layer.
- Extend `comfyvn/models/registry.json` (and schema helpers) to capture:
  - Cloud-friendly provider slugs (`openai_public`, `anthropic_public`, `google_gemini`, `azure_openai`, `openrouter_hub`).
  - Model metadata: human labels, descriptive tags (`json-only`, `low-latency`, `long-context`, `voice-ready`), per-module defaults, and optional pricing notes.
- JSON schema presets per module (`defaults.modules.<module>.schema`) so `/api/llm/chat` can opt-in automatically.
- Refresh `docs/LLM_RECOMMENDATIONS.md` with the curated top-10 lists, pricing snapshots, and environment variable callouts (e.g. `COMFYVN_LLM_OPENAI_PUBLIC_API_KEY`, `COMFYVN_LLM_AZURE_OPENAI_BASE_URL`).

## Documentation Sweep — 2025-11-08
- Updated `README.md`, `architecture.md`, `CHANGELOG.md`, `docs/LLM_RECOMMENDATIONS.md`, `docs/development_notes.md`, `docs/dev_notes_modder_hooks.md`, and `docs/development/emulation_and_llm.md` to reflect the current `/api/llm/{registry,runtime,test-call}` surface and to spell out the pending chat/prompt-pack work.
- Added module shortlists, pricing snapshots, and sample curls for discovery/test-call workflows so contributors can hook into the registry without waiting for the full router.
- Embedded the verification checklist (below) for PR hand-off; leave boxes unchecked until implementation closes each item.

## Touchpoints (A/B Split)
- **Router (A-track)**: finish `/api/llm/chat` under `comfyvn/server/routes/llm.py` or move it into a new `comfyvn/server/routes/providers_llm.py` that owns request validation, provider resolution, schema enforcement, and stub fallbacks. Acceptance requires at least one working adapter in mock mode (the existing `StubAdapter` is fine for CI).
- **Providers (A-track)**: add `comfyvn/public_providers/llm_openai.py`, `llm_anthropic.py`, `llm_google_gemini.py`, `llm_azure_openai.py`, and `llm_openrouter.py` with helpers to:
  - Construct base URLs + headers from env vars.
  - List canonical model IDs and surface price metadata for `/api/llm/registry`.
  - Map convenience flags (`response_format`, `json_schema`, `request_id`) to the neutral adapter kwargs.
- **Adapters (A-track)**: consider thin wrappers or settings tweaks:
  - Azure OpenAI can reuse `OpenAICompatAdapter` if we inject the deployment path + `api-version`. Provide a shim that rewrites `model`→`deployment_name`.
  - Google Gemini needs a B-side adapter (or compatibility wrapper) that POSTs to `models/{model}:generateContent` and normalises the block structure to `ChatResult.reply`.
  - OpenRouter rides the OpenAI schema but mandates `HTTP-Referer` + `X-Title` headers; capture those in metadata.
- **Presets (B-track)**: update `comfyvn/models/registry.json` `defaults.modules` with the curated presets and attach any JSON schema snippets (e.g. `{"type": "object","properties":{"response":{"type":"string"}}}`) that the router can forward via adapter kwargs.
- **Docs (B-track)**: expand `docs/LLM_RECOMMENDATIONS.md` with tables, schema snippets, and pricing blurbs. Cross-link from `architecture.md` and release notes once the router ships.

## Router Implementation Notes
- Payload contract: accept `{provider?, model?, module?, messages, params?, schema?, mock?}`. When `mock` is truthy or the resolved provider is `stub`, bypass network and echo replies for smoke tests.
- Context merging: reuse the emulation engine defaults (`engine.plan_dispatch`) so module hints (`"translate"`, `"battle_narration"`) automatically pick the new presets. Expose `context` echoes (e.g. persona metadata) for observability.
- Error handling: map adapter failures to HTTP 502 with the adapter message; schema/validation issues stay 400. Include request IDs so logs tie back to provider diagnostics.
- Telemetry: consider tagging replies with `{provider, model, pricing_hint}` so Studio can surface per-turn cost estimates without hitting provider dashboards.

## Module Top-10 Shortlists (JSON-friendly)

### Translate
1. OpenAI `gpt-4.1-mini` — temp 0.1, top_p 0.8, `response_format={"type":"json_schema","json_schema":{"name":"translation","schema":{"type":"object","properties":{"detected_language":{"type":"string"},"translation":{"type":"string"}},"required":["translation"]}}}`. Excellent quality/cost balance for bilingual UI copy.
2. OpenAI `gpt-4o-mini` — temp 0.15, top_p 0.85, same schema; faster for UI pipelines with modest context.
3. Anthropic `claude-3-haiku-20240307` — temp 0.2, top_p 0.8, use `anthropic_beta={"thinking":{"type":"disabled"}}` and tool schema with `json` block requirement.
4. Anthropic `claude-3-5-sonnet-20240620` — temp 0.2, top_p 0.85, streaming ready; higher fidelity + long context.
5. Google `gemini-1.5-flash` — temperature 0.15, top_p 0.6, set `response_mime_type="application/json"` with schema above.
6. Google `gemini-1.5-pro` — temp 0.1, top_p 0.4, same schema; use for longer documents (>32k tokens).
7. Azure OpenAI `gpt-4o-mini` deployment — temp 0.15, top_p 0.85, specify `api-version=2024-06-01`. Mirrors OpenAI mini quality with Azure billing.
8. Azure OpenAI `gpt-35-turbo` deployment — temp 0.1, top_p 0.7; cost-effective fallback for bulk localisation.
9. OpenRouter `google/gemini-flash-1.5` — temp 0.15, top_p 0.6, ensure `X-Title` header; leverages OpenRouter credit pricing.
10. OpenRouter `mistralai/mistral-large-2` — temp 0.2, top_p 0.75, specify `response_format` JSON. Good for deterministic translations when OpenAI unavailable.

### VN Chat (Roleplay-friendly dialogue)
1. OpenAI `gpt-4o` — temp 0.65, top_p 0.95, optional JSON schema for structured replies when needed; natural voice and expressive tone.
2. OpenAI `gpt-4.1` — temp 0.6, top_p 0.9, strong reasoning for branching dialogue.
3. OpenAI `gpt-4.1-mini` — temp 0.7, top_p 0.95, budget-friendly alt retaining emoji-rich style.
4. Anthropic `claude-3.5-sonnet-20240620` — temp 0.65, top_p 0.95, set `system` persona primer; excels at long, coherent turns.
5. Anthropic `claude-3-opus-20240229` — temp 0.55, top_p 0.9, slower but maintains plot consistency.
6. Google `gemini-1.5-pro` — temp 0.7, top_p 0.95, supply safety settings to keep tone aligned; responses via `candidates[0].content`.
7. Azure OpenAI `gpt-4o` deployment — temp 0.65, top_p 0.95, tie into enterprise compliance.
8. OpenRouter `meta-llama/llama-3.1-70b-instruct` — temp 0.75, top_p 0.95, set JSON schema for optional metadata; good open-weight fallback.
9. OpenRouter `perplexity/llama-3.1-sonar-large-128k-chat` — temp 0.6, top_p 0.9, integrates retrieval-flavoured replies.
10. OpenRouter `qwen/qwen-2.5-72b-instruct` — temp 0.7, top_p 0.92, strong multilingual roleplay with manageable cost.

### Narrator (First-person storytelling voice-over)
1. OpenAI `gpt-4.1` — temp 0.6, top_p 0.92, schema ensures `{ "narration": "..." }` output for downstream TTS.
2. OpenAI `gpt-4o` — temp 0.7, top_p 0.94, expressive but fast; include `presence_penalty=0.6`.
3. OpenAI `gpt-4.1-mini` — temp 0.7, top_p 0.95, rapid iteration for storyboards.
4. Anthropic `claude-3.5-opus-20240808` — temp 0.65, top_p 0.9, use `thinking` disabled and request JSON block.
5. Anthropic `claude-3.5-sonnet` — temp 0.7, top_p 0.95, mixes lyric tone with speed.
6. Google `gemini-1.5-pro` — temp 0.75, top_p 0.96, set `safetySettings` to `BLOCK_NONE` for adventurous tone; JSON via `response_mime_type`.
7. Google `gemini-1.5-ultra` (if allow-listed) — temp 0.65, top_p 0.9, long-form narration for >16k tokens.
8. Azure OpenAI `gpt-4o` deployment — temp 0.7, top_p 0.94, integrates with Azure monitor logging.
9. OpenRouter `meta-llama/llama-3.1-405b-instruct` — temp 0.62, top_p 0.9, high narrative quality when credit budget allows.
10. OpenRouter `nousresearch/hermes-3-llama-3.1-70b` — temp 0.72, top_p 0.95, emphasises descriptive prose; enforce JSON with `response_format`.

### Worldbuild (Structured lore generation)
1. OpenAI `gpt-4.1` — temp 0.45, top_p 0.75, JSON schema capturing `regions`, `factions`, `hooks`.
2. OpenAI `gpt-4o` — temp 0.5, top_p 0.8, enlarge `max_tokens` to 2048 for multi-section output.
3. OpenAI `gpt-4.1-mini` — temp 0.5, top_p 0.82, budget-friendly but still structured.
4. Anthropic `claude-3.5-sonnet` — temp 0.45, top_p 0.78, use `tool_choice="required"` with JSON schema.
5. Anthropic `claude-3-opus` — temp 0.4, top_p 0.75, slower but great for consistency.
6. Google `gemini-1.5-pro` — temp 0.5, top_p 0.7, output as JSON with arrays for biomes/encounters.
7. Google `gemini-1.5-flash` — temp 0.55, top_p 0.75, quick iterative ideation.
8. Azure OpenAI `gpt-4o` deployment — temp 0.48, top_p 0.78, enterprise friendly.
9. OpenRouter `perplexity/sonar-medium-chat` — temp 0.5, top_p 0.8, includes retrieval-style suggestions.
10. OpenRouter `mistralai/mixtral-8x22b-instruct` — temp 0.52, top_p 0.82, deterministic long outputs with JSON support.

### Battle Narration (Action-heavy summaries)
1. OpenAI `gpt-4o` — temp 0.75, top_p 0.94, schema: `{ "summary": "...", "next_hooks": [...] }`.
2. OpenAI `gpt-4.1` — temp 0.7, top_p 0.9, add `frequency_penalty=0.2` to avoid repetition.
3. OpenAI `gpt-4.1-mini` — temp 0.8, top_p 0.96, fast adrenaline recaps.
4. Anthropic `claude-3.5-sonnet` — temp 0.78, top_p 0.96, maintain momentum with balanced creativity.
5. Anthropic `claude-3.5-haiku-20241001` (beta) — temp 0.82, top_p 0.97, streaming friendly for live commentary.
6. Google `gemini-1.5-flash` — temp 0.85, top_p 0.98, lower latency for real-time overlays.
7. Google `gemini-1.5-pro` — temp 0.8, top_p 0.95, emphasise tactical details; JSON for damage logs.
8. Azure OpenAI `gpt-4o` deployment — temp 0.78, top_p 0.94, integrate with telemetry dashboards.
9. OpenRouter `meta-llama/llama-3.1-70b-instruct` — temp 0.82, top_p 0.96, reliable long context for combat logs.
10. OpenRouter `deepseek/deepseek-chat` — temp 0.85, top_p 0.97, low cost for repeated action beats, ensure JSON response via `response_format`.

## Pricing & Credential Reminders (Oct 2024 snapshots)
- **OpenAI**: GPT-4.1 — ~$60 / $120 per 1M input/output tokens; GPT-4o — $5 / $15; GPT-4o-mini — $0.15 / $0.60. Set `COMFYVN_LLM_OPENAI_PUBLIC_API_KEY`.
- **Anthropic**: Claude 3.5 Sonnet — $3 / $15; Claude 3.5 Haiku — $1 / $5. Use `COMFYVN_LLM_ANTHROPIC_PUBLIC_API_KEY` plus `anthropic-version=2023-06-01`.
- **Google Gemini**: Gemini 1.5 Flash — $0.35 / $1.05; Gemini 1.5 Pro — $3.50 / $10.50 (cached tiers optional). API key via `GOOGLE_API_KEY` mirrored to `COMFYVN_LLM_GOOGLE_GEMINI_API_KEY`.
- **Azure OpenAI**: Region-specific, e.g. GPT-4o $5 / $15 per 1M tokens; set `COMFYVN_LLM_AZURE_OPENAI_BASE_URL`, `COMFYVN_LLM_AZURE_OPENAI_API_KEY`, and include deployment name in `settings`.
- **OpenRouter**: Adds ~15% platform fee; popular models price-match source providers. Requires `COMFYVN_LLM_OPENROUTER_API_KEY` and optional `COMFYVN_LLM_OPENROUTER_HEADERS` for referer/title.

## Acceptance Hooks
- `GET /api/llm/registry` must emit every provider with `models[].tags` populated, `metadata.pricing` (optional), and module defaults referencing the new top-10 entries.
- `POST /api/llm/chat` should succeed in mock mode by targeting the `stub` provider (or `mock: true` flag) and echoing a deterministic reply, satisfying CI without external network calls.
- Documentation updates should capture presets, schemas, and pricing so Studio operators know how to enable each provider and interpret router responses.

## Debug & Rollout Notes
- Add unit tests around the router to cover JSON schema injection and adapter error surfaces. Existing `llm_test_call` helper can act as a smoke-test path for real providers.
- Surface provider health checks (optional) by teaching `comfyvn/public_providers` helpers to ping `/models` or `/v1/models` endpoints; expose results via `/api/llm/registry?diagnostics=1`.
- Keep feature-flags in mind: router endpoints remain active even when the emulation engine is disabled, so guard server logs to avoid confusion.
- When shipping presets, record any schema changes in `CHANGELOG.md` and include quick cURL samples in `docs/LLM_RECOMMENDATIONS.md` for each module.

## Debug & Verification Checklist
- [ ] **Docs updated**: README, architecture, CHANGELOG, /docs notes (what changed + why)
- [ ] **Feature flags**: added/persisted in `config/comfyvn.json`; OFF by default for external services
- [ ] **API surfaces**: list endpoints added/modified; include sample curl and expected JSON
- [ ] **Modder hooks**: events/WS topics emitted (e.g., `on_scene_enter`, `on_asset_saved`)
- [ ] **Logs**: structured log lines + error surfaces (path to `.log`)
- [ ] **Provenance**: sidecars updated (tool/version/seed/workflow/pov)
- [ ] **Determinism**: same seed + same vars + same pov ⇒ same next node
- [ ] **Windows/Linux**: sanity run on both (or mock mode on CI)
- [ ] **Security**: secrets only from `config/comfyvn.secrets.json` (git-ignored)
- [ ] **Dry-run mode**: for any paid/public API call
