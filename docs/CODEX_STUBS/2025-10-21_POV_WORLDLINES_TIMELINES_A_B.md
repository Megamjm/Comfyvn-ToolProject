# Work Order — POV Worldlines & Timelines (A/B)

**Status:** Delivered 2025-11-06 • Owners: Narrative Systems & Export Chats  
**Tracks:** POV manager extensions, timeline diff/merge tooling, export integration, documentation sweep.

## Summary
- Implemented `comfyvn/pov/worldlines.py` with a thread-safe registry + `Worldline` dataclass (id, label, pov, root, notes, metadata, timestamps) and convenience helpers for create/update/switch.
- Added `comfyvn/pov/timeline_worlds.py` diff/merge utilities so automation can compare node coverage and fast-forward non-conflicting branches.
- New FastAPI surface `comfyvn/server/routes/pov_worlds.py` exposes `/api/pov/worlds`, `/api/pov/worlds/switch`, `/api/pov/diff`, and `/api/pov/merge`; payloads include metadata + activation snapshot for tooling.
- Updated `POVRunner.current_context()` to surface the active worldline and extended `/api/pov/get` to include world state for GUI/CLI clients.
- `RenPyOrchestrator` gained `ExportOptions.world_id/world_mode`, embedding world selections in `export_manifest.json`; CLI (`scripts/export_renpy.py`) and `/api/export/renpy/preview` accept `--world` / `--world-mode`.

## Acceptance Checklist
- ✅ Switching worldlines updates the shared POV manager and returns the runner snapshot.
- ✅ `/api/pov/worlds` supports list/create/switch with metadata echo for modder dashboards.
- ✅ `/api/pov/diff` reports node and choice deltas; `/api/pov/merge` fast-forwards when conflict-free.
- ✅ Export pipeline can target a specific worldline or emit multi-world “master” manifests.
- ✅ Documentation refreshed (`README.md`, `architecture.md`, `architecture_updates.md`, `CHANGELOG.md`, `docs/POV_DESIGN.md`, `docs/dev_notes_modder_hooks.md`) with new development note (`docs/development/pov_worldlines.md`).

## Follow-ups / Risks
- Persisting worldlines to disk (e.g., under `data/worldlines/*.json`) remains future work; current registry is in-memory.
- Diff/merge relies on clients populating `metadata.nodes`/`metadata.choices`; consider schema validation before Phase 7.
- Tests pending finalisation (`tests/test_pov_worldlines.py`) to harden registry and API behavior.
