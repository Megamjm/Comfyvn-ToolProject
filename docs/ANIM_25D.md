# P6 — 2.5D Animation Rig

> Auto-rig layered puppets into a deterministic bone hierarchy, expose idle/breath/blink behaviours, and wire the motion graph so previews remain safe for Stage3D playback.

## Overview

The 2.5D animation stack targets layered portrait sprites that include anchor metadata for each movable region. The system converts those anchors into a lightweight bone tree, clamps all transforms with deterministic constraints, and drives a motion graph that sequences idle, turn, and emote loops.

- **Rig builder** — `comfyvn/anim/rig/autorig.py` normalises anchors, infers roles (spine/head/eye/mouth/etc.), emits constraints, and derives mouth shapes (A/I/U/E/O) suitable for light lip-sync.
- **Motion graph** — `comfyvn/anim/rig/mograph.py` stitches idle, turn, and emote segments with guard rails that reject moves exceeding the rig’s constraints.
- **Server routes** — `comfyvn/server/routes/anim.py` exposes `/api/anim/rig`, `/api/anim/preview`, and `/api/anim/save`, wrapping feature flag `enable_anim_25d`.
- **Preset catalog** — Presets live in `cache/anim_25d_presets.json`, recording the rig, idle cycle, preview loop, and metadata so designers can reuse them in Playground/Designer.

## Rig Pipeline

1. **Anchor ingestion**  
   Submit an anchor list ordered arbitrarily. The builder normalises IDs, parents, tags, and positions, adds a `root` anchor when missing, and performs a deterministic topological sort.

2. **Role inference & constraints**  
   Roles drive constraint magnitudes:
   - `head`, `neck`, `spine`, `arm`, `leg`, `mouth`, `eyelid`, `brow`.  
   Each role gets rotation/twist/translation/scale limits sized from anchor distances (clamped to sane bounds) to prevent bone explosions.

3. **Mouth shapes**  
   Bones tagged as `mouth/jaw/lip` receive per-shape blend targets. The visemes respect the constraints and stay below 90% of the allowed travel.

4. **Idle cycle**  
   `generate_idle_cycle` crafts a deterministic loop (default 2.4s @ 24 fps) with subtle breathing, scheduled blinks, and micro mouth motion. Blink timings are seeded from the rig checksum, so the same input always yields the same cadence.

5. **Checksum & stats**  
   A SHA-1 digest over the normalised rig payload tracks determinism. Stats include bone counts per role and the available mouth shapes.

## Motion Graph

`MotionGraph.generate_preview_loop` composes:

1. Idle breath/blink loop.
2. Turn sway — only if head/neck/spine constraints allow ≥18° rotation.
3. Emote pass — cycles through {A,I,U,E,O} if shapes exist, otherwise falls back to idle.
4. A tail idle segment to close the loop seamlessly.

Guards ensure transitions never exceed configured limits. Inputs lacking the required bones gracefully fall back to idle-only previews.

## API Surface

| Route | Method | Description |
|-------|--------|-------------|
| `/api/anim/rig` | POST | Returns rig payload + idle cycle, emits `on_anim_rig_generated`. |
| `/api/anim/preview` | POST | Returns rig, idle cycle (respecting `fps`/`duration` overrides), and a preview loop (+ optional viseme sequence). Emits `on_anim_preview_generated`. |
| `/api/anim/save` | POST | Persists a named preset (`overwrite` supported) and emits `on_anim_preset_saved`. |

All endpoints require `features.enable_anim_25d` to be true. Payloads accept additional fields for future expansion; unknown keys are preserved for downstream tooling.

## Modder Hooks

Three hooks document the rig lifecycle via `comfyvn.core.modder_hooks`:

- `on_anim_rig_generated`
- `on_anim_preview_generated`
- `on_anim_preset_saved`

Each hook carries a deterministic timestamp, rig checksum, and targeted metadata so modders can build sidecar tooling, dashboards, or analytics listeners.

## Performance & Determinism Notes

- The rig builder is O(n) over anchors and avoids randomness; blink spacing uses the rig checksum as the RNG seed.
- Preview loops default to 24 fps and <5 s runtime to keep Stage3D playback smooth.
- Constraint clamping keeps transforms below 90% of the allowed travel, leaving headroom for runtime tween blends.
- Preset persistence writes to a single JSON file; concurrent edits should serialise through the REST API to avoid clobbering.

## Development Checklist

- `config/comfyvn.json` → add `"enable_anim_25d"` for smoke tests.
- `tools/check_current_system.py --profile p6_anim_25d` validates feature flag, endpoints, and documentation presence.
- See `docs/dev_notes_anim_25d.md` for debugging recipes, integration plans for Designer/Playground, and asset authoring guidelines.
