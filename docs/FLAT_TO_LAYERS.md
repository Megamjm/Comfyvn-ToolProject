```text
┌───────────── Before ──────────────┐      ┌──────────── After ─────────────┐
│  Flat sprite (PNG/JPG)            │      │  layered/character/<id>/       │
│    ┌──────────────┐               │      │    cutout.png                  │
│    │ hero + bg    │               │  →   │    mask.png                    │
│    └──────────────┘               │      │    anchors.json                │
│                                   │      │  layered/background/planes/    │
│                                   │      │    00/plane.png … NN/plane.png │
└───────────────────────────────────┘      └────────────────────────────────┘
```

# Flat → Layers Pipeline

> Extract parallax-ready layers from a single illustration using rembg/SAM/SAM2 for
> segmentation, MiDaS/ZoeDepth for depth, LaMa for cleanup, and optional Real-ESRGAN
> for upscale. Interactive SAM brushes let modders refine masks directly inside the
> Playground while provenance sidecars capture every tool, version, and parameter.

## What ships in P1

- `comfyvn/pipelines/flat2layers.py` orchestrates the deterministic pipeline.
- `tools/depth_planes.py` exposes an interactive CLI to tune depth thresholds +
  parallax scale and export JSON the pipeline can reuse.
- Feature flag `features.enable_flat2layers` **defaults to false**. Enable it in
  `config/comfyvn.json` to surface the pipeline hooks/server wiring.
- Every exported asset writes a provenance sidecar (`*.prov.json`) with
  `{tool, version, params}` so downstream tools can validate the source.

## Workflow Overview

1. **Load + normalize** the source sprite (RGBA).
2. **Foreground mask** via rembg → optional SAM/SAM2 loop for brush cues.
3. **Character export**: composite foreground, store `cutout.png`, `mask.png`,
   and `anchors.json` (centroid, bounding box, coverage).
4. **Depth estimation**: MiDaS/ZoeDepth when installed; otherwise a deterministic
   luminance/position fallback. Depth is normalized to 0…1.
5. **Background plane slicing** using thresholds from `FlatToLayersOptions` or
   the CLI helper. Each plane composite lands in `layered/background/planes/{z}`.
6. **Optional clean/upscale** (Real-ESRGAN) per artifact.
7. **Provenance stamping** for every output (character, mask, anchors, planes).
8. **Hook dispatch**: pipeline publishes `on_mask_ready`, `on_plane_exported`,
   `on_debug`, and `on_complete` events to registered callbacks.

## Running the Pipeline

```python
from pathlib import Path
from comfyvn.pipelines.flat2layers import FlatToLayersPipeline, FlatToLayersOptions

pipeline = FlatToLayersPipeline()
options = FlatToLayersOptions(
    source_path=Path("assets/sprites/hero.png"),
    output_root=Path("layered"),
    plane_count=5,
    plane_thresholds=[0.05, 0.2, 0.45, 0.7],  # optional; defaults to even spread
    parallax_scale=1.35,
    enable_real_esrgan=False,                # toggle when Real-ESRGAN installed
)
result = pipeline.run(options)
print(result.cutout_path, [plane.image_path for plane in result.planes])
```

Outputs land under:

```
layered/
  character/<character-id>/
    cutout.png
    mask.png
    anchors.json
  background/planes/
    00/plane.png
    01/plane.png
    …
```

Each `*.png`/`*.json` is paired with `<name>.<ext>.prov.json` containing:

```json
{
  "provenance": {
    "id": "9b1fa5c2ea68456c8d74ed789617df6c",
    "target": "/abs/path/layered/background/planes/00/plane.png",
    "source": "flat2layers.background_plane",
    "inputs": {
      "tool": "flat2layers",
      "version": "1.0",
      "params": {
        "plane_index": 0,
        "depth_range": [0.0, 0.25],
        "plane_count": 4,
        "thresholds": [0.25, 0.5, 0.75],
        "parallax_scale": 1.0,
        "source": "hero.png"
      }
    },
    "file_hash": "…",
    "timestamp": 1731200000.12
  }
}
```

## Interactive SAM Refinement

- Initialize `SAMInteractiveSession` with your SAM2 checkpoint and call
  `attach_to_playground(playground_view)` to listen for brush events emitted from
  the Playground hooks.
- Publish brush events through the Playground bus:

```json
{"channel":"flat2layers.sam","event":"brush","points":[[512,392],[516,402]],"positive":true}
```

- To reset session state: `{"channel":"flat2layers.sam","event":"reset"}`
- Subscribers receive streaming masks via `on_mask_update` hook. Use them to draw
  overlays, run LaMa inpaints, or persist intermediate masks.

## Depth Plane Helper (`tools/depth_planes.py`)

```
python tools/depth_planes.py --depth layered/debug/depth.png --planes 5 \
       --output layered/debug/depth_planes.json --preview-dir layered/debug/previews
```

Commands inside the REPL:

- `list` view thresholds + parallax scale.
- `set <index> <value>` adjust individual thresholds (clamped 0–1).
- `percentile <index> <pct>` snap to depth histogram percentiles.
- `scale <value>` record the parallax multiplier used by the Playground.
- `preview` export quick-look masks for each plane.
- `save` write the configuration (or `quit` to exit without saving).

Feed the resulting JSON thresholds back into the pipeline run or keep them in
project docs for reproducibility.

## Debug & API Hooks

`FlatToLayersPipeline` exposes hook names (`on_start`, `on_mask_ready`,
`on_depth_ready`, `on_plane_exported`, `on_complete`, `on_debug`) for modders.
Hook payloads include relative paths, depth ranges, parallax scale, and the
provenance stamp so automation scripts can mirror results into the asset
registry or fire additional QA.

`SAMInteractiveSession` exposes `on_mask_update`, `on_brush_event`, and
`on_debug` hooks. Use them to log user edits, store revision history, or perform
background comparisons against previous masks.

## Known Limitations

- **Soft edges / hair**: SAM/SAM2 improves over rembg alone. When checkpoints are
  missing the fallback mask uses alpha + luminance heuristics; expect aliased
  edges around wispy hair. Pair with the interactive brushes before finalizing.
- **Specular backgrounds**: Highly reflective backgrounds collapse into the same
  depth bucket under the fallback estimator. Use the depth-plane CLI with
  `percentile` tweaks to keep important silhouettes separate.
- **Occluded props**: LaMa/Real-ESRGAN are optional; without them, removing the
  hero from the background leaves gaps. Run LaMa on plane masks before handing
  off to parallax or consider manual paint-overs.
- **Windows paths**: All provenance sidecars store POSIX strings. The pipeline
  normalizes paths internally so mixed Windows/Linux setups stay consistent.
- **Determinism**: identical inputs + thresholds + brush events yield identical
  outputs. Random seeds are avoided; Real-ESRGAN is called with deterministic
  tiling. The fallback gradient depth estimator is purely analytic.

## Troubleshooting

- `RuntimeError: Flat→Layers pipeline disabled` → add `"enable_flat2layers": true`
  under `features` in `config/comfyvn.json`.
- Missing rembg/SAM/MiDaS? The pipeline logs a notice and pivots to the fallback
  heuristics. Install extras with `pip install rembg segment-anything torch`.
- `depth_planes.py` cannot load `.npy` without NumPy → install `numpy`.
- Export directories are recreated on every run but not cleared; clean them
  manually if you need a fresh export (`layered/*`).

## Before / After Example

```
Input sprite: assets/sprites/demo_hero.png

layered/character/demo_hero-3c872b1d/
  cutout.png          # hero isolated with transparent background
  mask.png            # grayscale mask used for anchors + parallax occlusion
  anchors.json        # centroid=(482,412), bbox=(280,110,396,748), coverage=0.27

layered/background/planes/
  00/plane.png        # far sky + clouds
  01/plane.png        # distant mountains
  02/plane.png        # near buildings
  03/plane.png        # foreground shrubs / props (empty if none)
```

Pair the cutout with the generated anchors and parallax planes inside the
Playground to preview motion and finalize anchor tweaks before committing to the
modder asset registry.
