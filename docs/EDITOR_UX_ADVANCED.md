# Editor UX — Blocking Assistant & Snapshot Sheets

Feature flag baseline (both default **OFF**):

- `features.enable_blocking_assistant`
- `features.enable_snapshot_sheets`

Enable through `config/comfyvn.json` or Settings → Debug & Feature Flags before calling the endpoints described below. The checker profile `p6_editor_ux` expects both flags disabled by default and verifies route discovery via:

```bash
python tools/check_current_system.py --profile p6_editor_ux --base http://127.0.0.1:8001
```

---

## Blocking Assistant

**Endpoint**: `POST /api/editor/blocking`  
**Purpose**: Deterministic shot + beat suggestions (“give me 3 angles + 2 beats”) scoped to the current scene/node context. The assistant never mutates runner state; callers must apply the plan manually after review.

### Request payload

| Field | Type | Notes |
|-------|------|-------|
| `scene` | object (optional) | Scene payload (id/title/nodes/cast) used to infer characters and POV when no node is supplied. |
| `node` | object (optional) | Inline node payload. Overrides `node_id` search when provided. |
| `node_id` | string (optional) | Node identifier used to look up the node inside `scene.nodes`. |
| `pov` | string (optional) | Explicit POV hint (falls back to scene/default). |
| `angles` | int (default 3) | Number of shot entries (1–8). |
| `beats` | int (default 2) | Number of beat summaries (1–10). |
| `style` | string (optional) | Free-form style tag copied into each shot’s notes block. |
| `prompt` | string (optional) | Intent string passed to the (optional) Narrator role mapper. |
| `seed` | int (optional) | XOR’d into the deterministic seed derived from payload content. |
| `metadata` | object (optional) | Caller-provided context echoed back in the response. |

### Response schema

The assistant returns a JSON object with the following top-level keys:

- `schema`: Version tag (`"p6.blocking.v1"`).
- `summary`: English summary describing shot/beat counts and deterministic seed.
- `context`: `{scene_id, scene_title, node_id, pov, characters[]}`.
- `shots[]`: Ordered shot plan entries (`id`, `angle_key`, `label`, `composition`, `focus[]`, `beat_ids[]`, `camera{lens_mm,height,movement,notes}`, `notes{style}`).
- `beats[]`: Ordered beat summaries (`id`, `order`, `summary`, `focus[]`, `emotion`, `keywords[]`, `source{scene_id,node_id,index,type}`).
- `determinism`: `{seed, seed_hex, digest}` — digest is the SHA-1 hash of the plan payload.
- `narrator_plan`: Present when `features.enable_llm_role_mapping=true`. Mirrors `ROLE_ORCHESTRATOR.plan(role="Narrator", dry_run=True)` so tooling can inspect adapter assignments without consuming budget.
- `request`: Normalised echo of the submitted payload.

### Modder hook

`on_blocking_suggested` (REST + WS via `/api/modder/hooks`):

```json
{
  "scene_id": "scene_01",
  "node_id": "beat_intro",
  "plan_digest": "d7f66f6c2a40...",
  "seed": 237615933,
  "shots": ["shot-01", "shot-02", "shot-03"],
  "beats": ["beat-01", "beat-02"],
  "pov": "narrator",
  "style": "noir",
  "timestamp": 1730068800.42
}
```

Use this to trigger downstream automation (storyboards, camera presets, animation previews) without scraping the REST response.

### Debug checklist

1. Ensure the feature flag is ON.
2. `curl -X POST http://127.0.0.1:8001/api/editor/blocking -H 'Content-Type: application/json' -d '{"scene":{"id":"demo"}}' | jq`.
3. Watch `logs/server.log` for `comfyvn.editor.blocking_assistant` logs (set `LOG_LEVEL=DEBUG` for verbose output).
4. Tail the modder hook bus via `/api/modder/hooks/ws` and confirm `on_blocking_suggested` envelopes match the REST digest.

---

## Snapshot Sheets

**Endpoint**: `POST /api/editor/snapshot_sheet`  
**Purpose**: Assemble scene or timeline thumbnails into a deterministic contact sheet (PNG + optional PDF) for feedback reviews and milestone drops.

### Request payload

| Field | Type | Notes |
|-------|------|-------|
| `items[]` | array | Each entry may include `id`, `node_id`, `snapshot_id`, `image`, `thumbnail{path,filename}`, `caption`, `metadata`. The builder resolves image paths in the following order: explicit `image`, `thumbnail.path`, `thumbnail.filename` under `cache/viewer/thumbnails/`, slugged `snapshot_id/node_id/id` PNG under the same cache. |
| `layout` | object (optional) | Controls grid layout. Defaults: `{columns:3, cell_width:512, cell_height:288, margin:48, padding:24, caption_height:72, header_height:96, background:"#101010", caption_color:"#f1f1f1", font_size:20}`. |
| `title` / `subtitle` | string (optional) | Rendered above the grid. |
| `project_id` / `timeline_id` | string (optional) | Stored in the response context and hook payloads for traceability. |
| `outputs` | array (optional) | Subset of `["png","pdf"]`. Defaults to `["png"]`. Output files land in `exports/snapshot_sheets/`. |
| `metadata` | object (optional) | Echoed in the response `context.metadata`. |

### Response schema

- `sheet_id`: Deterministic identifier (`sheet-<digest-prefix>`).
- `digest`: SHA-1 digest of the normalised request payload.
- `outputs[]`: `{format, path, sheet_id, digest, width, height}` for each artefact generated.
- `items[]`: `{id, node_id, caption, path, missing}` so clients can highlight missing tiles.
- `layout`: Echo of the resolved layout configuration.
- `context`: `{project_id, timeline_id, title, subtitle, metadata}`.

### Output artefacts

- PNG: Full-resolution board (`exports/snapshot_sheets/<sheet_id>.png`).
- PDF (optional): Single-page vectorised export suitable for print decks (`exports/snapshot_sheets/<sheet_id>.pdf`).

### Modder hook

`on_snapshot_sheet_rendered` payload:

```json
{
  "sheet_id": "sheet-9fd3178c4a",
  "digest": "9fd3178c4aba85b2c4d5b0c5619f7fe5d1b3727b",
  "outputs": [
    {"format": "png", "path": "exports/snapshot_sheets/sheet-9fd3178c4a.png", "width": 2048, "height": 1536}
  ],
  "project_id": "vn_demo",
  "timeline_id": "branch_a",
  "item_count": 6,
  "timestamp": 1730068805.12
}
```

Listen for this event to sync generated boards into external asset registries or to notify collaborators when a review sheet is ready.

### Debug checklist

1. Confirm the feature flag is ON.
2. Seed the thumbnail cache (`cache/viewer/thumbnails/*.png`). Use `MiniVNPlayer.generate_snapshot()` or existing renders.
3. `curl -X POST http://127.0.0.1:8001/api/editor/snapshot_sheet -H 'Content-Type: application/json' -d '{"items":[{"snapshot_id":"scene_intro"}],"title":"Act I"}' | jq`.
4. Verify PNG/PDF outputs under `exports/snapshot_sheets/`.
5. Watch modder hooks (`/api/modder/hooks/ws`) for `on_snapshot_sheet_rendered`.

---

## Related resources

- Development note: `docs/development/dev_notes_editor_blocking.md` (debug CLI snippets, hook payloads, deterministic seed reference).
- `comfyvn/editor/blocking_assistant.py` — shot/beat generator core.
- `comfyvn/editor/snapshot_sheet.py` — snapshot compositor.
- FastAPI routes: `comfyvn/server/routes/editor.py`.
- Feature flags: `config/comfyvn.json`, `comfyvn/config/feature_flags.py`.
