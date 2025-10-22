# Codex Playground Overview

The Studio playground exposes two rendering tiers hidden behind feature flags. Both tiers share the same snapshot flow (`exports/playground/render_config.json`) so modders can iterate between a light parallax preview and the full WebGL stage without losing determinism.

| Tier | Flag | Purpose |
| --- | --- | --- |
| Tier-0 (2.5D) | `enable_playground` | Multi-plane parallax cards + overlays with an orbit/pan camera. |
| Tier-1 (Stage 3D) | `enable_stage3d` (requires Tier-0) | Qt WebEngine + Three.js stage that renders glTF environments and VRM/glTF actors with gizmos + light rig controls. |

Both flags default to `false` in `comfyvn/config/feature_flags.py`; enable them in `comfyvn.json → features` when you are ready to expose the playground tab.

---

## Tier-0 • Parallax Stack

- **Scene orchestration** lives in `comfyvn/playground/parallax.py`.
  - Layers are `ParallaxLayer` dataclasses with the asset id, depth, tint, and overlay metadata.
  - `ParallaxScene.load_snapshot(payload)` restores camera + layers from `render_config.json`, so Tier-0 can replay Tier-1 snapshots (and vice-versa for shared overlays).
  - `ParallaxScene.debug_state()` returns the latest composed frame, camera pose, and weather hints for quick diagnostics.
- **Camera** is driven by `OrbitController` with smooth interpolation (`yaw`, `pitch`, `distance`, `pan_x`, `pan_y`, `fov`). Mouse bindings in the preview widget: left-drag to orbit, Shift/Right-drag to pan, wheel to zoom.
- **Weather overlays** ride the same layer pipeline (`set_weather(profile, intensity)`), so fog/rain assets stay in sync with parallax offsets and snapshot determinism.
- **Snapshot** payloads include the current frame transform (offset, rotation, parallax strength) for deterministic camera replay:
  ```jsonc
  {
    "mode": "tier0",
    "workflow": "comfyvn.playground.parallax.v1",
    "seed": 424242,
    "camera": { "yaw": 0.2, "pitch": -0.05, "distance": 4.1, "fov": 48.0 },
    "layers": [
      { "name": "Sky Far", "depth": -6.0, "asset": "playground/backgrounds/far_sky" },
      { "name": "Hero Cards", "depth": -0.25, "asset": "playground/cards/hero_stack" }
    ],
    "overlays": [
      { "name": "Weather Overlay", "overlay": true, "meta": { "profile": "fog" } }
    ]
  }
  ```

---

## Tier-1 • Stage 3D

- Rendered through `comfyvn/playground/stage3d/viewport.html` inside a Qt WebEngine viewport (`Stage3DView`).
- `StageApp.loadScene(config)` now accepts a full scene descriptor:
  - `set.gltf` / `set.vrm` / `set.billboard.texture` for environments, plus optional HDRI (`set.hdr`) and background colour overrides.
  - `camera` position/target/quaternion/fov/near/far to line up Tier-0 compositions.
  - `lights` array replaces the rig; defaults spawn a key + fill if omitted. `Stage3DView.configure_lights` rewrites the rig on demand.
  - `actors` load VRM or glTF characters; failed loads fall back to billboards (portrait textures).
  - `cards` spawn parallax-aligned billboards inside Stage 3D (supports `overlay`, `pickable`, `metadata`).
- Transform gizmo shortcuts: Orbit (left drag), Pan (middle/Shift drag), Zoom (wheel), `W` translate, `E` rotate, `R` scale.
- `window.codexStage.debugState()` exposes the full runtime payload (camera, sets, actors, lights, environment) without emitting a new snapshot. `Stage3DView.debug_state(callback)` wires this to Qt, and `PlaygroundView.fetch_stage_debug(callback)` re-exposes it to the rest of Studio.
- **Snapshot** payloads mirror the scene config and now ship with set/environment metadata:
  ```jsonc
  {
    "mode": "tier1",
    "workflow": "comfyvn.playground.stage3d.v1",
    "camera": {
      "position": [0, 1.5, 6.3],
      "target": [0, 1.25, 0],
      "quaternion": [0, 0, 0, 1],
      "fov": 45.0,
      "near": 0.1,
      "far": 1000.0
    },
    "sets": [
      {
        "name": "Studio Set",
        "source": { "gltf": "assets/playground/stage3d/sets/diorama.glb" },
        "stageRole": "set",
        "pickable": false
      }
    ],
    "actors": [
      {
        "name": "Hero",
        "type": "mesh",
        "source": { "vrm": "assets/playground/stage3d/actors/hero.vrm" },
        "position": [0, 1.4, 0],
        "rotation": [0, 1.57, 0],
        "scale": [1, 1, 1]
      }
    ],
    "cards": [
      {
        "name": "Fallback Portrait",
        "type": "billboard",
        "source": { "texture": "assets/playground/cards/hero.png" },
        "overlay": false
      }
    ],
    "lights": [
      { "name": "Key", "type": "directional", "intensity": 2.2, "position": [4, 6, 8] }
    ],
    "environment": {
      "hdr": "assets/playground/stage3d/hdr/studio_4k.hdr",
      "background": "#0f172a"
    },
    "config": { "actors": [...], "lights": [...], "set": {...} }
  }
  ```

---

## Snapshot Flow & Determinism

- `PlaygroundView._finalize_snapshot` persists every capture to `exports/playground/render_config.json` with `mode`, `workflow`, `seed`, `timestamp`, and the tier payload.
- `ParallaxScene.load_snapshot(payload)` and `Stage3DView.load_scene(payload)` accept the saved config, so `PlaygroundView.load_snapshot(snapshot)` can hand modders a single API for replaying either tier.
- Stage 3D snapshots always include the last scene config under `config`. When mods ship only the serialized snapshot, you can rebuild the minimal config via `PlaygroundView._build_stage_config_from_snapshot` (exposed indirectly through `PlaygroundView.load_snapshot`).
- Snapshot hashes remain stable as long as the same asset URIs, seed, and config parameters are used. Rehydrating a snapshot should therefore be a pure function of `(render_config.json, asset bundle)`.

---

## Public API & Debug Hooks

| API | Description |
| --- | --- |
| `PlaygroundView.load_snapshot(snapshot)` | Rehydrate Tier-0 or Tier-1 from an existing `render_config.json`. |
| `PlaygroundView.debug_state()` | Returns combined tier state, feature flags, and latest Stage 3D info. |
| `PlaygroundView.fetch_stage_debug(callback)` | Async Stage 3D debug payload (no new snapshot) forwarded to Python/CLI tooling. |
| `ParallaxScene.register_hook(name, callback)` | `on_stage_load`, `on_stage_snapshot`, `on_layer_change` mirror UI events for Tier-0. |
| `Stage3DView.register_hook(name, callback)` | `on_stage_load`, `on_stage_snapshot`, `on_stage_log` mirror WebGL events for Tier-1. |
| `Stage3DView.configure_lights(entries)` | Replaces the light rig without reloading the HTML stage. |

Hooks fire in both tiers, so downstream tools (CLI logs, automations) can listen once and respond regardless of which rendering mode is active.

---

## Development Notes

- Stage 3D is optional: when Qt WebEngine is unavailable or `enable_stage3d` stays `false`, the playground falls back to Tier-0 with a status label describing the missing flag.
- All Three.js, VRM, loaders, and control scripts are vendored under `comfyvn/playground/stage3d/vendor/`; no CDN access is required during runtime or testing.
- Assets are not bundled by default. Drop glTF/VRM/card textures into `assets/playground/...` as documented in `docs/3D_ASSETS.md`.
- `PlaygroundView.debug_state()` is a convenient bridge for Studio integrations—feed its payload into logging, snapshot dashboards, or CLI tooling without having to duplicate Stage/Parallax internals.
- When upgrading Three.js/VRM, replace the vendor modules and run `PlaygroundView.fetch_stage_debug` to confirm renderer information, lights, and asset metadata match expectations on Windows/Linux smoke tests.
