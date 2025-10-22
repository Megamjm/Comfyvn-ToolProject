# Translation Manager

Last updated: 2025-10-22  
Owner: Localization & Narrative Tools

## Overview
- Centralises language lookup through `comfyvn.translation.manager.TranslationManager` with live switch between active and fallback locales.
- Persists translation memory (TM) records in `config/i18n/tm.json` using `{key -> {lang -> {text, meta, version}}}`.
- Provides review queue APIs so editors can approve or patch machine stubs before exporting `.json`/`.po` bundles.
- Exposes debug hooks (`links`, `meta`, filters) so modders and contributors can track asset scoped strings.

## Runtime Flow
1. **Batch Submit** → `POST /api/translate/batch` records missing keys as stub candidates (identity translation) and returns cached TM hits.
2. **Review** → `GET /api/translate/review` filters pending and approved entries (by language, key, or meta such as `asset`/`component`).
3. **Approve / Edit** → `POST /api/translate/review` mutates TM entries (translation, meta, reviewer, confidence, reviewed flag).
4. **Export** → `GET /api/translate/export/{json,po}` produces pipelines for CAT tools build steps (optional meta embedding).
5. **Live Switch** → `POST /api/i18n/lang` toggles `active`/`fallback` languages; `TranslationManager.t()` resolves TM overrides with fallback to source key.

## Data Model
```json
{
  "id": "sha1(lang:key)",
  "key": "ui.greeting",
  "lang": "es",
  "source_text": "Hello",
  "target": "Hola",
  "origin": "stub | tm | review | provider:<id>",
  "version": 3,
  "confidence": 0.92,
  "reviewed": true,
  "meta": {
    "asset": "scene:intro",
    "component": "dialogue",
    "hooks": {
      "onSave": "studio.translation.afterSave"
    }
  }
}
```

- Versions increment on target/source/meta change or review transitions.
- `meta` is always deep copied to maintain determinism for diffing; contributors can tag entries with `asset`, `component`, `context`, `hooks`, etc.
- Translation memory indices support lookups by key (preferred) and legacy source text.

## API Reference

### GET `/api/i18n/lang`
Reports active/fallback languages and available locales.

```bash
curl -s http://127.0.0.1:8001/api/i18n/lang | jq
```

### POST `/api/i18n/lang`
Switch active and/or fallback languages.

```bash
curl -sX POST http://127.0.0.1:8001/api/i18n/lang \
  -H "Content-Type: application/json" \
  -d '{"lang": "es", "fallback": "en"}'
```

### POST `/api/translate/batch`
Submits keys for translation. Accepts either a list of strings or rich items with metadata.

```bash
curl -sX POST http://127.0.0.1:8001/api/translate/batch \
  -H "Content-Type: application/json" \
  -d '{
        "target": "es",
        "source_lang": "en",
        "items": [
          {"key": "ui.greeting", "source": "Hello", "meta": {"asset": "scene:intro"}},
          {"key": "ui.exit", "default": "Exit", "meta": {"component": "menu"}}
        ]
      }' | jq '.items[] | {key, lang, source, src, tgt, status, reviewed}'
```

- `status` → `stubbed` for new entries, `cached` when TM returned a hit, `pending`/`reviewed` mirrors approval state.
- Each item carries `links.review`, `links.export_json`, `links.export_po` for follow-up automation.

### GET `/api/translate/review`
Fetches review queue entries. Supports filters:
- `status=pending|reviewed|all`
- `lang=<code>`
- `key=<translation-key>`
- `asset=<meta.asset>` or `component=<meta.component>`
- `limit=<n>` and `include_meta=true`

```bash
curl -s "http://127.0.0.1:8001/api/translate/review?lang=es&status=pending&include_meta=1" | jq
```

### POST `/api/translate/review`
Updates a TM entry (approve, unapprove, edit translation, enrich meta).

```bash
curl -sX POST http://127.0.0.1:8001/api/translate/review \
  -H "Content-Type: application/json" \
  -d '{
        "id": "a1b2c3d4",
        "translation": "Bienvenido",
        "reviewer": "alice",
        "confidence": 0.98,
        "meta": {"asset": "scene:intro", "notes": "QA pass"},
        "reviewed": true
      }'
```

### Legacy Compatibility
- `GET /api/translate/review/pending` returns the classic payload (`total`, `by_lang`) for tools that have not migrated.
- `POST /api/translate/review/approve` is still wired to the new handler.

### Export Endpoints

```bash
# JSON
curl -s "http://127.0.0.1:8001/api/translate/export/json?lang=es&include_meta=1" | jq

# PO
curl -s "http://127.0.0.1:8001/api/translate/export/po?lang=es&include_meta=1"
```

`include_meta=1` embeds asset hooks/comments for downstream liners. When a `key` query param is supplied, exports scope to that key.

## Live Lookup & Fallbacks
- `TranslationManager.t("ui.greeting")` resolves the active language, consults TM for overrides, and falls back to the configured fallback language before defaulting to the key itself.
- `get_table_value(key, lang)` allows debugging exact table values without triggering fallback logic.
- Feature flags (`enable_i18n`, `enable_translation_manager`) remain **off** by default for determinism; toggle via `config/comfyvn.json` only when wiring the Viewer front-end.

## Debug & Hooks for Modders
- Batch responses include `meta` and `links` so tooling can deep link into review queues or exports.
- Review API supports filtering by `meta.asset` and `meta.component` enabling asset-specific QA sweeps.
- TM entries expose `version`, `hits`, `confidence`, `reviewed_by`, and `reviewed_at` making it simple to surface dashboards or notify translators.
- Deleting `config/i18n/tm.json` resets the TM cache; the store will recreate it on demand.

## Checker & Smoke
- Run the phase checker:  
  `python tools/check_current_system.py --profile p5_translation --base http://127.0.0.1:8001`
- Run translation tests:  
  `pytest tests/test_translation_routes.py`

## Future Work
- Plug machine translation providers by swapping the stub identity inside `TranslationMemoryStore.record` (pegged for feature flag `enable_public_translation_apis`).
- Surface reviewer attribution in export metadata for CI gating.
- Expand `meta.hooks` to trigger custom scripts when entries transition from pending → reviewed.
