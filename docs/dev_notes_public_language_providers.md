# Public Language Provider Hooks (Dry-Run)

Date: 2025-12-10 • Updated: 2025-12-10 • Owner: Project Integration & Docs (Public APIs)

This note captures the public translation, OCR, speech, and LLM adapters introduced
for Phase 3. Every route defaults to dry-run behaviour while `enable_public_translate`
and `enable_public_llm` remain `false`, allowing Studio tooling, modders, and CI to
exercise payload shapes without incurring API costs.

## Feature Flags & Secrets

- Feature flags (Settings → Debug & Feature Flags):
  - `enable_public_translate`
  - `enable_public_llm`
- Configuration landing points:
  - `config/comfyvn.json` persists the flags.
  - Secrets land in `config/comfyvn.secrets.json` (encrypted) or environment overrides.
- Secrets resolution order (per provider):
  - Translation:
    - Google Cloud: `COMFYVN_TRANSLATE_GOOGLE_API_KEY`, `COMFYVN_TRANSLATE_GOOGLE_CREDENTIALS`, `GOOGLE_APPLICATION_CREDENTIALS`.
    - DeepL: `COMFYVN_TRANSLATE_DEEPL_KEY`, optional `COMFYVN_TRANSLATE_DEEPL_ENDPOINT`, `COMFYVN_TRANSLATE_DEEPL_FORMALITY`.
    - Amazon: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, optional `COMFYVN_TRANSLATE_AWS_REGION`.
  - OCR:
    - Google Vision: `COMFYVN_OCR_GOOGLE_API_KEY`, `COMFYVN_OCR_GOOGLE_CREDENTIALS`, `GOOGLE_APPLICATION_CREDENTIALS`.
    - AWS Rekognition: standard AWS keys, optional `COMFYVN_OCR_AWS_REGION`.
  - Speech:
    - Deepgram: `COMFYVN_SPEECH_DEEPGRAM_KEY`, `DEEPGRAM_API_KEY`.
    - AssemblyAI: `COMFYVN_SPEECH_ASSEMBLYAI_KEY`, `ASSEMBLYAI_API_KEY`.
  - LLM:
    - OpenAI: `COMFYVN_LLM_OPENAI_KEY`, `OPENAI_API_KEY`, optional `OPENAI_ORG_ID`.
    - Anthropic: `COMFYVN_LLM_ANTHROPIC_KEY`, `ANTHROPIC_API_KEY`.
    - Google Gemini: `COMFYVN_LLM_GEMINI_KEY`, `GOOGLE_API_KEY`.
    - OpenRouter: `COMFYVN_LLM_OPENROUTER_KEY`, `OPENROUTER_API_KEY`.

## Routes & Payloads

| Route | Summary | Notes |
| --- | --- | --- |
| `GET /api/providers/translate/health` | Aggregated translation/OCR/speech registry. | Returns `providers.translate|ocr|speech[]` with pricing links, last-checked timestamps, and `credentials` snapshots. |
| `GET /api/providers/translate/public/catalog` | Static heuristics from `catalog.py`. | Useful when the feature flag stays off but docs want pricing copy. |
| `POST /api/providers/translate/public` | Dry-run translation payload. | Body: `{provider, texts, source, target, config}`. Response echoes items + usage. |
| `GET /api/providers/llm/registry` | LLM provider diagnostics + model index. | Includes `tags` for filtering UI presets. |
| `GET /api/providers/llm/public/catalog` | Static heuristics for docs/UI. | Mirrors legacy `/catalog` behaviour. |
| `POST /api/providers/llm/chat` | Dry-run chat router. | Returns `plan.dispatch` (method/url/headers/json) and `plan.model_info`. |

All responses emit `dry_run: true`. When feature flags are disabled the routes
return `{"ok": false, "reason": "feature disabled"}` so integration tests can
assert guardrails.

## Debug Workflow

1. Ensure `config/comfyvn.secrets.json` is populated (or export env vars).
2. Toggle `enable_public_translate` / `enable_public_llm` via Settings or by editing `config/comfyvn.json`.
3. Hit the health endpoints to confirm credentials resolve:
   ```bash
   curl -s http://127.0.0.1:8001/api/providers/translate/health | jq '.providers.translate[] | {id,credentials_present}'
   curl -s http://127.0.0.1:8001/api/providers/llm/registry | jq '.providers[] | {id,credentials_present}'
   ```
4. Exercise dry-run payloads before switching anything live:
   ```bash
   curl -s -X POST http://127.0.0.1:8001/api/providers/translate/public \
     -H "Content-Type: application/json" \
     -d '{"provider":"amazon_translate","texts":["Xin chào"],"source":"vi","target":"en"}' | jq '.usage'

   curl -s -X POST http://127.0.0.1:8001/api/providers/llm/chat \
     -H "Content-Type: application/json" \
     -d '{"provider":"openrouter","model":"openrouter/google/gemma-2-9b-it","messages":[{"role":"user","content":"Ping"}]}' \
     | jq '.plan.dispatch'
   ```
5. Watch `logs/server.log` (with `COMFYVN_LOG_LEVEL=INFO`) for `public.translate.*`
   and `public.llm.*` log lines when the feature flags are enabled.

## Modder Hooks & Automation

- Secrets access still emits `on_security_secret_read`; pair with health endpoint
  payloads to build dashboards without leaking values.
- Surface registry data inside Studio's Debug channel or external dashboards by
  caching the `pricing_links` and `tags` returned by the registry endpoints.
- When routing live traffic in future phases, reuse the dry-run payload as a base
  for actual HTTP requests so logging/tests stay aligned (`plan.dispatch` already
  matches the upstream schema).

## QA Checklist

- [ ] `tools/check_current_system.py --profile p3_providers_lang_speech_llm` passes.
- [ ] Feature flags remain `false` in committed config files.
- [ ] Docs updated: `README.md`, `architecture.md`, `architecture_updates.md`, `docs/PROVIDERS_LANG_SPEECH_LLM.md`, `docs/LLM_RECOMMENDATIONS.md`.
- [ ] Health endpoints show `credentials_present=false` when keys are absent and `true` once env/secrets are configured.

