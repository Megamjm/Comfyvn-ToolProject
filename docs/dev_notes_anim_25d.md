# Dev Notes — 2.5D Animation Rig

## Quick Start

```bash
python tools/check_current_system.py --profile p6_anim_25d --base http://127.0.0.1:8001
```

This profile verifies:

- Feature flag `enable_anim_25d`.
- Routes `/api/anim/rig`, `/api/anim/preview`, `/api/anim/save`.
- docs: `docs/ANIM_25D.md`.

## Rig Builder Debugging

- Use the `anchors` payload capture option in Designer to export anchor snapshots (JSON). Feed them directly into `/api/anim/rig` for deterministic output.
- The rig response includes `rig.stats.role_counts`. If a role is misclassified, adjust anchor tags:
  - `mouth`, `jaw`, `lip`, `brow`, `eyelid`, `eye`, `spine`, `torso`, `chest`, `arm`, `leg`, `shoulder`.
- Enable debug logging (`COMFYVN_LOG_LEVEL=DEBUG`) to see rig generation summaries in `logs/server.log`.
- Generated mouth shapes live under `rig["mouth_shapes"]`. Values are stored as local transforms respecting the constraint envelope (<90% of travel).

## Motion Graph Tweaks

- Preview generation honours `fps` and `duration` overrides, but auto-adjusts segments if constraints fail guards (falls back to idle).
- To audition viseme sequences, pass `{"sequence": ["A","E","I","O","U"]}` in the preview request. The response echoes the applied sequence under `preview["sequence"]`.
- Guards:
  - Turn requires rotation range ≥18° on head/neck/spine bones.
  - Emote requires mouth shapes to exist.
  - Failures default to idle segments and log a debug message.

## Modder Hooks

- `on_anim_rig_generated` fires after rig construction; payload includes `checksum`, `stats`, `anchors`.
- `on_anim_preview_generated` returns `frames`, `duration`, `states`.
- `on_anim_preset_saved` provides `name`, `checksum`, `path`.
- Hooks are documented under `docs/ANIM_25D.md` and surfaced via WebSocket topic `modder.*`.

## Presets

- Stored at `cache/anim_25d_presets.json` (written on demand).
- Structure:
  ```json
  {
    "sample-puppet": {
      "name": "sample-puppet",
      "display_name": "Sample Puppet",
      "checksum": "…",
      "rig": { ... },
      "idle": { ... },
      "preview": { ... },
      "saved_at": "2024-…Z"
    }
  }
  ```
- To resynchronise in Playground, reload preset metadata from the cache file or call `/api/anim/save` again with updated anchors (`overwrite=true`).

## Integration Plan

1. Designer panel reads presets, allows quick audition of idle/preview loops.
2. Playground Stage3D preview consumes `/api/anim/preview` output to drive cutscene previews without the full runtime rig.
3. Future: extend `/api/anim/save` to push metadata into the asset registry for teams that share presets.

## Testing

- Unit smoke: `python -m compileall comfyvn/anim comfyvn/server/routes/anim.py`.
- Contract: `pytest tests/server/routes/test_anim.py` *(placeholder; add once Stage3D scaffolding lands)*.
- Manual: Hit `/api/anim/preview` with anchors covering head/eyes/mouth to confirm the motion graph cycles through idle → turn → emote → idle.
