# Dev Notes — Editor Blocking Assistant & Snapshot Sheets

Updated: 2025-10-27

## Flags & routes

- Blocking Assistant → `features.enable_blocking_assistant`
- Snapshot Sheet Builder → `features.enable_snapshot_sheets`
- Routes live under `comfyvn/server/routes/editor.py` (`/api/editor/blocking`, `/api/editor/snapshot_sheet`)
- Deterministic core logic: `comfyvn/editor/blocking_assistant.py`, `comfyvn/editor/snapshot_sheet.py`

## Quick enable

```bash
# 1. Flip flags locally
jq '.features.enable_blocking_assistant=false | .features.enable_snapshot_sheets=false' config/comfyvn.json

# 2. Fire up the server (LOG_LEVEL=DEBUG recommended)
LOG_LEVEL=DEBUG python comfyvn/server/app.py
```

Flags default to OFF. Toggle them in Studio (Settings → Debug & Feature Flags) or edit `config/comfyvn.json` directly and restart the backend.

## Blocking Assistant drills

```bash
cat <<'JSON' > /tmp/blocking-request.json
{
  "scene": {
    "id": "demo_scene",
    "title": "Demo Scene",
    "cast": [{"id": "aya", "name": "Aya"}, {"id": "mori", "name": "Mori"}]
  },
  "angles": 3,
  "beats": 2,
  "style": "noir"
}
JSON

curl -s http://127.0.0.1:8001/api/editor/blocking \
  -H "Content-Type: application/json" \
  -d @/tmp/blocking-request.json | jq '.determinism, .shots[], .beats[]'
```

Observations:

- `determinism.seed_hex` stays stable for identical payloads. Override with `seed` for A/B plans.
- `narrator_plan` appears only when `features.enable_llm_role_mapping=true`.
- Hook bus (`/api/modder/hooks/ws`) carries `on_blocking_suggested` envelopes with the same digest so dashboards don’t need to diff REST payloads.

### Debug logging

Enable `LOG_LEVEL=DEBUG` to surface `comfyvn.editor.blocking_assistant` traces:

- A line for the resolved seed, node, and character roster.
- Emission of the modder hook (caught exceptions are logged at DEBUG and suppressed to keep the API deterministic).

## Snapshot sheet drills

Populate the thumbnail cache first (Mini-VN or existing captures). Example:

```python
from comfyvn.viewer.minivn.player import MiniVNPlayer
player = MiniVNPlayer(project_id="demo")
snapshot, thumbs = player.generate_snapshot(seed=42)
print([t.path for t in thumbs.values()])
```

Then call the sheet builder:

```bash
cat <<'JSON' > /tmp/sheet-request.json
{
  "title": "Act I Blocking Review",
  "subtitle": "Timeline A — Seed 42",
  "project_id": "demo",
  "timeline_id": "timeline_a",
  "outputs": ["png", "pdf"],
  "items": [
    {"snapshot_id": "scene_intro", "caption": "Intro • Establishing"},
    {"snapshot_id": "scene_choice", "caption": "Branch setup"},
    {"snapshot_id": "scene_cliffhanger"}
  ]
}
JSON

curl -s http://127.0.0.1:8001/api/editor/snapshot_sheet \
  -H "Content-Type: application/json" \
  -d @/tmp/sheet-request.json | jq '.outputs'
```

Artefacts land under `exports/snapshot_sheets/`. Deterministic digest includes layout, outputs, and ordered `items[]` payloads, so identical requests reuse filenames.

### Asset resolution order

1. `item.image` (absolute or repo-relative path)
2. `item.thumbnail.path`
3. `cache/viewer/thumbnails/<thumbnail.filename>`
4. `cache/viewer/thumbnails/<slug>.png` (slug derived from `snapshot_id`, `node_id`, or `id`)

Missing assets render a placeholder tile with a `[missing]` caption prefix. Check the response `items[].missing` flag to branch UI states.

### Hook payload

```json
{
  "event": "on_snapshot_sheet_rendered",
  "sheet_id": "sheet-b73152f4cc",
  "outputs": [
    {"format": "png", "path": "exports/snapshot_sheets/sheet-b73152f4cc.png"}
  ],
  "item_count": 3,
  "timestamp": 1730068805.12
}
```

Use this to auto-push sheets into shared drives or send Studio notifications.

## Determinism reference

- Blocking assistant seed material: scene id, node id, requested angles/beats/style/pov/prompt, plus line text from `node.lines/dialogue`. Provide a custom `seed` to XOR in overrides.
- Snapshot sheet digest: normalised request payload (item order sensitive). Captions do **not** affect layout dimensions but do modify the digest (so review notes stay versioned).

## Troubleshooting

- **403** → Feature flag is still OFF. Toggle + restart.
- **400** (blocking) → Malformed payload; ensure `scene` is an object and `angles/beats` fall within documented ranges.
- **400** (sheet) → Empty `items[]`. Provide at least one entry.
- **Missing thumbnails** → Confirm file exists under `cache/viewer/thumbnails/` and matches `snapshot_id` slug (`scene_intro.png`).
- **Hook not firing** → Ensure `/api/modder/hooks/ws` is subscribed or check `logs/server.log` for suppressed exceptions.

## Verification checklist

- [ ] Flags default to OFF in `config/comfyvn.json`.
- [ ] `python tools/check_current_system.py --profile p6_editor_ux` passes.
- [ ] `/api/editor/blocking` returns JSON schema documented above.
- [ ] `/api/editor/snapshot_sheet` writes PNG (and PDF when requested).
- [ ] Modder hooks fire once per call with deterministic payloads.
