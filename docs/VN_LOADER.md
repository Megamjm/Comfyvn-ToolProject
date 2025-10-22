# VN Loader Core

Date: 2025-10-21  
Owner: VN Systems (P9)

## Overview
- Consolidates Story Tavern transcripts, legacy VN packs, and inline JSON dumps into a canonical scenario bundle for Mini-VN playback and the Ren'Py exporter.
- Builds a repeatable project layout under `data/projects/<projectId>` with per-scene/persona JSON plus manifest/debug sidecars.
- Exposes HTTP endpoints for modders (`/api/vn/projects`, `/api/vn/build`, `/api/vn/scenes`) and keeps hooks discussed in `dev_notes_modder_hooks.md`.
- Ships with `comfyvn.vn.schema` (Pydantic models) and `comfyvn.vn.loader.build_project`, which Tooling/CLI modules may call directly.

## Project Layout
```
data/projects/<projectId>/
  manifest.json          # Summary for UIs and exporters
  debug.json             # Trace of inputs, warnings, options
  scenes/<sceneId>.json  # Canonical Scene payloads
  personas/<personaId>.json
  assets/manifest.json   # Optional asset bindings (portrait, bgm, etc.)
```

Manifest fields:
- `projectId`, `sceneCount`, `personaCount`, `assetCount`
- `scenes[]` with `id`, `title`, `order`
- `personas[]` with `id`, `displayName`
- `hooks` exposing API + event names (`on_scene_enter`, `on_choice_selected`, `on_asset_loaded`)

## Pipeline Stages
1. **Source ingest**: `_load_source_payload` accepts `kind` of `inline`, `scenario`, `file`, or `directory` (JSON glob). Sources may ship `data`/`payload` or `path`.
2. **Scenario normalisation**: `ScenarioDocument` wraps personas, scenes, assets, metadata, and attaches source provenance.
3. **ID allocation**: `IdAllocator` slugifies and deduplicates personas (`persona_*`), scenes (`scene_*`), nodes, choices, anchors, and assets.
4. **Node/choice fixes**: Fills missing `choice.to` with the next node (or `END`), seeds `Presentation()` placeholders, merges duplicate persona tags/portraits.
5. **Disk emit**: Writes per-item JSON plus `manifest.json` and `debug.json` (trace + warnings). Optional assets manifest consolidated when supplied.

## Source Descriptor Cheatsheet
| Field | Notes |
| --- | --- |
| `kind` | Defaults to `inline`. `file` and `directory` resolve relative to `workspace` or repo root. |
| `id` | Optional label in build trace (`debug.json`). |
| `path` | Relative/absolute path for `file`/`directory` kinds. |
| `data`/`payload` | Inline scenario body. Can be a Scene dict, array of Scenes, or a ScenarioDocument. |
| `options` | Per-source hints (currently stored in trace; future use for importer mapping). |

Example inline build:
```bash
curl -X POST http://localhost:8001/api/vn/build \
  -H "Content-Type: application/json" \
  -d '{
        "projectId": "p9_demo",
        "sources": [{
          "kind": "inline",
          "data": {
            "personas": [{"id": "alice", "displayName": "Alice"}],
            "scenes": [{
              "title": "Meet Cute",
              "nodes": [
                {"speaker": "alice", "text": "Hey there!"},
                {"text": "The scene fades out."}
              ]
            }]
          }
        }]
      }'
```

## API Surface
- `GET /api/vn/projects` → `{ items: [manifest...] }`
- `POST /api/vn/build` → `{ project, scenes[], personas[], assets[], debug }`
- `GET /api/vn/scenes?projectId=<id>[&sceneId=<id>][&includeManifest=true]`

Debug hooks:
- `debug.json.trace[]` records each source (`kind`, `origin`, persona/scene ids, warnings).
- Exporters watch `manifest.hooks.events` to attach websocket topics (`on_scene_enter`, `on_asset_saved`).

## Development Notes
- Loader logs warnings for implicit fixes (missing `choice.to`, duplicate persona ids) and mirrors them into `debug.json`.
- `BuildError` yields HTTP `400` for bad inputs; unexpected issues bubble as `500` with log traces.
- Workspace guard: `/api/vn/build` rejects non-existent `workspace` paths and defaults to repo root.
- Future work: support ST importer glue (`kind: "st_transcript"`), asset binding heuristics, and watcher for persona portrait manifests.

## Changelog
- **2025-10-21**: Initial VN loader core shipped (`comfyvn.vn.schema`, `comfyvn.vn.loader`, FastAPI routes, docs).

## Debug & Verification (phase P9)
- [ ] **Docs updated**: README, architecture, CHANGELOG, /docs notes (what changed + why)
- [ ] **Feature flags**: added/persisted in `config/comfyvn.json`; OFF by default for external services
- [ ] **API surfaces**: list endpoints added/modified; include sample curl and expected JSON
- [ ] **Modder hooks**: events/WS topics emitted (e.g., `on_scene_enter`, `on_asset_saved`)
- [ ] **Logs**: structured log lines + error surfaces (path to `.log`)
- [ ] **Provenance**: sidecars updated (tool/version/seed/workflow/pov)
- [ ] **Determinism**: same seed + same vars + same pov ⇒ same next node
- [ ] **Windows/Linux**: sanity run on both (or mock mode on CI)
- [ ] **Security**: secrets only from `config/comfyvn.secrets.json` (git-ignored)
- [ ] **Dry-run mode**: for any paid/public API call
