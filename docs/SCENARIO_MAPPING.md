# Scenario Mapping Guide

Date: 2025-10-21  
Owner: VN Systems (P9)

## Purpose
Document how upstream content (Story Tavern transcripts, VN pack exports, hand-authored JSON) maps onto the VN Loader schema (`comfyvn.vn.schema`) so that Mini-VN, Ren'Py export, and tooling can share a consistent surface.

## Schema Quick Reference

| Model | Key Fields | Notes |
| --- | --- | --- |
| `PersonaRef` | `id`, `displayName`, `tags[]`, `portraitRef` | Tags deduped/trimmed; portrait may resolve via asset manifest. |
| `Node` | `id`, `speaker`, `text`, `aside`, `choices[]`, `presentation` | `choices[].weight` defaults to `1.0`; `presentation` is always populated (empty placeholder allowed). |
| `Choice` | `id`, `text`, `to`, `when?`, `weight?` | Missing `to` is auto-steered to next node or `END`. |
| `Scene` | `id`, `title`, `order`, `cast[]`, `nodes[]`, `anchors[]` | `cast[]` stores lightweight persona refs; `anchors` mark bookmarks / timeline offsets. |
| `ScenarioDocument` | `projectId`, `personas[]`, `scenes[]`, `assets[]`, `metadata` | Wraps per-source payload; `metadata.source` records origin + options. |

## Input → Schema Mapping

### Story Tavern Transcript (`kind: "file"`/`"directory"`)
1. `speaker` column → `Node.speaker`. Empty speaker becomes narrator (`None`).
2. `text` column → `Node.text`. Stage directions (e.g., `[aside]`) land in `Node.aside`.
3. Choice rows emitted as `Choice` entries with `to` pointing to the labelled node id.
4. Scene headers spawn `Scene` containers; persona list assembled from transcript participants.

### VN Pack JSON (`kind: "scenario"`)
1. Existing `scene.id` reused (slugified as needed). Title falls back to `scene.id`.
2. Persona attachments (`characters[]`) map into `Scene.cast[]` and global persona registry.
3. Presentation cues (pose/expression) copy into `Node.presentation`; missing segments padded with blank placeholders for Mini-VN defaults.

### Inline Authoring (`kind: "inline"`)
1. Accepts either a single `Scene` dict, an array of `Scene` dicts, or the full `ScenarioDocument`.
2. `cast` strings automatically become `{ "id": "<slug>", "displayName": "<label>" }`.
3. Asset descriptors (bgm, cg) drop into `assets[]` and surface in `assets/manifest.json`.

## Normalisation Rules
- IDs are slugified lowercase with `_` separators and deduplicated using numeric suffixes (`scene_ep1`, `scene_ep1_2`, ...).
- Persona collisions merge tags/portraits and append trace warnings (`debug.json.trace[].warnings[]`).
- `Choice.to` default: next node id, else `"END"` sentinel for exporters.
- Anchors with missing ids become `<scene>_aNN`. Timestamp accepts seconds (float) or string; loader stores float for determinism.
- Unknown fields are preserved via `ConfigDict(extra="allow")`, allowing modders to experiment without breaking the core schema.

## Output Contracts
- **Scenes**: Each `scenes/<id>.json` matches the `Scene` model with embedded nodes/choices for single-file consumption.
- **Personas**: Each `personas/<id>.json` stores the merged `PersonaRef`. Display names keep original casing.
- **Manifest**: Enumerates scenes/personas/assets plus hook registry for downstream event bus.
- **Debug**: `debug.json` collects source metadata, build warnings, and option flags to help reproduce issues.

## Integration Notes
- Downstream exporters should rely on manifest ordering (`Scene.order`) for deterministic traversal.
- Mini-VN runtime listens to `manifest.hooks.events` for websocket topics.
- Ren'Py exporter reads `assets/manifest.json` for portrait and BGM lookups; when absent, fallback logic chooses defaults.
- To stitch Story Tavern imports, run ST mapper first to produce per-scene JSON then feed via `kind: "directory"`.

## Follow-Ups
- Auto-map Story Tavern `#scene` markers to `Scene.anchors`.
- Extend `presentation.camera` schema to include easing/transition metadata.
- Align persona tag taxonomy with `docs/STYLE_TAGS_REGISTRY.md`.
