# Timeline Overlay & Snapshot Workflow

## Feature Flags
- `enable_worldlines` (default `false`) — exposes lane metadata, fork helpers, and snapshot capture on the POV routes.
- `enable_timeline_overlay` (default `false`) — builds overlay lanes (`comfyvn/gui/overlay/timeline_overlay.py`) and enables Ctrl/⌘-K snapshot mode in the GUI.
- `enable_depth2d` (default `false`) — unlocks auto/manual depth planes via `comfyvn/visual/depth2d.py` when overlays or renderers request parallax slices.

Flags live under `config/comfyvn.json → features` and can be toggled at runtime via Settings → Debug & Feature Flags.

## Lane Palette
| Lane | Color | Notes |
|------|-------|-------|
| OFFICIAL ⭐ | `#D4AF37` (Gold) | Canon timeline / base export. |
| VN Branch 🔵 | `#1E6FFF` (Blue) | Approved VN branch forks. |
| Scratch ⚪ | `#7A7A7A` (Gray) | Experimental lanes, temp work. |

`Worldline.snapshot()` now includes `lane`, `lane_color`, `lane_label`, and `parent_id`. Fork helpers default descendants to their parent lane unless explicitly overridden.

## Snapshot Metadata
- Cache keys blend `{scene,node,worldline,pov,vars,seed,theme,weather}` via `comfyvn/pov/worldlines.make_snapshot_cache_key()`. The hash (`vars_digest`) is appended to the key and reused for dedupe.
- Snapshot payload example:
  ```json
  {
    "scene": "chapter_04",
    "node": "c04_n12",
    "pov": "rei",
    "vars": {"affinity": 72, "branch": "b"},
    "seed": 1337,
    "theme": "sunset",
    "weather": "rain",
    "thumbnail": "snapshots/c04_n12.png",
    "badges": {"pov": "rei", "diff": "added"}
  }
  ```
- `/api/pov/worlds`, `/api/pov/worlds/switch`, and `/api/pov/confirm_switch` accept the payload under `snapshot`. If `cache_key` / `hash` are omitted they are derived automatically.
- Snapshot records also include a `workflow_hash` and `sidecar` payload capturing `{tool,version,workflow_hash,seed,worldline,pov,theme,weather,cache_key,thumbnail_hash}` so modders can archive provenance alongside thumbnails. Hook `on_snapshot` mirrors the same fields.
- Ctrl/⌘-K in Studio pipes through `comfyvn/gui/overlay/snapshot.SnapshotController`. Successful captures emit `on_snapshot` with the final metadata; listeners can stream via `/api/modder/hooks/ws`.

## Confirm Switch Flow
1. Client requests `/api/pov/confirm_switch` with:
   ```json
   {
     "id": "official",
     "apply": false,
     "mask_pov": true,
     "snapshot": {...},          // optional (same shape as above)
     "fork": {                   // optional fork-on-confirm
       "source": "official",
       "id": "vn_branch_rei",
       "lane": "vn_branch",
       "label": "Rei Route",
       "notes": "Approved branch",
       "metadata": {"milestone": "alpha"},
       "snapshot": {...}
     }
   }
   ```
2. Response includes the target world snapshot, optional diff (`nodes.only_in_a/b/shared`, POV-masked choices), enriched snapshot metadata (`workflow_hash`, `sidecar`, lane colour), and activation state.
3. When `fork` is supplied, the new worldline inherits metadata, lane color, and emits `on_worldline_created` before returning the diff summary.

## Overlay Controller
- `comfyvn/gui/overlay/timeline_overlay.py` builds lane payloads (`TimelineOverlayLane`) with scrub helpers, per-lane `delta` metadata (delta-over-base storage), and diff badges per snapshot:
  - `diff_badge = added|removed|changed|shared`
  - `badges.pov` mirrors the POV badge shown in the overlay thumbnail.
- Modder hooks invalidate the overlay cache:
  - `on_worldline_created` — refresh lane list & diff caches.
  - `on_snapshot` — update the lane containing the snapshot.
- Helpers:
  - `overlay_state(refresh=False)` → `{"enabled": bool, "lanes": [...]}` for GUI panels.
  - `scrub_lane(lane_id, cache_key=?, step=±1)` returns the neighbouring snapshot metadata for timeline scrubbers.
- Snapshot nodes now surface `workflow_hash`, `worldline`, and the flattened `sidecar` block for quick provenance lookups; GUI scrubbers reuse these keys when requesting media or exporting sidecars.

## Auto Bio Suggest
- `/api/pov/auto_bio_suggest` summarises a worldline’s `_wl_delta`, recent snapshots, and optional diffs against its parent (or a supplied `compare_to`).
- Request shape:
  ```json
  {"world": "vn_branch_rei", "pov": "rei", "mask_pov": true}
  ```
- Response includes `suggestions[]` (title/summary/confidence/source), the world snapshot (`delta` + lane metadata), and optional `diff` payloads when a comparison target exists. Use it to populate worldline bios, changelogs, or modder dashboards without hand-summarising every fork.

## Depth-from-2D Helpers
- `comfyvn/visual/depth2d.DEPTH2D.resolve(scene_id, plane_count=4, image_size=(1920,1080))` returns:
  ```json
  {
    "enabled": true,
    "mode": "manual",
    "source": "manual",
    "planes": [
      {"name": "foreground", "depth": 0.2, "mask": "c04_fg.png"},
      {"name": "mid", "depth": 0.5, "mask": "c04_mid.png"},
      {"name": "background", "depth": 0.85, "mask": "c04_bg.png"}
    ]
  }
  ```
- Manual masks live under `data/depth_masks/<scene>.json`; toggles persist in `cache/depth2d_state.json` (`{"scene_modes": {"chapter_04": "manual"}}`).
- Auto mode (`mode: "auto"`) emits 3–6 evenly spaced planes with per-plane bounds for parallax samplers. Consumers should respect `meta.auto` to distinguish heuristics from artist-authored planes.

## Testing & Debugging
- Toggle the feature flags, call `/api/pov/worlds` with `snapshot` payloads, and confirm deterministic `cache_key` + `hash` values on repeat captures.
- Validate fork-on-confirm by diffing the parent and child worldlines; `nodes.only_in_b` should align with the overlay's `diff_badge="added"` thumbnails.
- Depth tests: mock `DEPTH2D.load_manual_masks` to return fixtures, ensure manual overrides win when scene mode is `manual`, and verify auto planes clamp to 3–6 slices.
