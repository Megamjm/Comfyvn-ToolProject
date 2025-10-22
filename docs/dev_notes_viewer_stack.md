# Dev Notes — Viewer Fallback Stack

Updated: 2025-10-21

## Phase 9 — VN Loader Hooks
- Panel location: `Panels → VN Loader` (implementation: `comfyvn/gui/panels/vn_loader_panel.py`).
- Requests fan out through `ServerBridge` to `/api/vn/{projects,build,scenes,preview}` plus `/api/viewer/start`. Keep those routes stable; GUI and automation share the same payloads.
- `Play from Here` normalises dialogue into `{speaker,text,choices}` for quick QA runs; extend `_extract_lines` when adding richer node types (animations, audio cues, etc.).
- Mini-VN previews call `MiniVNPlayer.generate_snapshot()` so viewport digests match `/api/viewer/status`. If backend tokens are available, snapshots will pick up thumbnail URLs via `/api/viewer/mini/thumbnail/{token}/{key}` automatically.
- Debug console captures raw REST responses. When bumping payload fields, update this doc, `docs/VN_VIEWER_GUIDE.md`, and smoke `p9_viewer_integration`.

## Feature Flags
- `enable_viewer_webmode` (default: true) — allows `/api/viewer` to serve the web build when native Ren’Py embedding fails.
- `enable_mini_vn` (default: true) — enables the deterministic Mini-VN preview + thumbnailer.
- Toggle via Settings → Debug & Feature Flags or edit `config/comfyvn.json` directly.

## API Cheatsheet
- `/api/viewer/start` — unchanged payload, now returns `runtime_mode` plus `webview` / `mini_vn` payloads during fallback.
- `/api/viewer/web/{token}/{path}` — streams the Ren'Py web bundle (`index.html`, JS, assets).
- `/api/viewer/mini/snapshot` — latest Mini-VN snapshot (scenes, thumbnails, digest).
- `/api/viewer/mini/refresh` — rebuild snapshot; supports `{ "seed": <int>, "pov": "mc" }` overrides.
- `/api/viewer/mini/thumbnail/{token}/{key}` — serve cached thumbnails. Token invalidates on every start.

## GUI Behaviour
- Qt WebEngine embeds the web fallback when available; otherwise the pane surfaces an “Open in browser” prompt with the absolute URL.
- Mini-VN pane renders scene summaries, POV metadata, and thumbnail cache state. Digest prefixes help automation detect stale caches.
- Accessibility overlays (filters/subtitles) remain active regardless of fallback mode.
- The status poller now auto-demotes to web or Mini-VN whenever the native process exits unexpectedly—`stub_reason` surfaces the exit code and the GUI swaps immediately without waiting for another start request.

## Hooks
- `on_thumbnail_captured` fires whenever the Mini-VN thumbnailer writes/refreshes a cache entry. Payload includes scene id, timeline id, POV, digest, path, width/height, and seed.
- `on_export_started` / `on_export_completed` (Ren'Py CLI) broadcast export runs, weather bake flag, label manifest path, and error states.

## Debug Tips
- Web fallback fails? Verify a fresh Ren'Py web build exists under `<project>/web/` and that Qt WebEngine is installed. Logs surface as `runtime_mode=webview` with `webview.entry` path.
- Mini-VN digest drift? Compare `label_manifest.json` and Mini-VN snapshot digests; rerun `/api/viewer/mini/refresh` with explicit `seed` to reset caches.
- Thumbnail hooks missing? Ensure feature flag `enable_mini_vn` is enabled and watch `logs/viewer/` for stack traces from the thumbnailer (Pillow must be importable).
- Crash loops? `viewer.status` automatically clears native state and logs the exit code before promoting fallbacks—inspect `stub_reason` and `logs/viewer/renpy_viewer.log` to understand why the native window died.
