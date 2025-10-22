# Theme & World Changer — Developer Notes

Updated: 2025-11-05

This note collects implementation details, REST contracts, and debugging hooks for the Theme & World Changer service so Studio teams, modders, and automation scripts can integrate without spelunking the source tree.

## Overview
- Templates live in `comfyvn/themes/templates.py` and define LUT stacks, ambience assets, music packs, prompt styles, and character role defaults for the core presets (Modern, Fantasy, Romantic, Dark, Action).
- `comfyvn/server/routes/themes.py` exposes `/api/themes/templates` and `/api/themes/apply` so front-ends can enumerate templates, preview deltas, and stage overrides without touching render pipelines.
- Plan responses are deterministic: if the same `{theme, scene, overrides}` payload is submitted, the resulting checksum and `mutations` payload are byte-identical. The GUI relies on this to diff previews without forcing fresh renders.

## REST contracts

### List templates
```
GET /api/themes/templates
→ 200 OK
{
  "ok": true,
  "data": {
    "templates": ["Action", "Dark", "Fantasy", "Modern", "Romantic"],
    "count": 5
  }
}
```

### Apply template
```
POST /api/themes/apply
Content-Type: application/json
{
  "theme": "Fantasy",
  "scene": {
    "scene_id": "scene-001",
    "world": {"id": "world-42"},
    "theme": {
      "assets": {"backdrop": "city/old"},
      "luts": ["neutral"],
      "music": {"set": "silence"}
    },
    "characters": [
      {"id": "alex", "roles": ["protagonist"], "theme": {"palette": "cool"}},
      {"id": "blair", "roles": ["antagonist"], "theme": {"palette": "cool"}}
    ]
  },
  "overrides": {
    "characters": {
      "blair": {"accent": "violet"}
    }
  }
}
```

Success response:
```
{
  "ok": true,
  "data": {
    "plan_delta": {
      "theme": "Fantasy",
      "scene_id": "scene-001",
      "world_id": "world-42",
      "mutations": {
        "assets": {"before": {...}, "after": {...}, "changed": true},
        "luts": {"before": [...], "after": [...], "changed": true},
        "music": {"before": {...}, "after": {...}, "changed": true},
        "prompt": {"before": {...}, "after": {...}, "changed": true},
        "characters": [
          {
            "id": "alex",
            "before": {"palette": "cool"},
            "after": {"palette": "warm", "rim_light": "amber"},
            "changed": true
          },
          {
            "id": "blair",
            "before": {"palette": "cool"},
            "after": {"palette": "cool", "accent": "violet"},
            "changed": true
          }
        ]
      },
      "checksum": "b5654d4de2a7..."
    },
    "templates": ["Action", "Dark", "Fantasy", "Modern", "Romantic"]
  }
}
```

Errors:
- `404` — unknown theme key (check spelling/aliases).
- `400` — malformed requests or internal planning issues (logged as warnings with stack traces).

## Debug workflow

1. **Capture payloads**: call `/api/themes/apply` with `dry_run` scenario payloads before invoking renders. Save the resulting `plan_delta` to `tmp/plan_debug.json` for regression comparisons.
2. **Verify determinism**: repeat the same request; the `checksum` and entire response should match. If not, inspect the scene payload for non-deterministic ordering (e.g., unsorted lists).
3. **Inspect character merges**: each entry in `mutations.characters` lists `before` and `after` states. Roles compound onto `default` entries; per-character overrides win last. Missing `roles` arrays default to template `default`.
4. **Tracking additions**: adding new keys to template payloads requires keeping dictionary ordering stable—call `_sorted_dict` or copy the existing pattern in `comfyvn/themes/templates.py`.
5. **Logging**: run the server with `COMFYVN_LOG_LEVEL=DEBUG` to log theme application inputs/outputs. FastAPI route logs appear in `logs/server.log` with the hashed checksum for cross-tool debugging.

## Automation & tooling hooks

- Modders can wire CLI tools to post plan payloads, diff the `mutations` block, and then dispatch background render queues via `/api/schedule/enqueue`.
- Asset scripts should honour `mutations.assets.after["ambient_sfx"]` and `mutations.music.after` when staging audio previews.
- Use the checksum as a cache key for generated thumbnails or ambient mixes; if the plan checksum matches a cached entry, skip recomputation.
- Combine `/api/themes/apply` with `/api/presentation/plan` to preview directive deltas: apply the theme first, update the scene state with the returned mutations, then request the presentation plan.

## Related documents
- `docs/CODEX_STUBS/2025-10-21_THEME_WORLD_CHANGER_A_B.md` — work order intent and acceptance hooks.
- `architecture.md` and `architecture_updates.md` — high-level placement, docs index, and release alignment.
- `README.md` (Theme & World Changer section) — feature overview for Studio operators.
