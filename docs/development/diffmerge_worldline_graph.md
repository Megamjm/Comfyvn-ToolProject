# Diff/Merge Toolkit & Worldline Graph Panel

## Feature flag & scope
- Feature flag: `enable_diffmerge_tools` (default `false`). Toggle via `config/comfyvn.json → features` or `COMFYVN_ENABLE_DIFFMERGE_TOOLS=1`.
- Modules: `comfyvn/diffmerge/scene_diff.py`, `comfyvn/diffmerge/worldline_graph.py`, GUI dock `comfyvn/gui/panels/diffmerge_graph_panel.py`.
- Routes: `/api/diffmerge/scene`, `/api/diffmerge/worldlines/graph`, `/api/diffmerge/worldlines/merge`.

## API walkthrough
```bash
# POV-masked diff (added/removed/changed nodes & choices)
curl -s http://127.0.0.1:8000/api/diffmerge/scene \
  -H 'Content-Type: application/json' \
  -d '{"source":"branch_a","target":"canon","mask_pov":true}' | jq '.node_changes'

# Timeline graph with fast-forward previews
curl -s http://127.0.0.1:8000/api/diffmerge/worldlines/graph \
  -H 'Content-Type: application/json' \
  -d '{"target":"canon","worlds":["branch_a"],"include_fast_forward":true}'

# Apply merge (conflicts raise HTTP 409)
curl -s -X POST http://127.0.0.1:8000/api/diffmerge/worldlines/merge \
  -H 'Content-Type: application/json' \
  -d '{"source":"branch_a","target":"canon","apply":true}'
```
- `target_preview` mirrors the post-merge snapshot without mutating the registry when `apply=false`.
- Structured logs (`comfyvn.server.routes.diffmerge`) include `diff_changed_nodes`, `graph_node_count`, `merge_fast_forward`, and `merge_added_nodes` for Ops dashboards.

## Modder hooks & automation
- `on_worldline_diff`: fires after each diff request, payload includes `{source,target,mask_pov,node_changes,choice_changes,timestamp}`.
- `on_worldline_merge`: emits for preview and apply paths, covering `{apply,fast_forward,added_nodes,conflicts?,timestamp}`.
- Subscribe via `/api/modder/hooks/ws` to mirror diff/merge activity in automation pipelines.

## Studio panel
- **Modules → Worldline Graph** dock respects the feature flag, auto-loads `/api/pov/worlds`, and renders up to 1k nodes without freezing.
- Panel actions:
  1. **Render Graph** fetches `/api/diffmerge/worldlines/graph` and paints timelines.
  2. **Apply Merge** posts to `/api/diffmerge/worldlines/merge` with `apply=true` and reloads when successful.
- Yellow nodes highlight divergence from the target worldline; teal marks the active target.

## Debug & verification checklist
- [x] Feature flag defaults to `false`; enabling exposes REST + GUI panel.
- [x] API sample curls return masked node/choice deltas, graph payload, and dry-run merge preview.
- [x] Modder hooks observed via `/api/modder/hooks/ws` during diff + merge apply preview.
- [x] GUI panel renders 1k mocked nodes without freezing (stress-run via `tests/test_diffmerge_routes.py`).
- [x] Logs: `logs/server.log` captures structured diff/merge entries; GUI emits status text per render/merge.
- [x] Determinism: repeated diff + merge preview calls with identical worldlines return identical payloads.
