# Dev Notes — Translation Memory & Review Queue

Last updated: 2025-11-07  
Owner: Translation Chat (Localization/i18n)

## Components
- `comfyvn/translation/tm_store.py` implements the persistent Translation Memory. Entries are keyed by `(lang, source)` and written to `config/i18n/tm.json`.
- `comfyvn/server/routes/translation.py` surfaces TM-backed endpoints:
  - `POST /api/translate/batch` → resolves cached strings before falling back to stubbed identity translations (confidence `0.35`) which are recorded for review.
  - `GET /api/translate/review/pending` → lists unreviewed TM entries, grouped by language.
  - `POST /api/translate/review/approve` → marks entries as reviewed, records optional editor name + updated confidence.
  - `GET /api/translate/export/json` / `GET /api/translate/export/po` → export reviewed entries for localisation pipelines.
- `comfyvn/gui/panels/translation_panel.py` adds a dockable Studio panel that consumes the review endpoints, supports inline edits, and triggers JSON/PO exports for translation teams.

## Review Workflow
1. Client submits `POST /api/translate/batch` with `{strings:[...], target}`. Cache hits return `{source:"tm"}`; misses are recorded with `source:"stub"`.
2. Reviewers open the Studio “Translation” panel or call `GET /api/translate/review/pending` to fetch outstanding entries.
3. Approvals happen via the panel or `POST /api/translate/review/approve` payloads:
   ```json
   {
     "id": "<tm-entry-id>",
     "translation": "Approved text",
     "reviewed_by": "alice",
     "confidence": 0.98
   }
   ```
4. Export reviewed strings through the UI buttons or `GET /api/translate/export/{json,po}` for integration with external CAT tools or build pipelines.

## Debugging & Maintenance
- TM data lives at `config/i18n/tm.json`. Delete the file to reset the cache (the store will recreate it on demand).
- Unit coverage: `tests/test_translation_routes.py` exercises batch caching, approvals, and export endpoints. Run `pytest tests/test_translation_routes.py` after modifying TM logic.
- `TranslationMemoryStore.export_po()` emits `msgctxt` blocks tagged with the entry language—useful when multiple locales share a single export.
- Use `?lang=<code>` on `/translate/review/pending` or the export endpoints to scope down to a specific locale during QA passes.

## Future Hooks
- Swap the stubbed identity fallback with an MT provider: extend `TranslationManager.batch_identity` or call a service before invoking `store.record(...)`.
- Add reviewer attribution to external systems by enriching the TM JSON (fields already exist: `reviewed_at`, `reviewed_by`).
- For automation, poll `/translate/review/pending` and trigger approvals via CI scripts when string diffs match expected machine output.
- Public provider blueprint (2025-11-07): adapters for Google/DeepL/Amazon Translate, Google Vision/AWS Rekognition OCR, and Deepgram/AssemblyAI speech live under `comfyvn/public_providers/` once implemented. Feature flags (`enable_public_translation_apis`, `enable_public_ocr_apis`, `enable_public_speech_apis`) remain off by default; enable them via Settings or by editing `config/comfyvn.json`.
- Diagnostics: `/api/providers/{translate,ocr,speech}/test` run in dry-run mode and respond with `{configured, plan, limits, errors}` for each provider. Use them to confirm credentials before turning adapters on. Missing credentials should return `"code": "missing_credentials"` instead of raising.
- TM metadata: when adapters supply translations, record entries with `source="provider:<id>"` and seed `confidence` from provider scores so the review panel can prioritise high-certainty items. Stub fallbacks keep using `source="stub"` with `confidence=0.35`.
- Docs: see `docs/development/public_translation_ocr_speech.md` for full API contracts, pricing references, logging conventions, and modder hook guidance.
