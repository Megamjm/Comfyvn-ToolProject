
# ComfyVN v0.6 Upgrade Notes
[COMFYVN Architect | v0.6 Patch | this chat]

## What's new (0.5.1..0.6)
- **Events Bus** (SSE at `/events-bus/sse`, health at `/events-bus/health`)
- **Jobs API**: `/jobs/enqueue`, `/jobs/status`, `/jobs/{id}`, `/jobs/{id}/update`
- **Settings API**: `/system/settings` (GET/POST) with `/system/settings/schema` for defaults + validation metadata
- **Export stub**: `/export/renpy/plan` + `/export/health`
- **Doctor v0.6**: `tools/doctor_v06.py`
- Patches `app.py` to initialize `EventHub` and mount routers

## Configure
- DB is SQLite by default: `data/comfyvn_v05.db` (override with `COMFYVN_DB_URL`)
- Set `DB_ECHO=1` for SQL logs
- Apply migrations via `python tools/apply_migrations.py --list` (dry-run) then `python tools/apply_migrations.py --verbose` during rollout.
- Post-upgrade health checks: `python tools/db_integrity_check.py` (expects `ok`) and `python tools/seed_demo_data.py --force` for smoke fixtures if desired.

## Run
```
uvicorn comfyvn.app:app --reload
python tools/doctor_v06.py --base http://127.0.0.1:8000
```
