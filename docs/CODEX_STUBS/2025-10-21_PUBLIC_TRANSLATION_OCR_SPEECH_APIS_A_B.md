# Public Translation, OCR, Speech APIs — 2025-10-21

## Intent
- Stand up production-ready adapters for public translation, OCR/CV, and speech-to-text services with uniform response schemas so Studio tools can swap vendors without UI rewrites.
- Provide diagnostics endpoints (`/api/providers/translate/test`, etc.) that verify credentials, surface current plan/quota metadata, and degrade gracefully when keys are missing.
- Keep localisation primitives (translation memory, TM review UI, importers) untouched: network adapters plug in as optional accelerators layered over the existing cache + stub fallbacks.

## Touchpoints
- `comfyvn/public_providers/translate_google.py` — Google Cloud Translation v3 client and quota probes.
- `comfyvn/public_providers/translate_deepl.py` — DeepL API Free/Pro adapter with usage inspection.
- `comfyvn/public_providers/translate_amazon.py` — Amazon Translate (SigV4) adapter with region-aware config.
- `comfyvn/public_providers/ocr_google_vision.py` — Google Vision `images:annotate` wrapper for OCR payloads.
- `comfyvn/public_providers/ocr_aws_rekognition.py` — AWS Rekognition `DetectText` adapter plus collection helpers.
- `comfyvn/public_providers/speech_deepgram.py` — Deepgram streaming/batch STT bridge with tier detection.
- `comfyvn/public_providers/speech_assemblyai.py` — AssemblyAI transcript/polling adapter for async jobs.
- `comfyvn/server/routes/providers_translate_ocr_speech.py` — FastAPI router exposing health/quota tests for all public providers.

## Adapter Contracts
- Translation adapters export `class TranslationAdapter` with `.translate(texts, target, source=None, formality=None)` returning `{"items":[{"src","tgt","lang","provider","usage"}], "raw":{...}}` and `.quota()` for plan metadata. They raise `ProviderAuthError` for credential issues and `ProviderQuotaError` for limit breaches so the route can map to HTTP 401/429.
- OCR adapters expose `.extract(image_bytes, features=None, hints=None)` and normalise detections into `{"blocks":[...], "confidence":float, "provider":...}`. Google Vision supports feature toggles (`TEXT_DETECTION`, `DOCUMENT_TEXT_DETECTION`); Rekognition wraps region/bucket hints.
- Speech adapters implement `.transcribe(audio_bytes|url, *, model=None, diarize=False, language=None)` and optional `.stream(reader)` for websocket inputs. Responses always include `{"text": str, "segments":[...], "confidence": float, "duration": seconds, "provider": ...}`.
- All adapters are constructed through `from_env()` helpers that read environment/config keys and return `(adapter, diagnostics)` where diagnostics lists which credentials were discovered.

## Translation Providers
### Google Cloud Translation
- Uses v3 `projects/{project}/locations/{location}:translateText`. Requires `COMFYVN_TRANSLATE_GOOGLE_API_KEY` (for key-based access) **or** service account JSON via `COMFYVN_TRANSLATE_GOOGLE_CREDENTIALS`. Optional overrides: `COMFYVN_TRANSLATE_GOOGLE_PROJECT`, `COMFYVN_TRANSLATE_GOOGLE_LOCATION` (defaults to `global`).
- `.translate()` batches up to 128 strings, auto-detects source when none supplied, and includes glossary handling once `glossary_id` is present. Returns `usage` with `character_count` and `model` fields from the API response.
- `.quota()` hits `https://cloudtranslation.googleapis.com/v3/projects/{project}/locations/{location}:getSupportedLanguages` when credentials are valid, using the HTTP response headers to surface edition (`Advanced` vs `Basic`) and populating `{"plan": {"edition": "...", "characters": month_to_date}, "limits": {...}}`. Missing credentials return `{"ok": False, "reason": "missing_credentials"}` without raising.

### DeepL API
- Targets `https://api-free.deepl.com/v2/translate` or `https://api.deepl.com/v2/translate` depending on `COMFYVN_TRANSLATE_DEEPL_ENDPOINT` or inferred from the key prefix (`free:` for API Free). Credentials live in `COMFYVN_TRANSLATE_DEEPL_KEY`; optional `COMFYVN_TRANSLATE_DEEPL_FORMALITY`.
- `.translate()` honours fields `source_lang`, `target_lang`, `formality`. The adapter maps DeepL’s `detected_source_language` to our `lang` field and captures `character_count` for TM analytics.
- `.quota()` calls `/v2/usage` and returns `{"plan": {"tier": "free|pro", "limit": limit, "used": count}}`. Free plan limit defaults to 500_000 chars/month.

### Amazon Translate
- Relies on SigV4 signing via boto-style helpers. Credentials come from standard AWS envs (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`). Region defaults to `us-east-1` but can be overridden with `COMFYVN_TRANSLATE_AWS_REGION`.
- `.translate()` posts to `https://translate.{region}.amazonaws.com/` with `TranslateText`. Adapter exposes `terminology_names` support and maps `SourceLanguageCode`/`TargetLanguageCode`. Usage metadata includes `billed_units` so downstream UIs can estimate cost (`$15 per million` baseline).
- `.quota()` calls `ListTextTranslationJobs` (first page) to confirm service availability and extracts the account’s `EncryptionKey`/`TerminologyNames` entitlements. Missing permissions bubble up as structured error for `/translate/test`.

## OCR & Computer Vision
### Google Vision
- Accepts raw bytes or GCS URIs. The adapter builds `images:annotate` payloads with features `[{"type": "DOCUMENT_TEXT_DETECTION"}]` by default and allows detections to be scoped via `hints={"language_codes": [...]}`.
- Credentials mirror other Google services: API key via `COMFYVN_OCR_GOOGLE_KEY` or service account path in `COMFYVN_OCR_GOOGLE_CREDENTIALS`.
- Response normalises `fullTextAnnotation.text`, `pages`, and bounding boxes into `{"text": ..., "blocks":[{"text","bounding_box","confidence"}]}`.
- Diagnostic `quota()` calls `locations:operations` to fetch project usage, returning first 1,000 units free messaging when available.

### AWS Rekognition
- Uses the JSON API `DetectText`. Credentials piggyback off AWS envs (`AWS_ACCESS_KEY_ID`, etc.) with optional `COMFYVN_OCR_REKOGNITION_REGION`.
- Supports both byte payloads and S3 object refs (`{"s3_bucket","s3_key"}`) for large images. Results group LINE vs WORD detections with bounding boxes; we bubble up `Geometry` data.
- `quota()` verifies `DescribeProjectVersions` (if permissions) or defaults to `{"plan": "usage_based", "free_tier": "First 5K images/month for first 12 months"}` when only basic permissions exist.

## Speech Providers
### Deepgram
- Adapter wraps REST streaming (`/v1/listen`) and pre-signed websocket. Requires `COMFYVN_SPEECH_DEEPGRAM_KEY`. Supports model hints via `COMFYVN_SPEECH_DEEPGRAM_MODEL` (defaults `nova-2`) plus optional `COMFYVN_SPEECH_DEEPGRAM_TIER`.
- `.transcribe()` accepts bytes, URLs, or file-like streams. Normalises `channel.alternatives` into segments with `start/end` timestamps. Features toggled through payload flags (`smart_format`, `utterances`, `detect_language`).
- `.quota()` calls `/v1/projects/{project_id}` to surface balance/minutes and returns `{"plan": {"tier": "...", "balance": minutes_remaining}}`.

### AssemblyAI
- Uses async transcription: upload (when necessary) → `POST /v2/transcript` → poll `/v2/transcript/{id}` until `status in {"completed","error"}`. Key pulled from `COMFYVN_SPEECH_ASSEMBLYAI_KEY`.
- Supports advanced features (`auto_chapters`, `entity_detection`, `sentiment_analysis`) toggled via kwargs. Adapter exposes `.stream()` as a no-op since AssemblyAI is HTTP-only; frontends rely on polling.
- `quota()` hits `/v2/account` to fetch `auto_recharge`, `balance`, and product entitlements (streaming, understanding models). Errors produce `{"ok": False, "reason": "forbidden", "details": ...}`.

## Server API
- `GET /api/providers/translate/test` enumerates configured translation adapters, instantiates each via `from_env()`, and returns:
  ```json
  {
    "ok": true,
    "providers": [
      {
        "id": "google",
        "configured": true,
        "plan": {"edition": "Advanced", "characters": 12034},
        "limits": {"free_tier": "First 500K chars/month"},
        "errors": []
      },
      {
        "id": "deepl",
        "configured": false,
        "errors": [{"code": "missing_credentials"}]
      }
    ]
  }
  ```
- When no credentials exist, the route still returns HTTP 200 with `"ok": false` and `errors` describing missing variables so Studio can display setup guidance instead of hard failures.
- The same router exposes `/ocr/test` and `/speech/test` siblings mirroring the translate payload (configured flag, plan summary, last quota fetch timestamp). Each call is guarded with 5s timeouts and per-provider try/except so one failure does not abort the batch.
- Quota requests are cached in-memory for ~5 minutes to avoid hammering provider APIs while the settings panel is open.

## Credential Loading
- Environment variables take priority. Secondary source is `config/public_providers.json` which can store provider blocks:
  ```json
  {
    "translate": {"deepl": {"api_key": "<key>", "plan": "free"}},
    "speech": {"deepgram": {"api_key": "...", "tier": "payg"}}
  }
  ```
- Credentials detected by adapter constructors are recorded in `diagnostics["credentials"]` (masking secrets) so `/providers/.../test` can show which values were found.
- All adapters share the same HTTP client factory (`comfyvn/utils/http.py`) respecting proxy + timeout envs (`COMFYVN_HTTP_TIMEOUT`, `COMFYVN_HTTP_PROXY`).

## Pricing & References
- Google Cloud Translation — pay-as-you-go, editions (Advanced/Basic), first 500K chars/month free for Advanced projects. Docs: [Google Cloud Translation](https://cloud.google.com/translate/pricing).
- DeepL API — Free tier up to 500K chars/month; Pro tier scales by usage. Docs: [DeepL API](https://www.deepl.com/docs-api).
- Amazon Translate — $15 per million chars (standard), $60 with custom terminology; free tier 2M chars/month for 12 months. Docs: [Amazon Translate Pricing](https://aws.amazon.com/translate/pricing).
- Google Vision — Tiered by feature, first 1K units/month free. Docs: [Google Cloud Vision OCR](https://cloud.google.com/vision/pricing).
- AWS Rekognition — Usage-based with initial free credits (5K images/month for 12 months). Docs: [AWS Rekognition Pricing](https://aws.amazon.com/rekognition/pricing).
- Deepgram — $0.06–$0.08/min standard models, advanced tiers for Nova + features. Docs: [Deepgram Pricing](https://deepgram.com/pricing).
- AssemblyAI — Published per-product rates (streaming, LeMUR, understanding add-ons). Docs: [AssemblyAI Pricing](https://www.assemblyai.com/pricing).

## Acceptance & Verification
- `/api/providers/translate/test` returns configured providers with plan/quota when credentials are present; without keys it responds with `configured=false` and guidance instead of raising.
- OCR and speech diagnostics routes respond within 5s, include `configured`, `plan`, `limits`, and bubble up provider-specific error codes (auth/quota/network) for Studio UI surfacing.
- Translation adapters plug into `TranslationMemoryStore`: when adapters succeed, TM entries are tagged with `source="provider:<id>"` and `confidence` seeded from provider metadata; when no provider is available we fall back to the existing stub (identity mapping, confidence `0.35`).
- Unit hooks: lightweight tests simulate successful quota responses with `responses` mocks and verify credential discovery logic. Integration tests use env var stubs and assert de-duplicated error handling when multiple providers are missing keys.

