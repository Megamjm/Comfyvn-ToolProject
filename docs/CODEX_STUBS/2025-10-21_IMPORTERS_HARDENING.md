# Importers Hardening — 2025-10-21

## Overview
- Stabilize the Roleplay importer so large uploads land reliably, jobs queue through the shared worker, and previews normalize scene payloads for Studio.
- Stand up a VN Pack adapter skeleton that cleanly detects archives, defers to optional external extractors, and supports a non-destructive dry run.
- Lay the Manga ingestion scaffolding (panel segmentation → OCR → dialogue grouping → speaker inference) with stubbed workers and predictable artifact layout.

## References
- `docs/import_roleplay.md` — existing endpoints and processor outline.
- `docs/importer_engine_matrix.md` — engine signatures and extraction notes.
- Jobs WebSocket artefacts under `comfyvn/gui/panels/jobs_panel.py` for payload shape and broadcast cadence.

## Roleplay Importer Stabilization
- **Upload validation & streaming**
  - Accept `.txt` or `.json` parts via multipart or raw JSON body; reject others with `415`.
  - Enforce `10 MB` payload cap via streaming parser (limit `Content-Length` and stream into temp file).
  - Normalize UTF-8 with fallback for BOM; surface parsing errors with structured detail.
- **Job orchestration**
  - Immediately enqueue `roleplay_import` job (persist in `jobs` table) and broadcast `queued` status on Jobs WS.
  - Worker streams transcript into `data/imports/roleplay/{job_id}.txt`, runs parser, stores normalized scene JSON in `scene_cache/{job_id}.json`.
  - During processing, emit `progress` events (`uploaded`, `parsed`, `characters_linked`, `completed`) for Studio panel consumption.
- **Preview endpoint**
  - `GET /roleplay/imports/{job_id}/preview` returns normalized scene graph with consistent schema (characters, timeline, assets).
  - When job incomplete, return `202` with latest status + retry hint.
  - Persist preview payload with compression if >256 KB; reuse on repeat hits.
- **Error surfacing**
  - Capture exceptions to `imports/roleplay_<job_id>.log`; expose via `/roleplay/imports/{job_id}/log`.
  - Job errors push `failed` event including `log_url` so Studio links directly.
  - Ensure worker cleans temp files on failure and marks transcripts as quarantined for manual review.
- **Acceptance path**
  1. Upload 10 MB transcript (boundary case) → job completes within worker SLA.
  2. Verify Jobs WS stream shows queued → progress → completed.
  3. Preview endpoint delivers normalized JSON; Studio renders scene without manual refresh.
  4. Force parser error → Studio shows failure with log link; log contains stack trace.

## VN Pack Adapter Skeleton
- **Adapter contract**
  - Define `VNArchiveAdapter` with `load(path)`, `extract_assets(tmpdir)`, `extract_scripts(tmpdir)`, `map_to_scene_graph()`.
  - Provide registry keyed by file extension/pattern; default adapter throws `UnsupportedArchiveError`.
- **Detection & helpers**
  - Inspect extension (`.pak`, `.zip`, `.rpa`, future `.xp3`) and magic bytes; allow multi-file bundles.
  - If `tools/extractors/arc_unpacker` exists, use it as helper for supported formats (invoke via subprocess wrapper with timeout).
  - Record which helper executed for audit; adapters must run even if helper absent (fall back to placeholder extractions).
- **Dry run endpoint**
  - `/vn-pack/imports/dry-run` accepts archive path(s); enumerates candidate assets (sprites, bgm) and scripts without extracting.
  - Response lists adapters chosen, expected outputs, and any missing helper warnings; unknown formats log warning but do not abort.
  - Persist dry-run summary under `data/vn-pack/dry-runs/{timestamp}.json` for debugging.
- **Next implementation steps**
  - Flesh out Ren'Py + KiriKiri adapters first; expand matrix post verification.
  - Integrate with shared job queue for real imports once skeleton validated.

## Manga Pipeline Stubs
- **Endpoint contract**
  - `POST /manga/imports` → validates payload (images folder or archive), enqueues `manga_pipeline` job, returns `202` with `job_id`.
  - `GET /manga/imports/{job_id}` exposes status and pointers to artifact folders.
- **Stub worker flow**
  1. Create folder structure under `/data/manga/{job_id}/{raw,ocr,group,scenes}`.
  2. Copy raw pages into `raw/`.
  3. Drop placeholder JSON manifests in each subsequent stage (`ocr/index.json`, `group/index.json`, `scenes/index.json`) documenting the stub status.
  4. Emit Jobs WS progress events for `received`, `segmented`, `ocr`, `grouped`, `scenes_ready`.
- **Future hooks**
  - Panel segmentation: plan integration with `opencv`/`detectron` model; record config options now.
  - OCR: evaluate `tesseract` vs. cloud APIs; keep stub returning `{"text": "", "confidence": 0}`.
  - Bubble grouping & speaker inference: reserve slots for heuristics; store adjacency graph for voices.
- **Acceptance checks**
  1. Endpoint responds `202` with job id.
  2. Data directories materialize with placeholder artifacts.
  3. Jobs WS updates propagate; Studio Manga view can poll status without errors.

## Cross-Cutting Notes
- Queue all importer work through the existing job runner to centralize progress semantics.
- Standardize progress payloads (`type`, `job_id`, `stage`, `detail`) so Studio panels can reuse listeners.
- Ensure every importer writes human-readable logs and registers them with the log viewer list.
- Add integration tests covering Roleplay upload edge cases and VN Pack dry-run error paths once scaffolding lands.
