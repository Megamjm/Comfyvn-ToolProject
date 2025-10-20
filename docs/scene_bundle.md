<!-- SCENE_BUNDLE.md -->
<!-- [S2 Scene Bundle Export — ComfyVN Architect | 2025-10-20 | chat: S2] -->

# Scene Bundle Export (S2)

**Flow:** SillyTavern `/comfyvn_export` → `authoring/*.json` → `comfyvn bundle`.

**CLI**
```bash
python -m comfyvn bundle --raw authoring/comfyvn_scene_2025....json \
    --manifest assets/assets.manifest.json \
    --schema docs/scene_bundle.schema.json \
    --out bundles/demo.bundle.json

Tags recognized in lines (optional):

[[bg:room]] → inserts {"type":"scene","target_bg":"room"}

[[label:start]] → {"type":"label","name":"start"}

[[goto:next]] → {"type":"jump","goto":"next"}

[[expr:angry]] → {"type":"show","speaker":<current>,"emotion":"angry"}

If emotion missing, a small heuristic fills neutral|excited|confused|pensive|surprised.

Assets link-up: If assets/assets.manifest.json exists (A3), S2 will map
characters/<Name>/<expr>.png and bg/<name>.png into bundle assets.


# 6) Requirements (if you haven’t already)

You already added these earlier, but for completeness ensure:
Pillow>=10
jsonschema>=4.22
requests>=2.32
pytest>=8

comfyvn/
├─ scene_bundle.py # S2 builder + validator ← new
├─ cli.py # updated with bundle
tests/
├─ test_scene_bundle.py # new S2 test
docs/
├─ SCENE_BUNDLE.md # new S2 doc
configs/
├─ comfyvn.features.yaml # updated: S2 entry

