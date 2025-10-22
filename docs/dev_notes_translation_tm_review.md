# Dev Notes — Translation Memory & Review Queue

Last updated: 2025-10-22  
Owner: Translation Chat (Localization/i18n)

## Components
- `comfyvn/translation/tm_store.py` implements the persistent Translation Memory. Entries are keyed by `(key, lang)` and written to `config/i18n/tm.json` with `{text, version, meta, hits, confidence, reviewer}`.
- `comfyvn/translation/manager.py` persists active/fallback languages and now resolves strings via TM before falling back to inline tables or the key.
- `comfyvn/server/routes/translation.py` exposes the REST surface:
  - `POST /api/translate/batch` → resolves cached hits and records new stubs (identity, `confidence=0.35`, `origin="stub"`). Supports rich `items[].meta` (asset/component/hooks) merged with global payload meta.
  - `GET /api/translate/review` → filters pending/reviewed entries by `status`, `lang`, `key`, `asset`, `component`, `limit`, `include_meta`.
  - `POST /api/translate/review` → approves/edits TM entries, updates translation/meta/reviewer/confidence, toggles `reviewed` state. Legacy `/pending` + `/approve` routes forward here.
  - `GET /api/translate/export/{json,po}` → exports reviewed entries with optional `lang`, `key`, and `include_meta` query params (PO export writes meta as `# Meta key: value`).
- `comfyvn/gui/panels/translation_panel.py` adds a dockable Studio panel that consumes the review endpoints, supports inline edits, and triggers JSON/PO exports for translation teams.

## Review Workflow
1. Client submits `POST /api/translate/batch` with either `{"items":[{key,source,meta}]}` or a simple string array. Cache hits return `{source:"tm"}` with previous metadata; misses are recorded with `source:"stub"`, `origin:"stub"`, and merged `meta`.
2. Reviewers open the Studio panel or call `GET /api/translate/review?status=pending&lang=<code>&include_meta=1` to fetch outstanding entries (filters optional).
3. Approvals happen via the panel or `POST /api/translate/review` payloads:
   ```json
   {
     "id": "<tm-entry-id>",
     "translation": "Approved text",
     "reviewer": "alice",
      "confidence": 0.98,
      "meta": {"asset": "scene:intro", "notes": "QA pass"},
      "reviewed": true
    }
    ```
4. Export reviewed strings through the UI buttons or `GET /api/translate/export/{json,po}?lang=<code>&include_meta=1` for downstream CAT tools/build pipelines.

## Debugging & Maintenance
- TM data lives at `config/i18n/tm.json`. Delete the file to reset the cache (the store will recreate it on demand).
- Unit coverage: `tests/test_translation_routes.py` exercises batch caching, approvals, and export endpoints. Run `pytest tests/test_translation_routes.py` after modifying TM logic.
- `TranslationMemoryStore.export_po()` emits `msgctxt` blocks tagged with the entry language plus optional meta comments (`# Meta asset: scene:intro`).
- Use `/api/translate/review?asset=<tag>` or `?component=<tag>` to slice QA workloads per asset/component. Both endpoints accept `limit` for paging.
- Batch responses include debug `links` (review + export) so CLI tooling can jump directly into targeted updates.

## Future Hooks
- Swap the stubbed identity fallback with an MT provider: fan out `POST /api/translate/batch` to a provider, then call `POST /api/translate/review` with the translated text (`origin="provider:<id>"`, `confidence=<score>`).
- Add reviewer attribution to external systems by streaming TM entries (`reviewed_by`, `reviewed_at`, `version`) through dashboards or webhooks; the JSON export captures these fields.
- For automation, poll `/api/translate/review?status=pending&limit=50` and trigger approvals via CI scripts when string diffs match expected MT output.
- Public provider blueprint (2025-11-07): adapters for Google/DeepL/Amazon Translate, Google Vision/AWS Rekognition OCR, and Deepgram/AssemblyAI speech live under `comfyvn/public_providers/` once implemented. Feature flags (`enable_public_translation_apis`, `enable_public_ocr_apis`, `enable_public_speech_apis`) remain off by default; enable them via Settings or by editing `config/comfyvn.json`.
- Diagnostics: `/api/providers/{translate,ocr,speech}/test` run in dry-run mode and respond with `{configured, plan, limits, errors}` for each provider. Use them to confirm credentials before turning adapters on. Missing credentials should return `"code": "missing_credentials"` instead of raising.
- TM metadata: when adapters supply translations, record entries with `origin="provider:<id>"`, seed `confidence` from provider scores, and inject `meta.provider` so reviewers can prioritise high-certainty items. Stub fallbacks keep using `origin="stub"` with `confidence=0.35`.
- Docs: see `docs/development/public_translation_ocr_speech.md` for full API contracts, pricing references, logging conventions, and modder hook guidance.
