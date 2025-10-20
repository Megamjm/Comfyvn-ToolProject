# Roleplay Importer (Phase 3 Part A)

Endpoints:
- `POST /roleplay/import` – accepts either multipart uploads (`file` or `text`) or JSON payloads (`text`, `lines`). Logs job creation, writes raw transcript to `data/imports/roleplay`, and stores job/import metadata.
- `GET /roleplay/imports/{job_id}` – returns job status along with import metadata.

Processing steps:
1. Request validated and logged (`roleplay_api` logger).
2. Transcript written to raw folder; import row recorded (`ImportRegistry`).
3. Parser/formatter converts transcript into scene JSON; scene persisted (`SceneRegistry`).
4. Characters ensured via `CharacterRegistry`; participants linked to scene.
5. Raw transcript logged in `AssetRegistry` as asset type `transcripts` (sidecar + hash).
6. Job row updated with output payload; status can be queried via `/roleplay/imports/{job_id}`.

Debugging tips:
- Check `logs/imports/roleplay_<job>.log` for per-job transcript diagnostics.
- Inspect database rows with `sqlite3 comfyvn/data/comfyvn.db "SELECT * FROM jobs ORDER BY id DESC LIMIT 5;"`.
- Use `tests/test_studio_api.py` and future importer-specific tests for automation.
