# Phase 9 — VN Loader & Mini-VN Viewer Integration

Updated: 2025-10-21

## Purpose
- Surface a first-party GUI panel (`Panels → VN Loader`) that can discover compiled VN projects, trigger rebuilds from import bundles, and explore the resulting scene graph without leaving Studio.
- Provide a deterministic Mini-VN preview for any scene so modders can validate branching and localisation before launching a full Ren'Py runtime.
- Document the REST/API hooks and debug affordances modders should rely on when extending the loader, building automation, or shipping prefab assets.

## Panel Overview (`comfyvn/gui/panels/vn_loader_panel.py`)
- **Project selector** calls `GET /api/vn/projects` to enumerate build targets. Each entry carries `id`, `title`, `project_path` and raw metadata so automation can persist additional attributes.
- **Build from Imports** posts to `POST /api/vn/build` with `{ "projectId": "...", "sources": [] }`, mirroring the CLI importer rebuild flow.
- **Rebuild Timeline** reuses `/api/vn/build` with `{ "projectId": "...", "rebuild": true }` to force a refresh when the compiled scene graph drifts from source imports.
- **Scenes list** retrieves `GET /api/vn/scenes?projectId=...` and caches the raw payload for downstream hooks (e.g., export scripts, debug overlays).
- **Play from Here** opens an inline Mini-VN dialog that iterates the selected scene’s dialogue blocks, rendering speakers, narration, and choice nodes for quick validation.
- **Open in Viewer** instantiates `MiniVNPlayer` to generate a deterministic snapshot and renders it with the shared `MiniVNFallbackWidget`, providing the same digest + preview metadata used by the full viewer fallback.
- **Open in Ren’Py** sends `POST /api/viewer/start` with the current `project_id` and `project_path`, preserving parity with the central viewer pane.
- Debug console (bottom of the panel) streams JSON responses for every request so modders can copy payloads, diff responses, or wire automated tests. The read-only hook list doubles as an API cheat sheet.

## Required API Surface
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/vn/projects` | GET | Returns `{ ok, data: { items: [...] } }` or a bare list of projects. Each item should expose `id`, `title`, and `project_path`. |
| `/api/vn/build` | POST | Accepts `projectId` plus optional `sources`/`rebuild` flags. Returns `{ ok, data: { status, warnings, diagnostics } }`. |
| `/api/vn/scenes` | GET | Requires `projectId`; returns `{ ok, data: { items: [...] } }` where items include `id`, `title`, and `timeline_id`. |
| `/api/vn/preview/{scene_id}` | GET | Returns the compiled scene JSON. Optional `projectId` query narrows the lookup. |
| `/api/viewer/start` | POST | Launches native Ren'Py or Mini-VN fallback. Payload mirrors the central viewer pane. |

### Optional Debug Hooks
- `/api/viewer/mini/refresh` and `/api/viewer/mini/snapshot` remain compatible with the loader output; once the viewer fallback is active, the panel’s snapshot dialog will automatically pick up thumbnail URLs.
- `/api/modder/hooks` can subscribe to build events (`vn.build.started`, `vn.build.completed`) if the backend broadcasts them. The panel writes raw responses to the debug console so hook contracts are visible during development.

## Mini-VN Playback Notes
- The loader instantiates `MiniVNPlayer` locally, letting it reuse the shared export manifest and thumbnail cache. This keeps digests in sync with `/api/viewer/status` and avoids duplicating preview logic.
- Scene previews normalise dialogue nodes into `{speaker,text,choices}` so the inline player can display branching points without executing Ren’Py script.
- When thumbnails are unavailable (token not issued because the viewer isn’t running), the dialog falls back to textual summaries—matching the fallback widget’s behaviour in the central viewer.

## Contributor Checklist
- **Docs**: Link back to this guide whenever you surface VN loader features in release notes (`CHANGELOG.md`) or architecture updates.
- **Testing**: Smoke the `p9_viewer_integration` checker; it verifies route presence plus this doc file.
- **Automation**: Use the debug console output to capture fixtures for QA harnesses (`tests/vn/*`). Fixtures should mirror the payloads emitted here.
- **Extensibility**: New buttons or workflows must continue to rely on the REST layer documented above. Avoid reading raw files from disk in the GUI—funnel everything through the API so headless clients remain compatible.

## Related References
- `docs/dev_notes_viewer_stack.md` — broader viewer architecture, fallback states, and hook catalog.
- `docs/import_vnpack.md` — import pipeline that feeds `/api/vn/build`.
- `docs/VIEWER_README.md` — native viewer launch flow and Mini-VN fallback behaviour.
