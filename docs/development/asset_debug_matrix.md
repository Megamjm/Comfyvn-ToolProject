# Asset Debug Matrix & Modder Hook Recipes

Updated: 2025-11-10  
Owner: Project Integration — drop follow-ups in `CHAT_WORK_ORDERS.md`

This note consolidates the asset registry hooks, REST filters, and debugging flows
that modders and automation contributors rely on when wiring custom pipelines into
ComfyVN. Pair it with `docs/dev_notes_modder_hooks.md` for the broader bridge/import
surface.

---

## 1. `/assets` Filter Cheat Sheet

`GET /assets` returns `{ok, items[], total}`. Filters are cumulative and
case-insensitive.

| Parameter | Accepts | Behaviour | Notes |
|-----------|---------|-----------|-------|
| `type`    | string  | Restrict results to a registry bucket (`portrait`, `bgm`, `poses`, …). | Matches `AssetRegistry` `type` column exactly. |
| `hash`    | string  | Exact (case-insensitive) match on the stored hash. | Useful when reconciling local files against the registry. |
| `tags`    | multivalued or comma-separated string | Require every supplied tag to be present in `meta.tags`. | Combine `tags=` and `tag=` freely; duplicates are ignored. |
| `tag`     | multivalued or comma-separated string | Alias for `tags`. | Handy for ergonomic `curl` invocations. |
| `q`       | string  | Case-insensitive substring across the stored path and any string/list metadata values. | Ideal for quick provenance searches (`q=summer` will match descriptions, artists, etc.). |
| `limit`   | int (1–1000) | Maximum number of items to return; defaults to 200. | `total` still reflects the filtered count before truncation. |

Examples:

```bash
curl -s 'http://127.0.0.1:8000/assets?type=portrait&tags=hero&tags=modpack&q=summer' | jq '.items | length'
curl -s 'http://127.0.0.1:8000/assets?hash=7f8c7e9f4d1a2b3c' | jq '.items[0].meta'
curl -s 'http://127.0.0.1:8000/assets?tag=bgm,loop&limit=25' | jq '.total'
```

## 2. Debug Surfaces & Sidecars

- `GET /assets/{uid}` → canonical registry payload (path, hash, bytes, meta, preview links).
- `GET /assets/{uid}/sidecar` → parsed sidecar JSON; combine with git diffs for deterministic tests.
- `GET /assets/debug/hooks` → registry hook registrations, modder hook specs, and recent event history.
- `POST /assets/register` / `POST /assets/upload` → register loose files or upload new ones.

Enable verbose logs with `COMFYVN_LOG_LEVEL=DEBUG` to trace thumbnail generation and
sidecar writes (`comfyvn.studio.core.asset_registry`). When scripting, call
`AssetRegistry.wait_for_thumbnails()` to block until background preview jobs settle.

## 3. Modder Hook Topics (Asset Lifecycle)

The asset registry mirrors every lifecycle event into the Modder Hook bus. Topics:

- `on_asset_registered` — emitted after `AssetRegistry.register_file()` writes the sidecar.
- `on_asset_saved` — alias for `on_asset_registered` (legacy integrations).
- `on_asset_meta_updated` — fires whenever metadata (and the sidecar) is refreshed.
- `on_asset_sidecar_written` — dispatched for every sidecar write, including rebuilds and CLI refreshes.
- `on_asset_removed` — emitted after the registry row is deleted (files may already be trashed when `delete_files=true`).

Each payload includes:

```jsonc
{
  "uid": "f1aa22bb33cc4455",
  "type": "portrait",
  "path": "characters/alice/portrait/latest.png",
  "meta": {"tags": ["hero", "vn"], "notes": "batch-07"},
  "sidecar": "characters/alice/portrait/latest.png.asset.json",
  "hook_event": "asset_registered",
  "timestamp": 1731206400.123
}
```

Additional fields appear where applicable (`bytes`, `rel_path`, `sidecar` absolute
paths for sidecar events).

### 3.1 Webhook & WebSocket Quickstart

Register a webhook that only fires on metadata updates:

```bash
curl -s -X POST http://127.0.0.1:8000/api/modder/hooks/webhooks \
  -H 'Content-Type: application/json' \
  -d '{"event": "on_asset_meta_updated", "url": "https://example.test/hooks/assets", "secret": "dev-token"}'
```

WebSocket subscription (topics optional):

```bash
websocat ws://127.0.0.1:8000/api/modder/hooks/ws \
  -H='User-Agent: comfyvn-dev-tools' \
  -1 --json='{"topics": ["on_asset_registered", "on_asset_removed"]}'
```

Messages arrive as `{event, ts, data}`. Keep-alive `{ "ping": true }` frames are
sent every ~20 s when idle.

Use `/api/modder/hooks/test` to emit synthetic events for smoke testing:

```bash
curl -s -X POST http://127.0.0.1:8000/api/modder/hooks/test \
  -H 'Content-Type: application/json' \
  -d '{"event": "on_asset_sidecar_written", "payload": {"uid": "demo", "sidecar": "demo.asset.json"}}'
```

## 4. Troubleshooting Checklist

- **Missing events** → ensure `COMFYVN_DEV_MODE=1` when loading local hook plugins, and
  verify `/assets/debug/hooks` lists the listener/webhook.
- **Filters returning no data** → confirm tags are stored in `meta.tags` (list); the
  filter requires *all* provided tags. Use `/assets?hash=<sha>` to sanity check the
  registry entry first.
- **Thumbnail/preview paths missing** → install Pillow (`pip install pillow`) and rerun
  the registration. When thumbnails are optional, sidecar payloads still describe the
  canonical asset so automation can proceed.
- **Race conditions** → wrap bulk imports with `AssetRegistry.wait_for_thumbnails()` or
  watch `modder.on_asset_sidecar_written` before triggering downstream work.

---

For extended context across bridge/import tooling, continue with
`docs/dev_notes_modder_hooks.md` and the README’s Developer & Modding Hooks section.
