# Asset Registry Hooks & Gallery Debugging

These notes explain how modders, tooling authors, and pipeline engineers can tap
into the refreshed asset pipeline delivered with the Asset Gallery + Sidecar
Enforcer work order.

## Registry Event Bus

`comfyvn.studio.core.asset_registry.AssetRegistry` now emits structured events
whenever assets are created, updated, or removed. Register callbacks with
`add_hook(event, callback)` and clean up with `remove_hook` when you are done.
The same envelopes are mirrored to the Modder Hook Bus (`/api/modder/hooks`,
WebSocket topic `modder.on_asset_*`) so external tooling can subscribe without
running inside the Studio process. Each modder payload includes the originating
`hook_event`, a UTC timestamp, and, for updates/removals, the resolved sidecar
path to aid provenance audits. An alias `on_asset_saved` accompanies
`on_asset_registered` for legacy tooling.

Supported events:

- `asset_registered` — fires after `register_file` completes. Payload contains
  `uid`, `type`, `path`, `meta`, and the resolved `sidecar` path.
- `asset_meta_updated` — emitted whenever metadata or sidecar contents change,
  including bulk tag edits and rebuild/enforcer fixes. Payload includes `uid`,
  `type`, `meta`, `path`, and the updated `sidecar`.
- `asset_removed` — dispatched after a registry row (and optional files) are
  removed. Payload includes `uid`, `type`, original `path`, and the sidecar file
  that was deleted.
- `asset_sidecar_written` — triggered every time a sidecar is written. Payloads
  contain `uid`, `type`, the on-disk `sidecar` path, and `rel_path` relative to the
  assets root.

Example hook usage:

```python
from comfyvn.studio.core.asset_registry import AssetRegistry

registry = AssetRegistry(project_id="modding")

def log_sidecars(payload):
    print(f"[asset] sidecar updated for {payload['uid']}: {payload['sidecar']}")

registry.add_hook(AssetRegistry.HOOK_SIDECAR_WRITTEN, log_sidecars)

# ... run your automation ...

registry.remove_hook(AssetRegistry.HOOK_SIDECAR_WRITTEN, log_sidecars)
```

All callbacks execute synchronously; wrap heavy work in your own thread or
queue if you plan to perform long-running tasks.

Call `iter_hooks()` to inspect current listeners when debugging.

## REST & Debug Surfaces

- `GET /assets/debug/hooks` → lists in-process registry listeners so CI bots can
  assert their callbacks are attached.
- `GET /assets/debug/modder-hooks` → filters the Modder Hook Bus to the asset
  envelopes and returns documented payload fields (including `hook_event` and
  timestamps).
- `GET /assets/debug/history?limit=25` → returns the most recent asset hook
  envelopes mirrored through the Modder Hook Bus, already filtered to the
  `on_asset_*` topics.
- `GET /assets/{uid}/sidecar` → returns the parsed sidecar JSON payload for a
  single asset, making provenance diffs and automation dry-runs easier.

Quick curl samples:

```bash
curl -s http://127.0.0.1:8000/assets/debug/hooks | jq '.hooks | keys'
curl -s http://127.0.0.1:8000/assets/debug/modder-hooks | jq '.hooks | map(.name)'
curl -s http://127.0.0.1:8000/assets/debug/history?limit=5 | jq '.items'
curl -s http://127.0.0.1:8000/assets/'${UID}'/sidecar | jq '.sidecar.meta'
```

Both endpoints are read-only and require the same auth scopes as the existing
`/assets/*` API.

### Modder hook bridge

- REST discovery: `GET /api/modder/hooks` lists
  `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, and
  `on_asset_sidecar_written` with payload descriptors. Poll
  `/api/modder/hooks/history` to snapshot the last N events when debugging automation;
  entries now include `type`, `sidecar`, `meta`, `hook_event`, and `timestamp`.
- WebSocket subscription:

  ```bash
  websocat ws://127.0.0.1:8000/api/modder/hooks/ws <<< '{"topics":["on_asset_meta_updated","on_asset_removed"]}'
  ```

  Messages stream as JSON envelopes (`{"event": "...", "ts": 1734810231.1, "data": {...}}`).
- Webhooks: register `POST /api/modder/hooks/webhooks` with `{"event": "on_asset_meta_updated", "url": "https://example/payloads", "secret": "optional"}` to receive signed HMAC callbacks.
- Logging: set `COMFYVN_LOG_LEVEL=DEBUG` and tail `logs/server.log` (logger
  `comfyvn.studio.core.asset_registry`) to mirror the same payloads received via REST/WS.

## Asset Gallery Panel

The new `AssetGalleryPanel` (Panels → **Asset Gallery**) surfaces registry data
directly inside Studio:

- Filter assets by **type**, **tag**, or **license** and multi-select entries.
- Apply bulk tag additions/removals and license overrides without touching the
  database manually.
- Copy a clipboard-ready JSON blob for selected assets via **Copy Debug JSON**
  (uses UTF-8 and preserves nested metadata).
- Live-refresh behaviour is driven by the hook bus above; external scripts that
  mutate assets instantly appear in the panel.

Drop the panel out of the way or detach it while testing automation—we built it
specifically so modders can sanity-check metadata and sidecars mid-workflow.

## Sidecar Enforcement CLI

`tools/assets_enforcer.py` packages the enforcement logic into a standalone
tool. Typical usage:

```
python tools/assets_enforcer.py --dry-run --json > sidecar_report.json
python tools/assets_enforcer.py --fill-metadata --overwrite
```

- `--dry-run` reports issues without touching disk.
- `--fill-metadata` seeds missing tags/licences from folder structure and
  filenames.
- `--overwrite` rewrites sidecars even when files already exist (handy after
  editing metadata by hand).
- `--json` emits the full report for CI dashboards.

The CLI and the rebuilt `comfyvn.registry.rebuild` entry point both use the same
`audit_sidecars()` helper, so behaviour is consistent across workflows.

## Debug Tips

- Enable verbose logging with `COMFYVN_LOG_LEVEL=DEBUG` to see which files the
  gallery and enforcer touch.
- `AssetRegistry.resolve_thumbnail_path(uid)` returns the cached thumbnail file
  if you need to inspect/replace previews from scripts.
- Use `AssetRegistry.bulk_update_tags` for programmatic migrations; it reuses
  the same hook-driven sidecar updates as the gallery UI.

Reach out in the Assets chat if you need additional events or payload fields.
