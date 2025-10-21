# Studio Views Wiring — 2025-10-21

## Objective
- Wire Phase 2 Studio views to the refreshed importer and advisory infrastructure so UX reflects job state, asset previews, and editor affordances without manual refreshes.
- Align view events with the Jobs WebSocket payload schema and shared registries (`SceneRegistry`, `CharacterRegistry`, `AssetRegistry`).
- Provide scaffolds for planned Manga + VN Pack panels while keeping Roleplay tooling first-class.

## Reference Points
- `docs/studio_views.md` — current snapshot of view panels.
- Jobs WS shape in `comfyvn/gui/panels/jobs_panel.py`.
- Importer endpoints (roleplay, vn-pack, manga) in Phase 2 specs.
- Scene preview contract from Roleplay acceptance tests.

## Wiring Tasks
- **Jobs overlay**
  - Centralize WS subscription in `JobsPanel` and expose events via signal bus (`jobsEventBus`).
  - Panels subscribe to bus with `job_id` filter (RoleplayImportView, VNPackView, MangaImportView).
  - On `failed` events, render inline alert with `log_url` CTA.
- **Roleplay Import view**
  - Replace polling with WS-driven updates; show upload progress bar based on staged events (`uploaded`, `parsed`, etc.).
  - Embed preview iframe or JSON viewer tied to `/roleplay/imports/{job_id}/preview`.
  - Add “Re-queue” button that posts to `/roleplay/imports/{job_id}/retry` (scaffold endpoint if not live).
- **VN Pack view**
  - Provide file chooser (local path) and dry-run trigger hitting `/vn-pack/imports/dry-run`.
  - Display adapter decisions, helper usage flags, and candidate assets/scripts in tabular output.
  - Prepare import queue button (disabled until import endpoint lands) with tooltip pointing to spec.
- **Manga pipeline view**
  - Upload/archive chooser, triggers `POST /manga/imports`.
  - Render staged artifact exploration (raw → OCR → group → scenes) with placeholder file browser reading `/data/manga/{job_id}`.
  - Show warnings when stub JSON indicates incomplete processing.
- **Scenes & Characters panels**
  - Listen for `scene_cache` or `CharacterRegistry` updates triggered by importers; auto-refresh list without forcing project reload.
  - Provide “Open in Editor” action that routes to script editor or storyboard once implemented.
- **Audio + Advisory panels**
  - Audio: hook into Roleplay preview to surface latest voice assets; show link to generated audio if asset registry lists new BGM/voice items.
  - Advisory: consume new `scan_completed` WS events (Phase 7) and mark items resolved when associated scene/job updates.

## UX / Interaction Notes
- Spinner + overlay for panels while waiting on first WS event (retry fallback after 10s).
- Persist panel filters and column widths via `QSettings`.
- Ensure drag-docked layout persists; add `Reset Layout` button under View menu.

## Testing / Verification
- Simulate job lifecycle via CLI (`tools/mock_jobs_ws.py`) to confirm signals propagate to each panel.
- Manual run-through: upload Roleplay transcript, trigger VN Pack dry run, queue Manga stub → confirm panels update without reload.
- Guard against WS disconnect: auto-reconnect logs to console and show toast on second failure.

## Follow-Ups
- Integrate import/job notifications with status bar.
- Build common preview components (JSON tree, image grid) to reduce duplication across panels.
- Document signal bus API in `docs/studio_views.md` once wiring lands.
