# Props Manager & Anchor Spec

## Overview
`comfyvn/props/manager.py` hosts the in-memory registry and evaluation helpers that power `/api/props/*`. The goal for Props v1 is to let modders attach 2D overlays (FX, accessories, sweat/tear droplets, etc.) to character poses using body-part anchors, predictable layering, and tween presets while preserving provenance for generated assets.

Key updates for the P1 milestone:
- Pose-aware anchor set covering forehead, cheeks, hairline, eyes, mouth, upper torso, hands, and feet (legacy scene anchors remain for backward compatibility).
- Z-order buckets renamed to `under_bg | under_portrait | over_portrait | over_ui` to match compositing passes.
- Whitelisted condition grammar (only `weather`, `pose`, and `emotion` variables are exposed to expressions).
- Tween presets with a bounded duration cap plus supported kinds: `fade | drift | pulse | rotate | scale`.
- `ensure_prop` now records Visual Style Mapper provenance, alpha handling (`premultiplied` or `sdf_outline`), and deduplicates via a deterministic digest.

## Feature Gate
`enable_props` stays **off by default**. Toggle the flag in `config/comfyvn.json` or via the feature flag service before calling any endpoint. The system checker validates this default:

```bash
python tools/check_current_system.py --profile p1_props --base http://127.0.0.1:8001
```

## API Surface

### `GET /api/props/anchors`
Returns:
- `anchors` – dict of anchor metadata (`x`, `y`, `group`).
- `z_order` – list of supported layer buckets.
- `tween.defaults` – deep copy of the default tween payload (includes caps).
- `tween.kinds` – allowed tween kinds.
- `alpha_modes` – `["premultiplied", "sdf_outline"]`.

### `GET /api/props`
Lists ensured props (asset metadata, thumbnails, provenance, generator, alpha mode). Useful for tooling that needs to show thumbnails or audit provenance.

### `POST /api/props/ensure`
Payload (JSON):
- `prop_id` / `id` – unique identifier (required).
- `asset` – relative asset path (required).
- `style` – Visual Style Mapper label (`VISUAL_STYLE_MAPPER::<entry>`, optional).
- `tags`, `checksum`, `metadata` – optional descriptors.
- `generator` – pipeline name; defaults to `visual_style_mapper`.
- `alpha_mode` – `premultiplied` (default) or `sdf_outline`.

Behaviour:
- Computes a digest from the payload + generator + alpha mode.
- Returns `deduped: true` when the digest already exists (provides the original sidecar + thumbnail).
- Sidecar includes a `render` block with `generator` and `alpha_mode`.

Example ensure call:

```bash
curl -X POST http://127.0.0.1:8001/api/props/ensure \
  -H "Content-Type: application/json" \
  -d '{"id":"sparkle_r","asset":"props/fx/sparkle_r.png","style":"VISUAL_STYLE_MAPPER::sparkle","alpha_mode":"premultiplied"}'
```

### `POST /api/props/apply`
Payload:
- `prop_id` – ensured prop ID (required).
- `anchor` – defaults to `center` (legacy). Pose anchors such as `face_forehead`, `eyes`, `left_hand`, etc. are preferred.
- `z_order` – defaults to `over_portrait`.
- `conditions` – string or list of expressions.
- `tween` – overrides for `kind`, `duration`, `ease`, `loop`, `hold`, `stop_at_end`, optional `parameters`.
- `state` – optional snapshot; only `weather`, `pose`, and `emotion` keys are exposed to the evaluator.

Response:
- Anchor metadata (with `group` field) and resolved tween payload.
- `visible` plus per-expression `evaluations`.
- Previous ensure data (`sidecar`, `thumbnail`, `provenance`) when available.
- Whitelisted context echo.
- Emits `on_prop_applied` hook (see below).

Example apply call:

```bash
curl -X POST http://127.0.0.1:8001/api/props/apply \
  -H "Content-Type: application/json" \
  -d '{"prop_id":"sparkle_r","anchor":"right_hand","z_order":"over_portrait","conditions":["weather == \"rain\""],"tween":{"kind":"drift","duration":1.2},"state":{"weather":"rain","pose":"idle"}}'
```

### `POST /api/props/remove`
Removes an ensured prop and emits `on_prop_removed`. Response mirrors the ensured payload plus `removed_at`.

```bash
curl -X POST http://127.0.0.1:8001/api/props/remove \
  -H "Content-Type: application/json" \
  -d '{"id":"sparkle_r"}'
```

## Condition Grammar
- Grammar supports `and`, `or`, `not`, and comparison operators (`>`, `>=`, `<`, `<=`, `==`, `!=`) with chained comparisons allowed.
- Only three identifiers are exposed: `weather`, `pose`, `emotion`. Missing keys resolve to `None`; referencing any other identifier raises `400`.
- Expressions are deterministic because the evaluator rejects arbitrary attributes, function calls, or unapproved names.

Example expressions:
- `weather == "rain"`
- `pose == "attack" and emotion != "calm"`
- `emotion == "angry" and not (weather == "clear")`

## Tween Presets & Caps
- Supported kinds: `fade`, `drift`, `pulse`, `rotate`, `scale`.
- Duration is clamped to the `[0.05, 6.0]` second window. `hold` is clamped to `>= 0`.
- Default payload:

```json
{
  "kind": "fade",
  "duration": 0.45,
  "ease": "easeInOutCubic",
  "hold": 0.0,
  "stop_at_end": true,
  "loop": false,
  "caps": {
    "duration": {"min": 0.05, "max": 6.0},
    "kinds": ["fade","drift","pulse","rotate","scale"]
  }
}
```

Optional `parameters` maps are mirrored back to callers so preset authors can communicate amplitude, axes, or other effect-specific knobs.

## Anchors

| Anchor | Group | X | Y | Notes |
| ------ | ----- | --- | --- | ----- |
| `face_forehead` | pose | 0.50 | 0.16 | Stickers for sweat drops, halos, blush overlays. |
| `hairline` | pose | 0.50 | 0.12 | Hair accessories, bangs FX. |
| `eyes` | pose | 0.50 | 0.24 | Eye overlays, tear trails. |
| `cheek_l` | pose | 0.35 | 0.30 | Left cheek blush / FX. |
| `cheek_r` | pose | 0.65 | 0.30 | Right cheek blush / FX. |
| `mouth` | pose | 0.50 | 0.36 | Mouth decals, speech bubbles. |
| `upper_torso` | pose | 0.50 | 0.48 | Jackets, chest emblems, torso glow. |
| `left_hand` | pose | 0.28 | 0.68 | Held items or FX for the character's left hand. |
| `right_hand` | pose | 0.72 | 0.68 | Held items or FX for the character's right hand. |
| `feet` | pose | 0.50 | 0.90 | Grounded FX (splashes, dust kicks). |
| `center` | legacy | 0.50 | 0.55 | Backward compatible dialogue focal point. |
| `root` | legacy | 0.50 | 0.50 | Scene centre reference. |
| `left` | legacy | 0.18 | 0.60 | Legacy shoulder anchor. |
| `right` | legacy | 0.82 | 0.60 | Legacy shoulder anchor. |
| `upper` | legacy | 0.50 | 0.25 | Legacy ceiling anchor. |
| `lower` | legacy | 0.50 | 0.85 | Legacy ground anchor. |
| `foreground` | legacy | 0.50 | 0.90 | Legacy front overlay. |
| `background` | legacy | 0.50 | 0.20 | Legacy background overlay. |

Coordinates remain normalised to `[0,1]` relative to the render surface. The `group` flag helps editors separate pose-specific anchors from legacy scene anchors.

## Ensure-Prop Rendering Pipeline
- `generator` defaults to `visual_style_mapper`; override if an external pipeline generated the asset.
- `alpha_mode` controls downstream compositing: choose `premultiplied` for standard PNG overlays or `sdf_outline` when feeding signed-distance-field glyphs into shader stages.
- Sidecars carry:
  - Canonical prop metadata (`prop_id`, `asset`, `style`, `tags`).
  - `render` block (`generator`, `alpha_mode`).
  - Thumbnail path (`thumbnails/props/<digest>.png`).
  - Optional metadata payload (must be JSON serialisable).
- Provenance adds UTC timestamp, digest, and generator label. Deduplication is keyed off the digest so repeated ensures remain deterministic.

## Hooks & Debugging
- `on_prop_applied` – payload mirrors the apply response and now includes the `sidecar` block so automation can infer alpha modes or provenance without a follow-up request.
- `on_prop_removed` – emitted when a prop is deleted from the registry; includes sidecar, provenance, thumbnail, and `removed_at`.
- Subscribe via `/api/modder/hooks/subscribe` (topics `on_prop_applied`, `on_prop_removed`) or register listeners with `modder_hooks.register_listener`.
- Server logs include `comfyvn.server.routes.props` entries for ensure/apply/remove actions. Use them when triaging tween or condition issues.

## Verification Checklist
- `python tools/check_current_system.py --profile p1_props --base http://127.0.0.1:8001`
- `pytest tests/test_props_routes.py` (covers ensure dedupe, condition evaluation, tween defaults, hook emission).
- Smoke the REST endpoints on Windows/Linux targets via the `curl` samples above.
- Confirm repeated ensures return `deduped: true` and identical thumbnails when inputs are unchanged.
- Validate alpha handling by loading the returned thumbnail/sidecar in your compositing pipeline (premultiplied vs. SDF).
