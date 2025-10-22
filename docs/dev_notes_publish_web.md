# Dev Notes — Web Publish / Redaction Preview

## Scope
Phase 6 introduces a web-friendly publish pipeline that reuses the Mini-VN fallback renderer to emit self-contained bundles for QA or partner distribution dry-runs. The code lives in:
- `comfyvn/exporters/web_packager.py`
- `comfyvn/server/routes/publish.py`

Feature flag: `features.enable_publish_web` (defaults **false**).

## API surface
| Route | Method | Notes |
| --- | --- | --- |
| `/api/publish/web/build` | `POST` | Deterministic bundle without redaction; assets hashed into `assets/<sha12>-<alias>.ext`. |
| `/api/publish/web/redact` | `POST` | Same build pipeline with sanitisation toggles (strip NSFW assets, scrub provenance, optional watermarks). |
| `/api/publish/web/preview` | `GET` | Lists available bundles or returns manifest/content-map/health/redaction payloads for a specific slug. |

The router enforces the `publish.web` policy gate; acknowledge via Studio → Advisory or `/api/advisory/ack` when blocked with HTTP 423.

## Bundle layout
```
exports/publish/web/<slug>.web.zip
exports/publish/web/<slug>.web.manifest.json
exports/publish/web/<slug>.web.content_map.json
exports/publish/web/<slug>.web.preview.json
exports/publish/web/<slug>.web.redaction.json
exports/publish/web/<slug>.web.hooks.json  # optional via include_debug
```

Inside the archive:
- `index.html` bootstraps the manifest + content map, rendering a human-readable summary.
- `styles/app.css` is static (deterministic) for consistent ZIP hashes.
- `data/manifest.json`, `data/content_map.json`, `data/redaction.json` mirror the sidecars.
- `preview/health.json` carries the same payload returned by `/preview`.
- `assets/<sha12>-<alias>.ext` contain copied/filtered assets.

## Redaction heuristics
- `strip_nsfw=true` drops assets whose metadata includes `extras.nsfw`, ESRB-equivalent `rating` of `mature|adult`, or tags intersecting `{"nsfw","explicit","adult","18+","mature"}`.
- `remove_provenance=true` strips `seed`, `workflow_id`, `workflow_hash`, and provenance extras from asset metadata plus source paths from project/timeline descriptors.
- `exclude_paths` is matched against the asset relpath (`assets/<rel>`); use for manual overrides.
- `watermark_text` injects a translucent overlay into `index.html` for screenshot audits.

## Debug hooks & automation
- `include_debug=true` writes `debug/modder_hooks.json` with the live hook catalogue from `modder_hooks.hook_specs()`. `/preview?slug=<slug>` echoes the same path so dashboards can diff hook support between builds.
- Every build appends a structured record to `logs/export/publish.log`:
  ```json
  {"target":"web","slug":"phase6-preview-0-6-0","label":"Phase 6 Preview","archive":"exports/publish/web/phase6-preview-0-6-0.web.zip","checksum":"...","assets":42,"removed_assets":2,"debug_hooks":true}
  ```

## QA recipe
1. Enable the flag in `config/comfyvn.json` (`"enable_publish_web": true`).
2. `python tools/check_current_system.py --profile p6_publish_web --base http://127.0.0.1:8001` to confirm flags/routes/docs.
3. `POST /api/publish/web/build` (dry run first if desired) then `POST /api/publish/web/redact` with the required toggles.
4. `GET /api/publish/web/preview?slug=<slug>` and inspect `preview.status` (`ok` vs `degraded`), missing assets, and redaction summary.
5. For diffing redactions across builds, compare `<slug>.web.redaction.json` (only NSFW removals should differ).

## Troubleshooting
- Missing bundle files: rerun without `dry_run`. `dry_run=true` only reports diffs.
- Asset unexpectedly removed: inspect `result.redaction.removed_assets` and underlying asset metadata in the registry (`assets/_meta/*.json`). Adjust tags or disable `strip_nsfw`.
- 403 errors: ensure `enable_publish_web` flag is set true and the server reloaded.
- 423 errors: the advisory gate (`publish.web`) is blocking; acknowledge via `/api/advisory/ack`.
- Hash drift: confirm assets weren’t modified between builds and that the feature flag set matches expectations; the deterministic ZIP builder uses fixed timestamps/permissions, so only content changes should alter hashes.
