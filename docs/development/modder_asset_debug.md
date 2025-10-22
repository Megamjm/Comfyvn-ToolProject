# Modder Asset Debug & Hook Notes

Updated: 2025-11-11 • Owner: Assets Chat (Project Integration)

This note captures the asset-specific envelopes exposed by the Modder Hook Bus
and the places modders should watch when validating provenance, sidecar rebuilds,
or automation flows. Pair it with `docs/dev_notes_asset_registry_hooks.md` for
in-process callbacks.

## Quick checklist
- [x] Feature flags: none required — asset hooks are always on.
- [x] REST discovery: `GET /api/modder/hooks` lists `on_asset_saved`,
  `on_asset_registered`, `on_asset_meta_updated`, `on_asset_removed`, and
  `on_asset_sidecar_written`.
- [x] Asset debug APIs: `GET /assets/debug/{hooks,modder-hooks,history}` mirror
  registry listeners, documented payloads, and recent envelopes for CLI
  validation.
- [x] WebSocket subscription: `ws://127.0.0.1:8000/api/modder/hooks/ws`.
- [x] Logs: `logs/server.log` (`comfyvn.studio.core.asset_registry` at DEBUG).
- [x] Sidecars: live under `data/assets/**/<file>.asset.json`.

## API surfaces

### REST
- `GET /api/modder/hooks` → enumerate hook specs and current webhook registrations.
- `GET /api/modder/hooks/history?limit=50` → pull the latest envelopes (`{event, ts, data}`).
- `POST /api/modder/hooks/webhooks` with
  ```json
  {"event": "on_asset_saved", "url": "https://example/hooks", "secret": "opt"}
  ```
  to receive signed callbacks. HMAC SHA-256 signatures arrive via
  `X-Comfy-Signature`.
- `POST /api/modder/hooks/test` → emit a synthetic payload for smoke tests. Pass
  `{"event": "on_asset_removed"}` to mirror deletion flows.

### WebSocket
Connect with an optional topic filter:

```bash
websocat ws://127.0.0.1:8000/api/modder/hooks/ws <<< '{"topics":["on_asset_meta_updated","on_asset_removed"]}'
```

Responses stream as JSON envelopes:

```json
{"event":"on_asset_meta_updated","ts":1736641234.512,"data":{"uid":"…","path":"characters/hero/portrait.png","meta":{"tags":["hero","debug"]},"sidecar":"characters/hero/portrait.png.asset.json","timestamp":1736641234.512,"hook_event":"asset_meta_updated"}}
```

Keep-alive frames arrive as `{"ping": true}` every 20 s when no hooks fire.

## Payload cheat sheet

| Event                     | When it fires                                      | Payload highlights                                        |
|---------------------------|----------------------------------------------------|-----------------------------------------------------------|
| `on_asset_saved`          | Legacy alias emitted alongside `on_asset_registered` | `{uid,type,path,meta,sidecar,bytes,timestamp}`            |
| `on_asset_registered`     | New asset registered + sidecar written             | `{uid,type,path,meta,sidecar,bytes,timestamp}`            |
| `on_asset_meta_updated`   | Metadata refreshed (`update_meta`, bulk tags, CLI) | `{uid,path,meta,sidecar,timestamp}`                       |
| `on_asset_removed`        | Registry entry removed (+ optional file cleanup)   | `{uid,path,sidecar,meta?,bytes?,timestamp}`               |
| `on_asset_sidecar_written`| Any sidecar JSON write (includes rebuilds)         | `{uid,rel_path,sidecar,timestamp}`                        |

All payloads include a floating-point UTC `timestamp`. Paths are relative to the
assets root when available; deletions fall back to absolute paths for audit logs.

## Debugging tips
- Enable `COMFYVN_LOG_LEVEL=DEBUG` to mirror hook payloads in
  `logs/server.log` under the `comfyvn.studio.core.asset_registry` logger.
- Sidecar diffs: compare successive `on_asset_sidecar_written` payloads to decide when
  to re-ingest metadata in external pipelines.
- Provenance replay: fetch the recorded sidecar path and open the JSON on disk
  to inspect provenance, tags, and license information saved alongside the asset.
- CI mode: pair `tests/test_modder_asset_hooks.py` with your automation suite
  to ensure custom scripts still receive the modder envelopes after upgrades.

## Sample cURL

```bash
curl -s http://127.0.0.1:8000/api/modder/hooks | jq '.hooks[] | select(.name | startswith("on_asset"))'

curl -s http://127.0.0.1:8000/api/modder/hooks/history?limit=5 \
  | jq '.items | map(select(.event=="on_asset_meta_updated"))'
```

Use these calls to confirm hooks fire during asset imports, bulk tag edits, or
gallery operations before publishing mod packs.
