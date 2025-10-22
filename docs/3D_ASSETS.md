# Playground 3D Asset Guide

This guide explains how to prepare assets for the Codex playground tiers. Tier-0 and Tier-1 share the same directory tree so parallax cards, overlays, and 3D actors can coexist.

---

## Directory Layout

```
assets/
└── playground/
    ├── backgrounds/           # Tier-0 far/mid cards
    ├── overlays/              # Weather overlays (fog, rain, embers…)
    ├── cards/                 # Character portrait/card billboards
    ├── stage3d/vendor/        # Bundled Three.js + VRM modules (offline)
    └── stage3d/
        ├── sets/              # Environment glTF scenes (.gltf/.glb)
        ├── actors/            # VRM or rigged glTF characters
        ├── cards/             # Billboard textures for fallback actors
        └── hdr/               # Optional environment HDRI files
```

Use relative paths inside playground configs. Example: `"gltf": "assets/playground/stage3d/actors/hero.glb"`.

---

## Accepted Formats & Expectations

### Environment Sets (`config.set`)
- **glTF/glb** meshes for scenery. Keep polygon counts modest (<1.5M triangles) to avoid GUI stalls.
- **VRM** is also accepted for stylised stage sets; flag `pickable: true` if you want to move the set with gizmos.
- **Billboard fallback**: provide `set.billboard.texture` to display a flat card when 3D loading fails.
- **HDRI**: place `.hdr` files under `stage3d/hdr` and reference via `set.hdr`. Background colour fallback is `#0f172a`.

### Characters (`config.actors`)
- Preferred: **VRM 1.x/2.0** rigs loaded via `@pixiv/three-vrm`.
- Alternative: **glTF/glb** humanoids or props.
- Every actor can include `billboard.texture` as a fallback portrait and optional `metadata` for downstream tooling.
- `pickable` defaults to `true`; set to `false` when you want to lock an actor in place.

### Cards & Overlays (`config.cards`)
- PNG/WEBP with alpha. The default plane is 2.5 × 2.5 units.
- `overlay: true` keeps the billboard in the `overlays` array of the snapshot (used for UI or weather planes).
- `metadata` and `pickable` behave the same as actors.

### Lighting (`config.lights`)
- Directional, ambient, hemisphere, and spot lights are supported.
- Omit the array to spawn the default key + ambient fill rig.
- Each light entry may carry `metadata` for custom editors.

---

## Scene Config Cheat Sheet

```jsonc
{
  "set": {
    "name": "Studio Set",
    "gltf": "assets/playground/stage3d/sets/diorama.glb",
    "hdr": "assets/playground/stage3d/hdr/studio_4k.hdr",
    "background": "#101828",
    "pickable": false,
    "metadata": { "author": "EnvTeam" }
  },
  "camera": {
    "position": [0, 1.5, 6.5],
    "target": [0, 1.25, 0],
    "fov": 45.0
  },
  "lights": [
    { "type": "directional", "name": "Key", "position": [4, 6, 8], "intensity": 2.2 },
    { "type": "ambient", "name": "Fill", "color": "#536dfe", "intensity": 0.35 }
  ],
  "actors": [
    {
      "name": "Hero",
      "vrm": "assets/playground/stage3d/actors/hero.vrm",
      "billboard": { "texture": "assets/playground/cards/hero.png" },
      "transform": {
        "position": [0, 1.35, 0.2],
        "rotation": [0, 1.57, 0],
        "scale": 1.0
      },
      "metadata": { "palette": "cyan" }
    }
  ],
  "cards": [
    {
      "name": "Backdrop",
      "billboard": { "texture": "assets/playground/cards/set_wide.png" },
      "position": [0, 1.8, -2.0],
      "size": [6.0, 3.0],
      "overlay": false
    }
  ]
}
```

Pass the config to `PlaygroundView.load_stage_scene(config)` (or `Stage3DView.load_scene`). Every field is optional—Stage 3D fills sensible defaults and falls back to billboards when it cannot load a 3D asset.

---

## Debugging & Determinism

- `Stage3DView.debug_state(callback)` returns the same payload as `stage.snapshot` without forcing a new render. `PlaygroundView.fetch_stage_debug(callback)` forwards it to higher-level tooling.
- `PlaygroundView.load_snapshot(snapshot)` restores both tiers from `render_config.json`. When only the Tier-1 snapshot is available, the view rebuilds a minimal config using cached `source` metadata (gltf/vrm/billboard paths, lights, HDR, etc.).
- `ParallaxScene.debug_state()` mirrors the current Tier-0 camera, parallax offsets, and weather state for quick CLI logging.
- To keep snapshot hashes stable:
  1. Version control the asset bundle or include a bundle hash alongside the snapshot.
  2. Avoid procedural randomness inside Three.js; rely on the recorded transforms instead.
  3. Keep HDR and large textures under version control—the loader caches the absolute path in snapshot metadata.

---

## Performance Notes

- Target < 1.5M triangles and < 512 MB total VRAM per Stage 3D scene for parity across Windows/Linux laptops and handhelds.
- Prefer glTF binaries (`.glb`) over `.gltf + textures` to reduce IO stalls inside Qt WebEngine.
- When bundling VRM physics, bake to static poses or keep secondary motion light—WebEngine lacks the headless worker threads desktop Three.js uses.
- Stage 3D now hard-resets the light rig before applying new entries. If you need additive lights, include the existing entries in the new array instead of relying on accumulation.

---

## Troubleshooting

| Issue | Cause | Fix |
| --- | --- | --- |
| Stage loads but characters are flat cards | VRM loader unavailable or file missing | Bundle the portrait `billboard.texture`; confirm `@pixiv/three-vrm` modules are in `vendor/`. |
| Snapshot missing `config` block | Stage snapshot predates the Tier-1 upgrade | Reload the scene (`PlaygroundView.load_stage_scene`) and take a new snapshot. |
| Gizmo keeps selecting the environment | Set pickable flag | Ensure `set.pickable` (or the snapshot `sets[].pickable`) is `false`. |
| HDR not applied | Path typo or unsupported format | Verify the `.hdr` file exists inside `assets/playground/stage3d/hdr/` and reload via `Stage3DView.load_scene`. |
| FOV mismatch when recreating shot | Config never set camera fov | Update `render_config.json.camera.fov` before calling `load_stage_scene` (Tier-1) or use `ParallaxScene.set_fov` (Tier-0). |

---

## Offline Bundles

- Three.js `0.159.0`, VRM `@pixiv/three-vrm@2.0.1`, and supporting loaders/controllers are vendored under `comfyvn/playground/stage3d/vendor/`. Keep their directory structure when upgrading so `viewport.html`’s import map resolves correctly.
- No network calls are made during runtime—the stage operates entirely on local assets.
