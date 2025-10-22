# Worldline Overlay & Snapshot Dev Notes

## Feature Flags
- `enable_worldlines` — unlocks the POV worldline registry, fork-on-confirm flows, and snapshot capture APIs. Defaults to `false`.
- `enable_timeline_overlay` — enables the GUI overlay lanes, Ctrl/⌘-K snapshot mode, and live scrub helpers. Defaults to `false`.
- `enable_depth2d` — optional depth-from-2D resolver backing parallax previews; auto mode emits 3–6 planes while manual masks live in `data/depth_masks/<scene>.json` with per-scene mode persisted at `cache/depth2d_state.json`.

Toggle flags in `config/comfyvn.json` or via Settings → **Debug & Feature Flags**; changes broadcast through the notifier bus so Studio picks them up immediately.

## Worldline Registry
- Registry entries (`comfyvn/pov/worldlines.py`) now persist delta-over-base metadata under `_wl_delta` and track the parent world in `_wl_delta_base`. Forking a lane clones the parent metadata, stores only the fields that diverge, and emits the merged view to callers.
- `Worldline.snapshot()` returns `{metadata, delta, lane_color}` while `WorldlineRegistry.list_payloads()` adds `active` markers and lane labels (Gold ⭐ official, Blue 🔵 VN branch, Gray ⚪ scratch).
- Modder hook `on_worldline_created` carries the new `delta` payload plus lane/parent context:
  ```json
  {
    "id": "vn_branch_rei",
    "lane": "vn_branch",
    "parent_id": "official",
    "delta": {"nodes": ["c04_n12"], "notes": "Approved branch"}
  }
  ```

## Snapshot Sidecars
- Snapshot helpers (`WorldlineRegistry.record_snapshot`, `comfyvn/gui/overlay/snapshot.py`) mint deterministic cache keys from `{scene,node,worldline,pov,vars,seed,theme,weather}` and hash them into `vars_digest`.
- Recorded entries now include provenance sidecars in both metadata and a dedicated `sidecar` block:
  ```json
  {
    "cache_key": "chapter_04:c04_n12:vn_branch_rei:rei:...",
    "workflow_hash": "a0d9b6...",
    "sidecar": {
      "tool": "comfyvn.snapshot",
      "version": "1.0.0",
      "workflow_hash": "a0d9b6...",
      "seed": 1337,
      "worldline": "vn_branch_rei",
      "pov": "rei",
      "theme": "sunset",
      "weather": "rain",
      "cache_key": "chapter_04:c04_n12:...",
      "vars_digest": "51e4...",
      "thumbnail_hash": "4b78..."
    }
  }
  ```
- Modder hook `on_snapshot` mirrors these fields so automation can archive thumbnails and sidecars without querying the registry.

## REST Surface & Debug Routes
- `/api/pov/worlds`, `/api/pov/worlds/switch`, and `/api/pov/confirm_switch` accept inline `snapshot` payloads. Missing `hash` or `workflow_hash` values are derived from the cache key; the response echoes enriched snapshot metadata.
- `/api/pov/auto_bio_suggest` summarises a worldline’s deltas, recent snapshots, and POV-masked diffs. Example:
  ```bash
  curl -s http://127.0.0.1:8000/api/pov/auto_bio_suggest \
    -H 'Content-Type: application/json' \
    -d '{"world": "vn_branch_rei", "mask_pov": true}' | jq
  ```
  Returns `{suggestions:[...]}` with summaries sourced from `_wl_delta`, diff counts, and the most recent snapshot.

## GUI Overlay & Tooling Hooks
- `TimelineOverlayController.state()` now augments each lane with `delta` alongside `diff.summary`, and every node carries `workflow_hash`, `worldline`, and the `sidecar` dictionary for quick provenance lookups.
- Snapshot scrubbers rely on `scrub_lane(lane_id, cache_key?, step)`; passing the snapshot cache key preserves deterministic navigation.
- Depth helpers (`comfyvn/visual/depth2d.py`) honour per-scene manual overrides. Use `set_depth_scene_mode(scene_id, "manual")` to persist a manual mask preference and `resolve_depth_planes(scene_id)` to retrieve the current stack for previews.

## Testing & Debugging
- Unit tests live in `tests/test_pov_worldlines.py`; extend with fixtures covering new delta cases or snapshot metadata assertions.
- To inspect registry state, call `python - <<'PY'` → `from comfyvn.pov import list_worlds; import json; print(json.dumps(list_worlds(), indent=2))` with the relevant feature flags enabled.
- Hook payloads are inspectable via `ws://127.0.0.1:8000/api/modder/hooks/ws`; filter for `modder.on_worldline_created` or `modder.on_snapshot` to validate payloads end-to-end.

