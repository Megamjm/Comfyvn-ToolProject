# Public Language, OCR, Speech, and LLM Providers

Phase 3 introduces feature-flagged adapters for third-party language services and
LLM routing. Everything ships **dry-run first** so Studio workflows, modders, and
automation can validate payloads without contacting external APIs. Enable the
feature flags only after credentials are present and billing ownership is clear.

## Feature Flags

| Flag | Default | Scope |
| --- | --- | --- |
| `enable_public_translate` | `false` | Unlocks `/api/providers/translate/*` endpoints (translation, OCR, speech). |
| `enable_public_llm` | `false` | Unlocks `/api/providers/llm/*` endpoints (registry + dry-run chat router). |

Flags live in `config/comfyvn.json`. Keep them disabled in public builds until
credentials are injected via the secrets store or environment overrides.

## REST Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /api/providers/translate/health` | Consolidated registry covering translation, OCR, and speech adapters. Includes `links.docs`, `links.pricing`, and `last_checked`. |
| `GET /api/providers/translate/public/catalog` | Static catalog extract (pricing heuristics + review snippets) sourced from `comfyvn/public_providers/catalog.py`. |
| `POST /api/providers/translate/public` | Dry-run translation payload. Accepts `{provider, texts, source, target, config}` and echoes the routing plan. |
| `GET /api/providers/llm/registry` | LLM registry with provider diagnostics, model metadata, and tag index. Pricing links surface in `pricing_links`. |
| `GET /api/providers/llm/public/catalog` | Legacy catalog view mirroring the static heuristics in `catalog.py`. |
| `POST /api/providers/llm/chat` | Dry-run chat router. Accepts `{provider, model, messages, ...}` and returns the HTTP dispatch plan without sending traffic. |

Every response includes `feature.feature` / `feature.enabled` so dashboards can
reflect toggle state, and `dry_run: true` to signal that no external requests
occurred.

## Provider Matrix & Pricing Links

### Translation

| Provider | Pricing | Last Checked | Credentials |
| --- | --- | --- | --- |
| Google Cloud Translation | <https://cloud.google.com/translate/pricing> | 2025-01-20 | `COMFYVN_TRANSLATE_GOOGLE_API_KEY` or service account JSON via `COMFYVN_TRANSLATE_GOOGLE_CREDENTIALS`. |
| DeepL API | <https://www.deepl.com/pricing> | 2025-01-20 | `COMFYVN_TRANSLATE_DEEPL_KEY`; optional `COMFYVN_TRANSLATE_DEEPL_ENDPOINT` & `COMFYVN_TRANSLATE_DEEPL_FORMALITY`. |
| Amazon Translate | <https://aws.amazon.com/translate/pricing/> | 2025-01-20 | Standard AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`); region override via `COMFYVN_TRANSLATE_AWS_REGION`. |

### OCR

| Provider | Pricing | Last Checked | Credentials |
| --- | --- | --- | --- |
| Google Cloud Vision | <https://cloud.google.com/vision/pricing> | 2025-01-20 | `COMFYVN_OCR_GOOGLE_API_KEY` or service account JSON (`COMFYVN_OCR_GOOGLE_CREDENTIALS`). |
| AWS Rekognition | <https://aws.amazon.com/rekognition/pricing/> | 2025-01-20 | Standard AWS credentials with optional `COMFYVN_OCR_AWS_REGION`. |

### Speech-to-Text

| Provider | Pricing | Last Checked | Credentials |
| --- | --- | --- | --- |
| Deepgram | <https://deepgram.com/pricing> | 2025-01-20 | `COMFYVN_SPEECH_DEEPGRAM_KEY` or `DEEPGRAM_API_KEY`. |
| AssemblyAI | <https://www.assemblyai.com/pricing> | 2025-01-20 | `COMFYVN_SPEECH_ASSEMBLYAI_KEY` or `ASSEMBLYAI_API_KEY`. |

### LLM Inference

| Provider | Pricing | Last Checked | Credentials |
| --- | --- | --- | --- |
| OpenAI | <https://openai.com/api/pricing> | 2025-01-20 | `COMFYVN_LLM_OPENAI_KEY` / `OPENAI_API_KEY`. Optional `OPENAI_ORG_ID`. |
| Anthropic Claude | <https://www.anthropic.com/api#pricing> | 2025-01-20 | `COMFYVN_LLM_ANTHROPIC_KEY` / `ANTHROPIC_API_KEY`. |
| Google Gemini | <https://ai.google.dev/pricing> | 2025-01-20 | `COMFYVN_LLM_GEMINI_KEY` / `GOOGLE_API_KEY`. |
| OpenRouter | <https://openrouter.ai/pricing> | 2025-01-20 | `COMFYVN_LLM_OPENROUTER_KEY` / `OPENROUTER_API_KEY`. |

Credentials resolve via the encrypted secrets store (`config/comfyvn.secrets.json`)
and respect environment overrides. `/api/providers/translate/health` and
`/api/providers/llm/registry` report which keys are present via the `credentials`
object so modders can validate setup without shell access.

## Dry-Run Behaviour

- Translation adapters echo input text while reporting usage estimates (`characters`)
  and provider-specific config snapshots.
- OCR adapters synthesise bounding boxes + token payloads so layout tooling can
  exercise success paths.
- Speech adapters produce deterministic transcripts, segment timings, and
  confidence scores without decoding audio.
- LLM adapters return the exact HTTP request that *would* be sent (`dispatch`
  object containing method, URL, headers, JSON body).

Use these dry-run payloads in smoke tests, modder tooling, and CI. When the
feature flags remain disabled, responses include `{"ok": false, "reason":
"feature disabled"}`—matching `tools/check_current_system.py` expectations.

## Debug & Modder Hooks

- Secrets access continues to emit `on_security_secret_read` events for audit trails.
- Health endpoints expose structured diagnostics so the diagnostics bundle can be
  refreshed without shelling into the server.
- `/api/providers/llm/chat` responses include `plan.model_info.tags`; use them to
  align module presets with the recommender in `docs/LLM_RECOMMENDATIONS.md`.

## Example Requests

```bash
# Translation registry (dry-run)
curl -s http://127.0.0.1:8001/api/providers/translate/health | jq '.providers.translate[] | {id, credentials_present}'

# Dry-run DeepL translation
curl -s -X POST http://127.0.0.1:8001/api/providers/translate/public \
  -H "Content-Type: application/json" \
  -d '{"provider":"deepl","texts":["Xin chào ComfyVN!"],"source":"vi","target":"en"}' | jq '.items[0]'

# LLM registry
curl -s http://127.0.0.1:8001/api/providers/llm/registry | jq '.models | map(select(.provider=="openai")) | .[0]'

# Dry-run LLM chat
curl -s -X POST http://127.0.0.1:8001/api/providers/llm/chat \
  -H "Content-Type: application/json" \
  -d '{"provider":"openai","model":"gpt-4o-mini","messages":[{"role":"user","content":"Ping"}]}' \
  | jq '.plan.dispatch'
```

## Rollout Notes

- **Secrets**: keep third-party credentials in `config/comfyvn.secrets.json`. Never
  hard-code secrets in config files committed to the repo.
- **Smoke tests**: `tools/check_current_system.py --profile p3_providers_lang_speech_llm`
  validates the new endpoints, flags, and file presence. Run it after enabling
  the feature flags locally.
- **Docs sync**: Update `docs/LLM_RECOMMENDATIONS.md` when adding models or
  module presets so the modder preset UI stays aligned.

