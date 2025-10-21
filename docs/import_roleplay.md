# Roleplay Importer (Phase 3 Part A)

Endpoints:
- `POST /roleplay/import` – accepts either multipart uploads (`file` or `text`) or JSON payloads (`text`, `lines`). Logs job creation, writes raw transcript to `data/imports/roleplay`, and stores job/import metadata.
- `GET /roleplay/imports` – lists recent import jobs (default 20) with job, import, and asset references for the Studio shell.
- `GET /roleplay/imports/{job_id}` – returns job status along with import metadata.
- `GET /roleplay/imports/{job_id}/log` – streams the raw importer log text for debugging in shell/CLI.

Processing steps:
1. Request validated and logged (`roleplay_api` logger).
2. Transcript written to raw folder; import row recorded (`ImportRegistry`).
3. Parser/formatter converts transcript into scene JSON; scene persisted (`SceneRegistry`).
4. Characters ensured via `CharacterRegistry`; participants linked to scene.
5. Raw transcript logged in `AssetRegistry` as asset type `transcripts` (sidecar + hash).
6. Job row updated with output payload; status can be queried via `/roleplay/imports/{job_id}` or listed via `/roleplay/imports`.

Debugging tips:
- Check `imports/roleplay_<job>.log` under the user log directory for per-job transcript diagnostics.
- Inspect database rows with `sqlite3 comfyvn/data/comfyvn.db "SELECT * FROM jobs ORDER BY id DESC LIMIT 5;"`.
- Use `tests/test_studio_api.py` and future importer-specific tests for automation.
- Retrieve importer log text via `curl http://localhost:8001/roleplay/imports/<job_id>/log` to surface in Studio consoles.
- The Studio `RoleplayImportView` panel now displays the job queue and streams logs via the endpoints above; use the Refresh button or let it auto-sync every 10s.
