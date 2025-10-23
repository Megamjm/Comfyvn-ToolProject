# Dev Notes — License Snapshot & Ack Gate

**Scope:** Advisory phase 7 — snapshot model licenses/EULAs at download time, persist
audit payloads next to assets, and require explicit acknowledgements before hub pulls.

## Data Model

- `comfyvn/advisory/license_snapshot.py`
  - `capture_snapshot()` normalises text, writes `<asset_dir>/license_snapshot.json`,
    and records summary state in `config/config.json::advisory_licenses`.
  - `record_ack()` stores per-user acknowledgements in both the snapshot file and
    settings, preserving provenance payloads for later export manifests.
  - `require_ack()` now returns advisory metadata, setting `ack_required`/`warnings`
    when the snapshot hash lacks an acknowledgement so callers can warn instead of
    hard-blocking.
- Settings payload (`config/config.json`):

```json
{
  "advisory_licenses": {
    "hub:civitai:308691:v352812:flux-dev-fp16.safetensors": {
      "asset_id": "hub:civitai:308691:v352812:flux-dev-fp16.safetensors",
      "asset_path": "models/civitai/flux-dev-fp16.safetensors",
      "snapshot_path": "models/civitai/license_snapshot.json",
      "hash": "0f9a9e5b7f7a3d6d...",
      "source_url": "https://civitai.com/api/download/models/352812/license",
      "captured_at": "2025-12-22T04:35:11.124216+00:00",
      "metadata": {
        "provider": "civitai",
        "model_id": 308691,
        "version_id": 352812
      },
      "ack_by_user": {
        "qa.bot": {
          "user": "qa.bot",
          "hash": "0f9a9e5b7f7a3d6d...",
          "acknowledged_at": "2025-12-22T04:36:02.558903+00:00",
          "notes": "QA dry-run approval",
          "source_url": "https://civitai.com/api/download/models/352812/license",
          "provenance": {
            "workflow": "qa.p7.license_check",
            "ticket": "P7-142"
          }
        }
      }
    }
  }
}
```

Hashes changing wipe `ack_by_user` so downstream workflows re-prompt users.

## FastAPI Surface

- `comfyvn/server/routes/advisory_license.py`
  - `POST /api/advisory/license/snapshot` — capture or refresh snapshot. Returns the
    normalized text (for UI display) plus ack state.
  - `POST /api/advisory/license/ack` — persist per-user acknowledgement with optional
    provenance envelope.
  - `POST /api/advisory/license/require` — helper for connectors to warn when an
    acknowledgement is missing (`ack_required: true`), returning advisory context for dashboards.
  - `GET /api/advisory/license/{asset_id}` — dump stored status; `?include_text=true`
    surfaces the normalised EULA for dashboards.
- Routes stay active even when `features.enable_advisory` is disabled so CLI/QA can
  snapshot licences ahead of turning the full advisory stack on.

## Hooking & Automation

- The helper emits `on_asset_meta_updated` whenever snapshots or acknowledgements
  change, packaging:

```json
{
  "meta": {
    "license_snapshot": {"hash": "...", "captured_at": "...", "source_url": "..."},
    "license_ack": {"user": "...", "hash": "...", "acknowledged_at": "..."}
  }
}
```

- Hook specs already exist for `on_asset_meta_updated`, so no additional spec wiring.
- WebSocket topic: `modder.on_asset_meta_updated`.
- REST history: `/api/modder/hooks/history`.

## Debugging Tips

- `curl -X POST /api/advisory/license/snapshot ...` + `ack` + `require` to smoke test.
- Inspect `config/config.json` after calls to confirm per-user data persisted.
- `license_snapshot.status(asset_id, include_text=True)` returns a single payload for
  CLI scripts without hitting HTTP.
- If the API reports "snapshot hash mismatch", ensure the connector replays
  `capture_snapshot()` before acknowledging (hash resets when upstream terms change).

## Follow-Ups / TODO

1. Civitai + Hugging Face connector wiring:
   - Inject `capture_snapshot()` prior to download plan creation.
   - Record acknowledgements with the resolved asset UID (model + version + file).
   - Call `/require` (or helper) before streaming binaries.
2. Export provenance: embed acknowledgement hash + user + timestamp inside
   `license_manifest.json` so release audit trails carry the data forward.
3. Add regression tests around snapshot/ack cycle once connectors are hooked
   (pytest + temporary directories).
4. Consider diffing snapshot text and emitting a webhook when upstream EULAs change.
