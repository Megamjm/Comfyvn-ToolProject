## VN Pack Importer (Dry-Run & Extract)

The VN pack importer accepts packaged archives (`.zip`, `.cvnpack`, `.rpa`) and exposes two FastAPI endpoints under `/import/vnpack`.  Archives are handled by pluggable adapters that expose a common interface (`BaseAdapter`) and lean on the existing importer registry to surface engine-specific hints during previews.

### Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/import/vnpack/dryrun` | Streams the uploaded archive to a temp file, runs the matching adapter, and returns the first 50 entries plus importer-detected engine metadata. |
| `POST` | `/import/vnpack/extract` | Persists the upload to a new FileImporter session (`data/imports/vnpack`), safely extracts contents, and returns bundle directories + preview metadata. |

Both endpoints respond with `400` for unsupported extensions.  They rely on `find_adapter` which walks `ADAPTERS` (`ZipAdapter`, `RpaAdapter`, …) and instantiates the first adapter whose `detect(path)` matches.

### Response Preview

Dry-run replies now include:

- `adapter`: name of the adapter handling the archive.
- `files`: the first 50 entries reported by `adapter.list_contents()`.
- `preview`: importer-derived metadata:
  - `engine`: top-ranked engine from the traditional importer registry (`RenpyImporter`, `KiriKiriImporter`, etc.) plus that importer’s `plan()` steps when available.
  - `detections`: confidence-ordered list of detectors that matched during preview.
  - `scenes` / `assets`: truncated lists (<=25) gathered from the extracted file tree.

Extract replies include the same preview and additionally return:

- `bundle.id`: the generated import ID.
- `bundle.raw_path`: persisted upload inside `data/imports/vnpack/raw`.
- `bundle.extracted_path`: staging directory populated by the adapter.
- `bundle.converted_path`: reserved for downstream normalization runs.
- `extracted`: up to 50 relative paths extracted for quick inspection.

### Adapters

| Adapter | Extensions | Capabilities |
| --- | --- | --- |
| `ZipAdapter` | `.zip`, `.cvnpack` | Safe member extraction, file listing, scene/asset discovery, importer-based engine detection. |
| `RpaAdapter` | `.rpa` | Stub implementation that advertises unsupported status until external Ren’Py tooling is bundled. |

Adapters are registered in `comfyvn/importers/vnpack/__init__.py` and can be extended without touching the routes.  Each adapter implements:

- `list_contents()` → `list[dict]` summary of archive members.
- `extract(out_dir)` → iterates over extracted filesystem paths.
- `map_scene_graph(extracted_root)` → returns the importer-aware preview payload.

### Integration Points

- `comfyvn/importers/vnpack/base.py` hooks into `ALL_IMPORTERS` to reuse existing engine detectors and plan summaries.  Dry-run previews now mirror the logic used during full VN imports.
- `comfyvn/server/routes/import_vnpack.py` is auto-loaded via `comfyvn/server/modules/vnpack_import_api.py`, so the endpoints are available once the server starts.
- Persisted bundles live under the standard `FileImporter("vnpack")` hierarchy and can be consumed by the existing VN importer pipeline for normalization and scene generation.

### Future Work

1. Integrate `.rpa` and `.pak` adapters once the runtime ships with sanctioned extraction tooling (e.g., `rpatool`).
2. Feed extracted bundle metadata into the primary VN import workflow to allow one-click promotion from dry-run → normalized scenes.
3. Add route-level tests that exercise dry-run and extract behaviors across supported adapters.
