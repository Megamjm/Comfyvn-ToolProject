# Visual Style Mapper

This prompt pack maps prop identifiers and battle outcomes to palette, material, and lighting presets used across Studio overlays. Use it as the canonical source when tagging props via `/api/props/ensure` or pairing battle winners with scene dressing.

| Mapper Key | Usage | Notes |
| ---------- | ----- | ----- |
| `VISUAL_STYLE_MAPPER::torch` | Hand-held torch / flame props | Warm palette, emissive bloom, particle sparks. |
| `VISUAL_STYLE_MAPPER::banner` | Faction banners, pennants | Saturated cloth, mild wind motion, attach to `upper` anchor. |
| `VISUAL_STYLE_MAPPER::debris` | Environmental clutter after battles | Low saturation, midground placement, optional physics tweens. |

Expand this table as the art team contributes additional presets; prompt packs should stay in sync with the ENSURE `style` values stored in prop sidecars.
