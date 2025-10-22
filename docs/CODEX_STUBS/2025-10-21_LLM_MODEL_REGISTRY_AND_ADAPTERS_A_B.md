# LLM Model Registry & Adapters — 2025-10-21

## Overview
- Deliver a provider-neutral registry for local and remote LLM endpoints with tag metadata supporting Studio modules (`chat`, `translate`, `worldbuild`, `json`, `long-context`).
- Implement adapter abstractions for OpenAI-compatible APIs, LM Studio, Ollama, Anthropic-compatible gateways, and OpenRouter-style pass-through.
- Expose FastAPI routes for registry discovery and chat proxies so dashboards, importers, and automation scripts can reuse the same entrypoints.

## References
- `comfyvn/models/registry.json` — seeded provider list, defaults, and documentation-friendly metadata.
- `comfyvn/models/adapters/*` — adapter base + provider implementations; see `Adapter.chat()` contract.
- `docs/LLM_RECOMMENDATIONS.md` — per-module parameter guidance and cURL samples for contributors.

## Registry Implementation
- Create `comfyvn/models/registry.json` with provider entries (`name`, `adapter`, `base`, `models`, `tags`, `headers`, `settings`, `meta`), plus tag-specific defaults under `defaults.{chat,translate,worldbuild,json,long-context}`.
- Implement `comfyvn/models/registry.py` to load, validate, and cache the registry; expose `resolve_provider`, `iter_providers`, and `iter_models`.
- Support environment overrides per provider: `COMFYVN_LLM_<PROVIDER>_{BASE_URL,API_KEY,HEADERS,TIMEOUT}` and global `COMFYVN_LLM_DEFAULT_TIMEOUT`.

## Adapter Layer
- Base class `Adapter` encapsulates URL resolution, header management, timeouts, and `ChatResult` shape (`reply`, `raw`, `usage`, `status`).
- Implement provider-specific subclasses:
  - `OpenAICompatAdapter` — hits `/chat/completions`, extracts primary reply, translates `choices`/`usage`.
  - `LMStudioAdapter` — extends OpenAI-compatible defaults with LM Studio-specific path.
  - `OllamaAdapter` — maps to `/api/chat`, supports `options`, and normalises message schema.
  - `AnthropicCompatAdapter` — targets `/messages`, sets `x-api-key` + `anthropic-version`, handles content blocks, and enforces `max_tokens`.
- Register adapters via `comfyvn/models/adapters/__init__.py`, exposing `create_adapter` and `adapter_from_config`.

## API Surface
- Add `comfyvn/server/routes/llm.py` with:
  - `GET /api/llm/registry` — returns provider list, tags, metadata, and defaults for client discovery.
  - `POST /api/llm/chat` — validates payload (`provider`, `model`, `messages`, optional `params`, `adapter override`), resolves the provider, instantiates the adapter, and returns `reply`, `raw`, and `usage`.
- Wire adapter errors to HTTP 400/502 responses for predictable failure semantics.

## Documentation & Acceptance
- Update `README.md`, `architecture.md`, `architecture_updates.md`, `CHANGELOG.md`, `docs/development_notes.md`, and `docs/dev_notes_modder_hooks.md` with registry/adapters overview, debug hooks, and env override notes.
- Add `docs/LLM_RECOMMENDATIONS.md` to document tag defaults, module guidance, and quick tests.
- Acceptance checks:
  1. `GET /api/llm/registry` lists providers with tag metadata and defaults.
  2. `POST /api/llm/chat` succeeds against at least one adapter (mock/local) and surfaces adapter errors cleanly.
  3. Documentation highlights registry usage, adapter wiring, and modder-facing hooks.

