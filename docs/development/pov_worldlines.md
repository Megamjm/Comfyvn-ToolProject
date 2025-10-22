# POV Worldlines & Timeline Tooling

Updated: 2025-11-06 • Owners: Narrative Systems & Export Chats  
Scope: API contracts and automation guidance for worldline-aware branching.

---

## 1. Registry Overview
- Module: `comfyvn/pov/worldlines.py` defines the thread-safe `WorldlineRegistry` and dataclass payload (`id`, `label`, `pov`, `root_node`, `notes`, `metadata`, timestamps).
- Registry is process-local (persisted in memory alongside the POV manager). Switching a worldline updates the shared `POV` singleton so GUI panels, runners, and exports stay aligned.
- `metadata` is intentionally free-form but consumers should populate:
  - `nodes`: list of visited node identifiers for the branch.
  - `choices`: mapping `{pov_id: {node_id: choice_payload}}` for diff/merge inspection.
  - `assets`: optional list of asset references registered for the branch.
- Active world snapshot is exposed via `WORLDLINES.active_snapshot()` and mirrored onto `POVRunner.current_context()["world"]`.

## 2. REST API Surface (`/api/pov/*`)
| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/pov/worlds` | GET | Returns `{items:[...], active:{...}}` with world metadata, timestamps, and `active` marker. |
| `/api/pov/worlds` | POST | Upsert payload `{"id","label?","pov?","root_node?","notes?","metadata?","activate?"}`; activating returns the POV snapshot. |
| `/api/pov/worlds/switch` | POST | Switch to a registered worldline (`{"id": "branch_a"}`) and return `{world, pov, active}`. |
| `/api/pov/diff` | POST | Compare two worldlines (`{"source","target","mask_pov?"}`) and receive node deltas, per-POV choice maps, and asset lists. |
| `/api/diffmerge/scene` | POST | Feature-flagged richer diff with `{node_changes, choice_changes, asset_changes, timeline}` including scenario annotations when supplied. |
| `/api/diffmerge/worldlines/graph` | POST | Feature-flagged timeline graph (nodes, edges, fast-forward preview map) built from registered worldlines. |
| `/api/diffmerge/worldlines/merge` | POST | Feature-flagged dry-run/apply merge; returns `target_preview` without mutating when `apply=false`, or updated snapshot otherwise. Conflicts raise HTTP 409. |
| `/api/pov/merge` | POST | Fast-forward `source` onto `target` when no conflicting choices exist. Conflicts return HTTP 409 with details. |

### 2.1 Upsert payload example
```jsonc
{
  "id": "alice_route",
  "label": "Alice Route",
  "pov": "alice",
  "root_node": "chapter_1_intro",
  "notes": "Started from Chapter 1 override.",
  "metadata": {
    "nodes": ["chapter_1_intro", "branch_a1"],
    "choices": {
      "alice": {
        "branch_a1": {"selection": "confront"}
      }
    },
    "assets": ["backgrounds/city_night.png", "audio/bgm_route_a.ogg"]
  },
  "activate": true
}
```

### 2.2 Diff response sketch
```jsonc
{
  "ok": true,
  "world_a": {"id": "alice_route", "...": "..."},
  "world_b": {"id": "canon", "...": "..."},
  "nodes": {
    "only_in_a": ["branch_a2"],
    "only_in_b": [],
    "shared": ["chapter_1_intro", "branch_a1"]
  },
  "choices": {
    "a": {"alice": {"branch_a1": {"selection": "confront"}}},
    "b": {"narrator": {"branch_a1": {"selection": "retreat"}}}
  },
  "assets": {
    "a": ["backgrounds/city_night.png"],
    "b": ["backgrounds/cafe_day.png"]
  }
}
```

`mask_pov=false` returns the full `{pov: choices}` mapping for each world instead of limiting to the active POV.

## 3. Timeline Helpers
- `comfyvn.pov.timeline_worlds.diff_worlds(a, b, mask_by_pov=True)` backs the diff endpoint; pass `mask_by_pov=False` to compare all POVs.
- `merge_worlds(source, target, apply=True)` unifies node coverage and branch choices:
  - Conflicting entries (same `pov` + `node` with different values) trigger `{"ok": false, "conflicts": [...]}`.
  - Set `apply=false` for dry-run previews; the function returns `target_preview` without mutating the registry, matching `/api/diffmerge/worldlines/merge` behaviour.
  - Successful merges update the target metadata in-place and return `{"fast_forward": true}` when the target was a strict subset.
- World metadata is shallow-copied; maintain nested structures (like `assets`) as lists/dicts for predictable serialization.

## 4. Export & CLI Integration
- `ExportOptions.world_id` and `ExportOptions.world_mode` (`auto|single|multi`) drive Ren'Py exports.
- CLI usage:
  - `python scripts/export_renpy.py --project demo --world alice_route` → canonical Alice branch.
  - `python scripts/export_renpy.py --project demo --world-mode multi` → include every registered world.
- HTTP preview: `GET /api/export/renpy/preview?project=demo&world=alice_route`.
- Manifest snippet:
```jsonc
"worlds": {
  "mode": "single",
  "active": "alice_route",
  "worlds": [
    {
      "id": "alice_route",
      "label": "Alice Route",
      "pov": "alice",
      "root_node": "chapter_1_intro",
      "notes": "...",
      "metadata": {...},
      "created_at": "2025-11-06T10:25:00Z",
      "updated_at": "2025-11-06T12:05:11Z",
      "active": true
    }
  ]
}
```

Fork manifests inherit the worlds block unchanged so modders can diff canonical vs branch packages.

## 5. Testing & Tooling Notes
- Unit tests should cover `WorldlineRegistry` (create/update/switch/active snapshot), timeline helpers, and REST routes (`tests/test_pov_worldlines.py`).
- When scripting merges, retry on `409` with human resolution or present `conflicts` inline to the authoring team.
- Runner debug feeds (`POVRunner.current_context()`) now include `world` metadata; time-series logging can persist this to correlate exports with active branches.
- Pair worldline metadata with asset registry audits to ensure branch-specific renders (portraits/BGs) are registered before publishing.
- Feature flag `enable_diffmerge_tools` unlocks `/api/diffmerge/*`, modder hooks (`on_worldline_diff`, `on_worldline_merge`), and the Studio **Worldline Graph** dock for visual diff/merge operations. Tooling can subscribe to `/api/modder/hooks/ws` to mirror diff + merge activity in real time.
