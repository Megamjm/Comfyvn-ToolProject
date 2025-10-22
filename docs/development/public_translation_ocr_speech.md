# Public Translation, OCR, & Speech Services

Last updated: 2025-11-07  
Owner: Translation Chat • Reach via Project Integration when adapters land.

---

## 1. Scope & Current State
- The existing translation workflow ships with a local Translation Memory (TM) and stubbed identity translations (`POST /api/translate/batch`). No third-party calls occur today.
- This blueprint documents the planned public service adapters so implementation teams, modders, and automation authors share the same contract before code lands.
- Target providers (Phase 7):
  - Translation: Google Cloud Translation (Advanced/Basic), DeepL API (Free/Pro), Amazon Translate.
  - OCR / Computer Vision: Google Cloud Vision, AWS Rekognition.
  - Speech-to-text: Deepgram, AssemblyAI.
- All adapters live in `comfyvn/public_providers/` and expose consistent interfaces (`translate()/quota()`, `extract()/quota()`, `transcribe()/quota()`), plus `from_env()` constructors that return `(adapter, diagnostics)` and never raise on missing credentials.

---

## 2. Feature Flags & Configuration
- Flags (default `false`) live under `config/comfyvn.json → features`. Studio’s **Settings → Debug & Feature Flags** drawer exposes toggles once code ships:
  ```jsonc
  {
    "features": {
      "enable_public_translation_apis": false,
      "enable_public_ocr_apis": false,
      "enable_public_speech_apis": false
    }
  }
  ```
- Long-running processes must call `feature_flags.refresh_cache()` after edits to pick up changes without a restart.
- Credentials are discovered via environment variables first, then `config/public_providers.json`:
  ```jsonc
  {
    "translate": {
      "deepl": {"api_key": "<key>", "plan": "pro"},
      "google": {
        "credentials_path": "secrets/google-translate.json",
        "project": "my-project",
        "location": "us-central1"
      }
    },
    "ocr": {"google_vision": {"api_key": "AIza..."}},
    "speech": {"deepgram": {"api_key": "dg_..."}}
  }
  ```
- Secrets belong in `config/comfyvn.secrets.json` (git-ignored). The adapter loader should merge secrets at runtime so repo copies stay clean.

---

## 3. API Surfaces

### 3.1 Diagnostics Endpoints (GET)
- `/api/providers/translate/test`
- `/api/providers/ocr/test`
- `/api/providers/speech/test`

These routes:
1. Enumerate adapters gated by the feature flag.
2. Call `from_env()` for each provider to confirm credentials (never raising on failure).
3. Invoke `.quota()` with a 5 s timeout when credentials exist.
4. Return aggregated payloads:

```jsonc
{
  "ok": true,
  "providers": [
    {
      "id": "google_translate",
      "configured": true,
      "plan": {"edition": "advanced", "characters_month": 12034},
      "limits": {"free_tier": "500k chars/month"},
      "errors": [],
      "diagnostics": {
        "credentials": ["COMFYVN_TRANSLATE_GOOGLE_CREDENTIALS"],
        "checked_at": "2025-11-07T10:58:12Z"
      }
    },
    {
      "id": "deepl",
      "configured": false,
      "errors": [{"code": "missing_credentials"}]
    }
  ]
}
```

Dry-run mode (`?dry_run=1`) skips `.quota()` network calls and only reports credential discovery. All diagnostics should return HTTP 200 even when not configured so UI panels can surface guidance without raising.

### 3.2 Translation Calls (POST `/api/providers/translate/execute`)
- Request:
  ```jsonc
  {
    "provider": "deepl",
    "strings": ["Hello world"],
    "target": "ja",
    "source": "en",
    "formality": "prefer_less",
    "dry_run": false
  }
  ```
- Response:
  ```jsonc
  {
    "ok": true,
    "items": [
      {
        "src": "Hello world",
        "tgt": "こんにちは世界",
        "lang": "ja",
        "confidence": 0.9,
        "usage": {"characters": 11}
      }
    ],
    "provider": "deepl",
    "raw": {...},
    "diagnostics": {"latency_ms": 620, "model": "deepl-pro"}
  }
  ```
- With `"dry_run": true`, adapters skip network calls and return a synthetic payload (`confidence=0.0`, `source="dry_run"`) while logging the intended parameters. This allows editors to preview consumption or test payload shaping without costs.

### 3.3 OCR Calls (POST `/api/providers/ocr/extract`)
- Example payload:
  ```jsonc
  {
    "provider": "google_vision",
    "image": {"bytes": "<base64>"},
    "features": ["DOCUMENT_TEXT_DETECTION"],
    "hints": {"language_codes": ["ja"]},
    "dry_run": true
  }
  ```
- Response (dry-run example):
  ```jsonc
  {
    "ok": true,
    "dry_run": true,
    "provider": "google_vision",
    "blocks": [],
    "diagnostics": {"note": "dry-run mode: payload validated only"}
  }
  ```

### 3.4 Speech Transcription (POST `/api/providers/speech/transcribe`)
- Payload:
  ```jsonc
  {
    "provider": "deepgram",
    "audio": {"path": "assets/audio/sample.wav"},
    "model": "nova-2",
    "language": "en",
    "smart_format": true,
    "dry_run": false
  }
  ```
- Response:
  ```jsonc
  {
    "ok": true,
    "text": "Sample transcription.",
    "segments": [{"start": 0.0, "end": 1.42, "text": "Sample transcription."}],
    "confidence": 0.94,
    "duration": 1.42,
    "provider": "deepgram",
    "diagnostics": {"latency_ms": 730}
  }
  ```

---

## 4. Adapter Contracts
- **TranslationAdapter**
  - Required methods: `translate(texts, target, source=None, **kwargs)`, `quota()`.
  - Returns `{"items": [...], "provider": "<id>", "raw": vendor_payload, "diagnostics": {...}}`.
  - Raises `ProviderAuthError`, `ProviderQuotaError`, or `ProviderRequestError`. The router maps them to HTTP 401/429/502 respectively.
- **OCRAdapter**
  - Methods: `extract(image_bytes|url, *, features=None, hints=None, dry_run=False)`, `quota()`.
  - Normalises detections into `{"blocks": [{"text","confidence","bbox"}], "text": "...", "provider": ...}`.
- **SpeechAdapter**
  - Methods: `transcribe(audio_bytes|path|url, **kwargs)`, optional `stream(reader)`, `quota()`.
  - Responses include `{"text", "segments", "confidence", "duration", "provider"}`.
- All adapters accept a shared `HttpClient` (respecting proxy + timeout env vars) and should expose `.close()` for cleanup when needed.

---

## 5. Integration with Translation Memory
- Successful translation responses feed `TranslationMemoryStore.record()` with:
  - `source`: original string
  - `lang`: target language
  - `target`: translated text
  - `confidence`: provider-reported confidence (fallback to 0.75 if absent)
  - `metadata.provider`: `<provider_id>`
  - `metadata.usage`: optional usage payload for reporting
- Entries use `source="provider:<id>"`. Stubbed fallbacks continue using `source="stub"`.
- The review queue UI can prioritise provider-based entries by sorting on `confidence`. Provide a filter chip so reviewers can focus on MT suggestions only.

---

## 6. Logging & Observability
- Structured JSON logs live under `logs/providers/` (rotated per category):
  - `logs/providers/translate.log`
  - `logs/providers/ocr.log`
  - `logs/providers/speech.log`
- Format: `{"timestamp", "provider", "event", "status", "latency_ms", "dry_run", "plan", "quota_remaining"}`.
- Errors bubble to `logs/server.log` with the same context plus `error.code`.
- `COMFYVN_LOG_LEVEL=DEBUG` enables request/response snippets (provider-specific redaction rules apply; secrets must never be logged).

---

## 7. Modder & Automation Hooks
- Event bus topics (`comfyvn.core.events`):
  - `providers.translate.test` — emitted after diagnostics, payload includes `providers` array.
  - `providers.translate.executed` — emitted after a translation call with `{provider, items, dry_run}`.
  - `providers.ocr.test` / `providers.ocr.executed`
  - `providers.speech.test` / `providers.speech.transcribed`
- Use these events to update Studio panels or external dashboards without polling.
- WebSocket channel (future): `/ws/providers` streams the same events for lightweight tool overlays.
- CLI snippet for diagnostics:
  ```bash
  curl -s http://127.0.0.1:8001/api/providers/translate/test | jq
  curl -s http://127.0.0.1:8001/api/providers/ocr/test | jq '.providers[].plan'
  ```
- CI integration: run diagnostics with `dry_run=1` and fail the job when any provider returns `configured=false` but credentials are expected (e.g., environment variable set).

---

## 8. Security Considerations
- Secrets must flow from environment variables or git-ignored files only. Never commit provider keys.
- For service account JSON, point to an absolute path in `COMFYVN_TRANSLATE_GOOGLE_CREDENTIALS`; the adapter should read and parse it at runtime, not during import.
- Prevent accidental spend by keeping feature flags off and requiring `dry_run=true` in automated scripts unless explicitly overridden.
- Ensure adapters redact personally identifiable data before logging (especially OCR/Speech payloads).

---

## 9. Testing Checklist
- Unit tests mock vendor APIs (`responses` library or custom fixtures) and assert:
  - Credentials missing → `configured=false`, error code preserved.
  - `.translate()` writes TM entries with `provider` metadata.
  - Dry-run mode skips HTTP calls.
- Integration tests (future) spin up FastAPI routers and exercise `translate/test` with env vars set.
- Smoke checklist before enabling in Studio:
  - Diagnostics route returns quota metadata.
  - TM review panel marks provider entries with appropriate `source`/`confidence`.
  - Logs appear under `logs/providers/` with masked credentials.

---

## 10. References
- Google Cloud Translation: https://cloud.google.com/translate/pricing
- DeepL API: https://www.deepl.com/docs-api
- Amazon Translate: https://aws.amazon.com/translate/pricing
- Google Cloud Vision OCR: https://cloud.google.com/vision/pricing
- AWS Rekognition: https://aws.amazon.com/rekognition/pricing
- Deepgram: https://deepgram.com/pricing
- AssemblyAI: https://www.assemblyai.com/pricing
- Codex stub: `docs/CODEX_STUBS/2025-10-21_PUBLIC_TRANSLATION_OCR_SPEECH_APIS_A_B.md`

Implementation teams should update this document and the changelog once adapters land. Until then, treat it as a contract for planned behaviour.
