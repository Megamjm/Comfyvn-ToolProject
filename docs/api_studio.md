# Studio API Overview

The Studio HTTP endpoints coordinate the desktop shell with the backend.
All routes live under `/api/studio` and produce JSON responses.

## POST /api/studio/open_project
- **Body:** `{ "project_id": "my-project" }`
- **Response:** `{ "ok": true, "project_id": "my-project" }`
- **Logging:** `INFO` message with selected project ID.

## POST /api/studio/switch_view
- **Body:** `{ "view": "Timeline" }`
- **Response:** `{ "ok": true, "view": "Timeline" }`
- **Logging:** `INFO` message with active view.

## POST /api/studio/export_bundle
- **Body:**
  - Either `raw` (inline scene JSON) or `raw_path` (path to JSON file) is required.
  - Optional `manifest_path`, `schema_path`, and `out_path`.
- **Response:**
  - If `out_path` provided: `{ "ok": true, "bundle": { "path": "..." } }`
  - Otherwise returns the generated bundle structure.
- **Logging:** `INFO` on success, `ERROR` on failure.

### Notes
- All endpoints return HTTP 400 for missing parameters.
- Export endpoint leverages `comfyvn.scene_bundle.build_bundle` to perform conversion.
- Errors are surfaced with HTTP 500 and recorded in the server log.

Refer to `comfyvn/gui/studio_window.py` for an example client.
