# Theme Swap Wizard

## Intent
The Theme Swap Wizard lets editors restyle a project or branch while preserving
story anchors and audit trail metadata. It pairs curated kits (palettes, LUTs,
SFX/music, overlays, camera defaults, prompt flavors, and tag remaps) with a
wizard flow that:

1. Loads available kits, subtypes, and accessibility variants.
2. Lets authors pick anchors to keep in place (props, events, timeline markers).
3. Builds a deterministic preview delta (`checksum`) without mutating the save.
4. Commits the swap into a new **VN Branch** worldline so OFFICIAL stays pristine.

`enable_themes` must be set to **true** in `config/comfyvn.json` before the routes go
live. The default shipped configuration leaves it off so studios can phase rollout.

## API Surface
All routes live under `/api/themes` and are gated by the `enable_themes` flag.

### `GET /api/themes/templates`
Returns the catalog of theme kits, subtypes, accessibility variants, and tag remaps.
Use it to hydrate pickers and annotate UI with summaries.

```json
{
  "ok": true,
  "data": {
    "templates": ["ModernSchool", "UrbanNoir", "Gothic", "Cosmic", ...],
    "catalog": [
      {
        "name": "ModernSchool",
        "label": "Modern School",
        "summary": "Bright classrooms and festival nights for slice-of-life arcs.",
        "style_tags": ["slice_of_life", "campus", "youth"],
        "tag_remaps": {
          "environment.classroom": "environment.school.classroom_day",
          "props.poster": "props.school.poster_set"
        },
        "subtypes": [
          {"name": "day", "label": "Homeroom Day", "default": true},
          {"name": "festival", "label": "School Festival", "default": false}
        ],
        "variants": [
          {"name": "base", "label": "Studio Default"},
          {"name": "high_contrast", "label": "High Contrast"},
          {"name": "color_blind", "label": "Color Blind Safe"}
        ]
      }
    ],
    "count": 14
  }
}
```

### `POST /api/themes/preview`
Builds a deterministic plan without touching the project. The wizard calls this when
the user tweaks theme/subtype/variant/anchor selections.

**Request body**
```json
{
  "theme": "UrbanNoir",
  "subtype": "speakeasy",
  "variant": "high_contrast",
  "anchors": ["hero_pose", "prop_balcony"],
  "scene": {
    "scene_id": "chapter1.intro",
    "world_id": "official",
    "characters": [
      {"id": "alice", "roles": ["protagonist"], "theme": {"accent": "sky_blue"}}
    ]
  },
  "overrides": {
    "characters": {
      "alice": {"accent": "steel_blue"}
    }
  }
}
```

**Response body (truncated)**
```json
{
  "ok": true,
  "data": {
    "plan_delta": {
      "theme": "UrbanNoir",
      "theme_label": "Urban Noir",
      "scene_id": "chapter1.intro",
      "world_id": "official",
      "checksum": "f3ba19c8...",
      "mutations": {
        "assets": {"before": {...}, "after": {...}, "changed": true},
        "palette": {"before": {}, "after": {"accent": "#FF3366"}, "changed": true},
        "props": {"before": {}, "after": {...}, "changed": true},
        "style_tags": {"before": [], "after": ["noir","urban","crime","speakeasy","night"], "changed": true},
        "characters": [
          {
            "id": "alice",
            "before": {"accent": "sky_blue"},
            "after": {"accent": "steel_blue"},
            "changed": true
          }
        ]
      },
      "anchors": {
        "available": ["hero_pose", "prop_balcony"],
        "preserved": ["hero_pose", "prop_balcony"],
        "released": [],
        "details": []
      },
      "metadata": {
        "subtype": "speakeasy",
        "variant": "high_contrast",
        "anchors_preserved": ["hero_pose", "prop_balcony"],
        "prompt_flavor": "late-night speakeasy tension",
        "available_subtypes": [...],
        "available_variants": [...]
      },
      "preview": {
        "palette": {"primary": "#1B1F29", "accent": "#FF3366"},
        "luts": ["cool", "noir_high_contrast", "grain_emphasis"],
        "camera": {"lens": "50mm", "movement": "crane_rise"},
        "assets": {...},
        "music": {"set": "jazz", "mood": "brooding"}
      }
    },
    "templates": [... detailed catalog ...]
  }
}
```

### `POST /api/themes/apply`
Same payload as preview plus an optional `branch_label`. The server merges the plan,
forks (or updates) a VN Branch worldline, and leaves OFFICIAL untouched.

```json
{
  "theme": "Cosmic",
  "subtype": "eldritch",
  "variant": "color_blind",
  "anchors": ["experiment_control"],
  "scene": {"scene_id": "lab.a2", "world_id": "official"},
  "branch_label": "Nebula Drift"
}
```

**Response highlights**
```json
{
  "branch": {
    "id": "official--cosmic-eldritch-color_blind",
    "label": "Nebula Drift",
    "lane": "vn_branch",
    "metadata": {
      "theme_swap": {
        "theme": "Cosmic",
        "subtype": "eldritch",
        "variant": "color_blind",
        "anchors_preserved": ["experiment_control"],
        "mutations_changed": ["assets","palette","props","style_tags"],
        "checksum": "d8d0036d..."
      },
      "provenance": [
        {
          "event": "theme_swap",
          "theme": "Cosmic",
          "subtype": "eldritch",
          "variant": "color_blind",
          "checksum": "d8d0036d...",
          "timestamp": "2025-03-10T02:43:51Z"
        }
      ]
    }
  },
  "branch_created": true,
  "plan_delta": {...},
  "templates": [...]
}
```

If you re-run the wizard against an existing theme branch, the route updates its
metadata, refreshes provenance (deduped by checksum), and leaves OFFICIAL untouched.

## Hooks
`comfyvn/core/modder_hooks.py` auto-registers two modder-facing events when the router
loads. Both hooks respect the feature flag and only fire when the caller has access.

| Event             | When it fires                                           | Payload highlights                                                                 |
|-------------------|--------------------------------------------------------|-------------------------------------------------------------------------------------|
| `on_theme_preview`| After `POST /api/themes/preview` returns                | `theme`, `theme_label`, `subtype`, `variant`, `anchors_preserved`, `plan`, `scene`, `timestamp` |
| `on_theme_apply`  | After `POST /api/themes/apply` commits a VN Branch plan | All preview fields plus `branch`, `branch_created`, `checksum`, `timestamp`         |

Subscribe over REST polling, WebSocket (`modder.on_theme_*` topics), or in-process
plugins. See `docs/dev_notes_modder_hooks.md` for integration scaffolding.

## Anchor Preservation
The wizard never mutates the anchor payload supplied by the caller; it simply echoes
back which anchors were preserved and which would be released. Pair it with
`/api/props/anchors` when you need authoritative coordinates, or cross-link with the
Timeline Overlay when `enable_worldlines` is active.

## Debug & QA Tips
1. Run `python tools/check_current_system.py --profile p1_theme_swap --base http://127.0.0.1:8001`
   before handing off to QA. The profile checks the feature flag, routes, and docs.
2. Keep `COMFYVN_LOG_LEVEL=DEBUG` when iterating—the router logs the branch id,
   chosen subtype/variant, and preserved anchors.
3. Worldline IDs follow `sourceWorld--theme-subtype[-variant]`. Slugs are sanitized by
   `_slugify`, so expect lowercase and hyphenated tokens.
4. Attach the plan checksum to automation pipelines (render queues, advisory scans)
   so repeated previews are deduped.

## Related Material
- `docs/THEME_KITS.md` — flavor notes, palettes, LUTs, and subtype overviews.
- `docs/STYLE_TAGS_REGISTRY.md` — canonical tag descriptions for UI filters.
- `docs/VISUAL_STYLE_MAPPER.md` — how theme tags interact with props & battle payloads.
