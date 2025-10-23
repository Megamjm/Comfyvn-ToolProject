# Ren'Py Export Pipeline

Updated: 2025-11-04

## CLI Usage
- `python scripts/export_renpy.py --project <id>` drives the FastAPI-backed `RenPyOrchestrator`.
- Common flags:
  - `--timeline`, `--world`, `--world-mode` mirror the REST surface.
  - `--no-per-scene` disables per-scene `.rpy` modules.
  - `--pov-mode` / `--no-pov-switch` control POV generation.
  - `--bake-weather` toggles deterministic weather/lighting baking. When omitted the flag inherits the `enable_export_bake` feature flag (default: disabled).
  - `--dry-run` surfaces diffs without touching disk.
- Successful runs print `provenance_bundle`, `provenance_json`, and `provenance_findings` in the CLI summary so automation can archive provenance without unpacking the export directory.

## Outputs
- The export summary (printed to stdout) now includes `weather_bake` and `label_manifest` fields.
- A JSON label manifest is written to `<out>/label_manifest.json` on successful exports. Dry runs embed the manifest inline.
- Manifest schema:
  ```json
  {
    "project": "demo",
    "timeline": "main",
    "generated_at": "2025-11-04T04:32:10.000000Z",
    "weather_bake": true,
    "pov_labels": [
      {
        "scene_id": "scene_intro",
        "label": "intro_scene",
        "pov_ids": ["mc"],
        "pov_names": {"mc": "Main"}
      }
    ],
    "battle_labels": [
      {
        "scene_id": "scene_battle_finale",
        "label": "battle_finale",
        "hash": "9ac42b1d3ef1"
      }
    ]
  }
  ```
- `battle_labels` are derived heuristically (scene id or label containing "battle"). Hashes are SHA1 prefixes for cache invalidation.
- A zipped `provenance_bundle.zip` plus a readable `provenance.json` land next to the export output. The bundle mirrors the server-side `/api/export/bundle` format (manifest, provenance, timeline/scenes, referenced assets, embedded Ren'Py snapshot). The public mirror lives at `POST /export/bundle` for automation outside the `/api` namespace.
- Summary payloads expose `provenance_bundle`, `provenance_json`, `provenance_findings`, and `provenance_error` (when generation fails) alongside a nested `provenance` block that carries the raw enforcement payload.

### Example Summary

```json
{
  "ok": true,
  "project": "demo",
  "timeline": "main",
  "output_dir": "build/renpy_game",
  "label_manifest": "build/renpy_game/label_manifest.json",
  "weather_bake": true,
  "provenance_bundle": "build/renpy_game/provenance_bundle.zip",
  "provenance_json": "build/renpy_game/provenance.json",
  "provenance_findings": [],
  "provenance_error": null,
  "provenance": {
    "bundle": "build/renpy_game/provenance_bundle.zip",
    "json": "build/renpy_game/provenance.json",
    "findings": [],
    "error": null
  }
}
```

## Modder Hooks
- `on_export_started`
  - Payload: `{project, timeline, world, options:{pov_mode,dry_run,bake_weather}, timestamp}`.
- `on_export_completed`
  - Payload: `{project, timeline, ok, output_dir, weather_bake, label_manifest, provenance_bundle, provenance_json, provenance_findings, provenance_error, error?, timestamp}`.
- Hook specs are registered at runtime so REST/WS subscribers receive both events.

## Weather Bake Notes
- The bake flag only impacts the manifest today; downstream tooling (Ren'Py templates, weather planner) treats the flag as the canonical switch.
- `enable_export_bake` can be persisted in `comfyvn.json` (Settings → Debug Flags) so CI inherits the behaviour without changing scripts.

## Troubleshooting
- Missing project/timeline: the CLI returns a 404 payload mirroring the REST API.
- Publish phase failures surface `phase: "publish"` alongside the HTTP status and still emit `on_export_completed` with `ok: false`.
