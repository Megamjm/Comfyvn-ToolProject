# Export Publish Pipeline — Steam & itch

Updated: 2025-11-15 • Scope: deterministic distribution packages for Steam/itch

This note documents the end-to-end workflow for the new publish pipeline that
wraps Ren'Py exports into reproducible Steam/itch bundles, lists the feature
flags required to enable it, and provides curl samples for both dry-run previews
and real packaging.

---

## 1. Feature flags & prerequisites

- `enable_export_publish` (`config/comfyvn.json → features`) — gates the
  `/api/export/publish` route. Defaults to `false`.
- `enable_export_publish_steam` / `enable_export_publish_itch` — enable each
  platform-specific packager (`comfyvn/exporters/steam_packager.py`,
  `comfyvn/exporters/itch_packager.py`). Leaving a target disabled causes the
  route to reject requests for that platform with `403`.
- The Ren'Py export orchestrator must be usable for the requested project; the
  route internally invokes the same logic as `scripts/export_renpy.py`.
- Optional overrides (icon, EULA, license text) are read from disk if the path
  exists; otherwise placeholders are embedded so QA can validate packaging flows
  without waiting for legal content.

Logs are appended to `logs/export/publish.log` in JSONL form:

```jsonc
{"event":"steam_publish_created","slug":"demo-build","checksum":"…","archive_path":"exports/publish/steam/demo-build.steam.zip"}
{"event":"itch_publish_dry_run","slug":"demo-build","platforms":["windows"],"archive_path":"exports/publish/itch/demo-build.itch.zip"}
```

Use `tail -f logs/export/publish.log` during CI to watch packaging progress.

---

## 2. Dry-run preview

Dry runs rebuild the Ren'Py project (without touching the existing output
directory) and return diff summaries for each requested target. No archives or
manifests are written. Modder hook `on_export_publish_preview` fires with the
payload shown in Section 4.

```bash
curl -s -X POST http://127.0.0.1:8001/api/export/publish \
  -H 'Content-Type: application/json' \
  -d '{
        "project": "demo",
        "label": "Demo Build",
        "version": "0.1.0",
        "targets": ["steam","itch"],
        "platforms": ["windows","linux"],
        "dry_run": true
      }' | jq '{packages, export}'
```

Extract of the response:

```jsonc
{
  "packages": {
    "steam": {
      "archive_path": "exports/publish/steam/demo-build.steam.zip",
      "diffs": [
        {"path": "exports/publish/steam/demo-build.steam.zip", "status": "new"},
        {"path": "exports/publish/steam/demo-build.steam.manifest.json", "status": "new"}
      ]
    },
    "itch": {
      "archive_path": "exports/publish/itch/demo-build.itch.zip",
      "diffs": [
        {"path": "exports/publish/itch/demo-build.itch.zip", "status": "new"}
      ]
    }
  }
}
```

---

## 3. Full packaging run

When `dry_run` is omitted (or `false`) the route writes platform archives,
manifests, license summaries, and provenance sidecars under the configured
`publish_root` (default `exports/publish/{steam,itch}`).

```bash
curl -s -X POST http://127.0.0.1:8001/api/export/publish \
  -H 'Content-Type: application/json' \
  -d '{
        "project": "demo",
        "label": "Demo Build",
        "version": "0.1.0",
        "targets": ["steam","itch"],
        "platforms": ["windows","linux"],
        "icon": "assets/icons/steam_app.png",
        "eula": "docs/samples/EULA_demo.txt",
        "provenance_inputs": {"requested_by": "CI", "ticket": "OPS-123"}
      }' | jq '.packages.steam.manifest | {label,platforms,license_manifest}'
```

Key artefacts written per target:

- `<slug>.{steam,itch}.zip` — deterministic archive with
  `publish_manifest.json`, per-platform `builds/<platform>/game/`, legal folder,
  provenance data, and (optionally) `debug/modder_hooks.json`.
- `<slug>.{steam,itch}.manifest.json` — structured metadata referencing the Ren'Py
  export (`script_path`, `manifest_path`), requested platforms, license counts,
  and any metadata/provenance overrides supplied in the request.
- `<slug>.{steam,itch}.licenses.json` — flattened view of asset licenses derived
  from the Ren'Py manifest (`extras.license` fields fall back to
  `unspecified`). Provide `license_path` to drop a bespoke legal text into the
  archive.
- Provenance sidecars are generated for both archive and manifest (`*.prov.json`)
  capturing checksum, tool version (`COMFYVN_VERSION`), and the inputs recorded
  in the request.

Modder hook `on_export_publish_complete` fires once per target with checksum,
paths, and sidecar locations so automation can announce builds or trigger
downstream uploads (e.g., SteamPipe or itch.io Butler).

---

## 4. Hook payloads

- `on_export_publish_preview` — emitted for dry-run requests. Fields:
  `{project_id, timeline_id, targets[], label, version, platforms{target:[]}, diffs{target:[...]}}`.
- `on_export_publish_complete` — emitted after each archive is written on a full
  run. Fields:
  `{project_id, timeline_id, target, label, version, checksum, archive_path, manifest_path, platforms[], provenance{archive,manifest}}`.

Subscribe over the existing modder hook WebSocket (`/api/modder/hooks/ws`) or
poll `/api/modder/hooks/history` to surface packaging events in dashboards.

---

## 5. Source modules

- `comfyvn/exporters/publish_common.py` — deterministic ZIP builder, slug/feature
  helpers, license manifest extraction, log appender.
- `comfyvn/exporters/steam_packager.py` — Steam-specific packaging (icons,
  `publish_manifest.json`, provenance, debug hook snapshots).
- `comfyvn/exporters/itch_packager.py` — itch bundle packaging (`channels.json`,
  Butler script stub, provenance).
- `comfyvn/server/routes/export.py` — `POST /api/export/publish` route wiring
  Ren'Py exports, feature checks, modder hook emission, and response shaping.

See `tests/test_publish_packagers.py` for reproducibility assertions and dry-run
behaviour covering both packagers.
