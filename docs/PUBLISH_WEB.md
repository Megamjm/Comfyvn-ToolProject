# P6 — Web Packager: Mini-VN bundle, redaction, preview

## Feature flag & requirements
- Feature flag: `enable_publish_web` (defaults **OFF**). Flip it in `config/comfyvn.json` before calling the API.
- Depends on the Ren'Py export pipeline (`build/renpy_game`). The web packager reuses the same scene manifest and Mini-VN snapshots.
- Output root: `exports/publish/web/` (`<slug>.web.zip`, manifest, preview, redaction JSON sidecars).

```bash
# Quick verification (expects the FastAPI server on port 8001)
python tools/check_current_system.py --profile p6_publish_web --base http://127.0.0.1:8001
```

## Build pipeline
`POST /api/publish/web/build`

- Runs the Ren'Py export orchestrator (`RenPyOrchestrator.export`) with `per_scene` support, then invokes `comfyvn/exporters/web_packager.py`.
- Assets are fingerprinted with SHA-256 and emitted under `assets/<hash>-<alias>.ext` for cache busting.
- Deterministic ZIP builder normalises timestamps/permissions, so identical inputs produce identical bundle hashes.
- `include_debug=true` writes `debug/modder_hooks.json` mirroring the modder bus catalogue for automation tooling.

```bash
curl -X POST http://127.0.0.1:8001/api/publish/web/build \
  -H "Content-Type: application/json" \
  -d '{
        "project": "phase6",
        "timeline": "main",
        "label": "Phase 6 Preview",
        "version": "0.6.0",
        "include_debug": true
      }'
```

Response fields:
- `result.archive_path` — `exports/publish/web/<slug>.web.zip`
- `result.manifest` — high-level bundle manifest (`*.web.manifest.json`)
- `result.content_map` — scene order, POV routes, asset hashes
- `result.preview` — health snapshot with missing assets/redaction counts

## Redaction flow
`POST /api/publish/web/redact`

Adds selective sanitisation on top of the build pipeline:

| Toggle | Behaviour |
| --- | --- |
| `strip_nsfw` | Skips assets flagged as NSFW in asset metadata (`extras.nsfw`, `extras.tags`, or ESRB-derived rating). |
| `remove_provenance` | Removes seeds, workflow identifiers, provenance blobs, and absolute paths from asset metadata. |
| `watermark_text` | Renders an overlay across `index.html` for reviewer screenshots. |
| `exclude_paths` | Force-omit specific asset relpaths (e.g. legacy splash screens or experimental scenes). |

The redaction summary is recorded in `<slug>.web.redaction.json` and surfaced via the API response (`result.redaction`). Only the redacted artefacts receive new hashes; safe assets remain byte-identical.

```bash
curl -X POST http://127.0.0.1:8001/api/publish/web/redact \
  -H "Content-Type: application/json" \
  -d '{
        "project": "phase6",
        "strip_nsfw": true,
        "remove_provenance": true,
        "watermark_text": "PHASE6 QA ONLY"
      }'
```

## Preview & QA
`GET /api/publish/web/preview`

- Without params: lists available bundles and the quick health snapshot (`status`, missing/redacted counts).
- With `?slug=<slug>`: returns manifest, content map, preview health, redaction summary, plus archive/hook file paths for local QA.

```bash
curl http://127.0.0.1:8001/api/publish/web/preview?slug=phase6-preview-0-6-0
```

The bundled `index.html` bootstraps the Mini-VN manifest, surfaces asset hashes, and loads the cached `content_map.json` so reviewers can verify scene ordering offline. Watermarks (when configured) render as a translucent overlay.

## Debug & hooks
- `include_debug=true` writes `debug/modder_hooks.json` with the live modder hook catalogue (`hooks_payload()`), enabling contributor dashboards to trace available events without calling the main API.
- `preview` responses expose the same hook path so QA scripts can diff hook availability across builds.

## Failure modes & remediation
- HTTP `403`: `enable_publish_web` is disabled. Toggle the feature flag.
- Advisory warnings: the `publish.web` disclaimer is pending. Acknowledge in Studio → Advisory or via `/api/advisory/ack` before shipping the bundle.
- `status: degraded`: missing assets (Ren'Py export couldn’t copy them) or redaction removed NSFW assets. Inspect `result.preview` and `result.redaction.removed_assets`.

Keep bundle directories under version control as artefacts (manifest, redaction summaries) rather than committing ZIP payloads.
