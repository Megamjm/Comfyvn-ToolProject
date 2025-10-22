# POV Core & Runner

## Overview
Phase 6 introduces a first-class point-of-view (POV) pipeline so narrative forks, Ren'Py exports, and live previews stay in sync. The objective is to keep the manager deterministic while exposing enough hooks for tools, tests, and modders to experiment with alternate perspective filters.

- **Managers** persist the active POV and history. They provide slot helpers so save forks encode a stable POV suffix.
- **Runners** evaluate minimal scene metadata (cast, nodes, narrator cues) and emit candidate POVs for the UI.
- **Bridges** expose REST endpoints under `/api/pov/*` and GUI presenters that subscribe to the POV bus.
- **Worldlines** capture named POV/timeline forks (id, label, pov, root node, notes, metadata), enabling branch comparisons, fast-forward merges, and export selection for canonical or multi-world builds.

## Architecture
- `comfyvn.pov.manager.POVManager`: tracks `current`, `history`, and per-slot counters. The manager is thread-safe and intentionally minimal to keep the API predictable for modders calling it via Python plugins.
- `comfyvn.pov.runner.POVRunner`: resolves POV candidates for a given scene, runs filter pipelines, and houses placeholder connectors for LoRA or render cache awareness.
- `comfyvn.pov.worldlines.WorldlineRegistry`: thread-safe registry for named worldlines; switching a world updates the shared POV manager and exposes metadata for GUI/tools.
- `comfyvn.pov.timeline_worlds`: helpers for analysing world metadata (`nodes`, `choices`, `assets`) and powering the diff/merge utilities consumed by the REST surface.
- `comfyvn.server.routes.pov`: thin REST wrapper that delegates to the manager/runner and validates payloads.
- `comfyvn.server.routes.pov_worlds`: REST surface for `/api/pov/worlds`, `/api/pov/diff`, and `/api/pov/merge`, providing automation-friendly payloads for modders.
- `comfyvn.server.routes.diffmerge`: feature-flagged (`enable_diffmerge_tools`) router exposing `/api/diffmerge/{scene,worldlines/graph,worldlines/merge}` with POV-masked diffs, timeline graphs, and dry-run/apply merges plus structured logging + modder hooks.
- `comfyvn.gui.central.center_router.CenterRouter`: keeps the VN viewer and Character Designer in sync while surfacing quick actions for assets, timelines, and logs.
- `comfyvn.gui.central.character_designer.CharacterDesigner`: lightweight CRUD surface that loads characters from the shared registry and persists notes for render planning.

Each component is intentionally documented with inline stub methods (e.g. `POVRunner.ensure_render_assets`) so teams can expand the behavior without reworking the scaffolding.

## API Surfaces
- `GET /api/pov/get`: return current POV snapshot (`debug=true` adds runner context).
- `GET /api/pov/worlds`: list known worldlines with metadata + active marker.
- `POST /api/pov/worlds`: create or update a worldline (optional `activate`/`switch` flag).
- `POST /api/pov/worlds/switch`: activate a registered worldline and surface the updated POV snapshot.
- `POST /api/pov/auto_bio_suggest`: return POV-masked bios and delta summaries for a worldline (`{"world","pov?","mask_pov?","compare_to?"}`) using `_wl_delta`, recent snapshots, and diff helpers.
- `POST /api/pov/diff`: compare two worldlines (`{"source","target","mask_pov"}`) returning node/choice deltas and asset references.
- `POST /api/diffmerge/scene`: richer POV-masked diff with `{node_changes, choice_changes, asset_changes, timeline}`; accepts optional scenario payloads to annotate nodes. Feature flag `enable_diffmerge_tools`.
- `POST /api/diffmerge/worldlines/graph`: returns graph-friendly timelines, node/edge lists, and fast-forward previews (`fast_forward` map); dry-run results never mutate the registry.
- `POST /api/diffmerge/worldlines/merge`: merges or previews worldlines (`apply=false`) using the same conflict detection as `merge_worlds`, returning `target_preview` for tooling.
- `POST /api/pov/merge`: fast-forward one world onto another when there are no conflicting choices.
- `POST /api/pov/set`: switch the active POV (validated string).
- `POST /api/pov/fork`: produce a POV-aware save slot label.
- `POST /api/pov/candidates`: list possible POVs for the supplied scene (optional `debug` trace).
- `GET /api/viewer/status`: report the viewer center's state. This powers the GUI idle message and is safe to call when the backend runs headless.

LLM adapters and narrator/chat panels can query `POVRunner.current_context()` to capture a normalized perspective package (`{pov, history, filters, world}`) without touching manager internals.

## Worldlines & Timeline Tools
- Registry payloads expose `metadata.nodes`, `metadata.choices`, and `metadata.assets` so automation can diff branch reach and choice overrides.
- `comfyvn.pov.timeline_worlds.diff_worlds(a, b, mask_by_pov=True)` underpins `/api/pov/diff`; masking limits choice comparisons to the active POV when desired. Enhanced helpers in `comfyvn/diffmerge/scene_diff.py` expand the diff with node/choice/asset deltas and scenario annotations.
- `merge_worlds(source, target)` unifies node coverage and branch choices, aborting with a `409` when conflicting selections exist. Successful merges emit `fast_forward=True` when the target was a strict subset.
- Ren'Py exports honour world selection (`--world`, `--world-mode`) and embed the resolved manifest under `manifest["worlds"] = {"mode","active","worlds":[...]}` for modders.
- Feature flags `enable_worldlines` + `enable_timeline_overlay` (both default `false`) unlock OFFICIAL⭐/VN Branch🔵/Scratch⚪ lanes. `comfyvn/pov/worldlines.py` tracks `lane`/`lane_color` metadata, persists `_wl_delta` payloads so forks store only their delta over the parent, emits `on_worldline_created` when forks spawn, and captures deterministic snapshot cache keys blending `{scene,node,worldline,pov,vars,seed,theme,weather}`. GUI overlay wiring lives in `comfyvn/gui/overlay/timeline_overlay.py`.
- `/api/pov/worlds`, `/api/pov/worlds/switch`, and `/api/pov/confirm_switch` now accept inline `snapshot` payloads (same cache-key recipe) so Ctrl/⌘-K captures can be committed before or after a lane switch. Confirming a switch can fork straight to a VN Branch lane; responses include diff summaries (`diff.nodes.{only_in_a,only_in_b,shared}`) for overlay badges and now echo `workflow_hash` + `sidecar` metadata in the snapshot block.
- Snapshot capture delegates to `comfyvn/gui/overlay/snapshot.py` which funnels through `WorldlineRegistry.record_snapshot()` and emits `on_snapshot` envelopes for dashboards. Badges default to the active POV; additional markers can be added per snapshot via `badges` metadata. Envelopes now include `workflow_hash`, `sidecar`, and lane colour so automation can persist provenance alongside thumbnails.
- Depth-from-2D planes toggle with feature flag `enable_depth2d`. Auto mode provides 3–6 evenly spaced planes (`comfyvn/visual/depth2d.py`), while manual masks live at `data/depth_masks/<scene>.json` and override when a scene’s mode is set to `manual` (persisted in `cache/depth2d_state.json`). Editors can inspect/resample manual masks before toggling the flag.

## Debug & Extensibility Hooks
- `POVManager.snapshot()` returns a serializable dictionary, making it easy to dump into debug overlays or CLI status commands.
- `POVRunner.register_filter(name, func)` allows runtime injection of filters that veto POV candidates. Filters are stored in insertion order, making priority rules predictable.
- GUI `CenterRouter` emits `view_changed` whenever the viewer/designer switches so modders can attach quick actions.
- `CharacterDesigner.refresh(select_id=...)` keeps upstream registries and designer notes aligned when running automation scripts.
- `/api/pov/candidates` returns filter traces when `debug=true` so contributors can reason about why entries were pruned.
- `/api/pov/worlds` snapshots include notes/metadata so GUI overlays and automation scripts can surface provenance (e.g., branch root node, asset coverage, diff history).
- `POVRunner.current_context()["world"]` mirrors the active worldline payload, ensuring render/export adapters can track branch provenance.

## Development Notes
- Tests should live under `tests/pov/` and exercise manager state transitions, runner filtering, and slot suffix stability across forks.
- Add regression tests for `WorldlineRegistry` (create/update/switch), diff/merge helpers, and the REST surface (`tests/test_pov_worldlines.py`).
- Timeline overlay helpers (`comfyvn/gui/overlay/timeline_overlay.py`) expect snapshot metadata to include deterministic cache keys; tests should validate badge assignment (added/removed/changed) by diffing sample worldlines. Snapshot capture stubs (`comfyvn/gui/overlay/snapshot.py`) should be covered with dry-run payloads asserting dedupe + fork flows.
- Depth plane manager (`comfyvn/visual/depth2d.py`) deserves coverage for auto plane bounds, manual mask fallback, and per-scene mode persistence.
- CLI introspection lives in `CODEX_STUBS/POV_RUNNER_NOTES.md` to keep quick sketch code out of production modules.
- Use `scripts/export_renpy.py --world <id> --world-mode multi` to preview multi-world manifests; the orchestrator reports `worlds` data in both dry-run and full summaries.
