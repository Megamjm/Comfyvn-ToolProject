# ComfyVN GUI Follow-ups (Importer Focus)

Context: Backend importer flows now publish richer metadata (TaskRegistry jobs, cached summaries, log paths). The GUI team is working in parallel; this note aggregates the items they need to wire up once backend pieces stabilise.

Needed Updates
- Surface VN importer progress using `/jobs/status/{id}` and the cached summary exposed via `GET /vn/import/{job_id}`. Show warning counts and provide “open summary” actions pointing at `summary_path`.
- Extend the pending Imports/Jobs panels to list recent VN imports (pull from TaskRegistry or an eventual `/vn/import/history` endpoint once delivered). Include timestamps + basic stats (scene/character counts).
- Add affordances for retry/cancel once backend exposes controls—stub buttons with TODO notes so UX can design placement.
- Hook into importer log artefacts (e.g., `imports/vn_<id>.log` within the user log directory) so power users can open the raw log from the GUI.
- Wire the new “Import Tools → Installers” menu entry so it opens `docs/tool_installers.md`, and add a configuration panel for registering extractor binaries (arc_unpacker, custom tools) with legal warnings.
- Add “Install” buttons in the importer settings to call `POST /vn/tools/install` with `accept_terms=true`; show progress + license confirmation, and update the registered tool list on success.

Status
- Backend support for job polling + summary retrieval is live (2025-10-21).
- Cancellation endpoint and import history feed are still on the backend roadmap.

Please coordinate with the Importer chat before shipping UI changes so we keep behaviour aligned with server expectations.
