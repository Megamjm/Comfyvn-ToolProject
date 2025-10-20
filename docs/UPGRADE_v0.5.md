
# ComfyVN v0.5 Upgrade Notes
[COMFYVN Architect | v0.5 Scaffold & DB System | this chat]

## What's new
- Solid SQLAlchemy DB scaffold in `comfyvn/core/db_v05.py`
- New DB API mounted under `/db` (status, basic scene CRUD)
- Single mass fixer script: `tools/apply_v05_scaffold.py`
- Doctor script: `tools/doctor_v05.py`

## Configure
- Default DB is SQLite at `data/comfyvn_v05.db` (override with `COMFYVN_DB_URL` or `COMFYVN_DB_PATH`)
- Set `DB_ECHO=1` to see SQL logs

## Run
```
python -m uvicorn comfyvn.app:app --reload
# then
python tools/doctor_v05.py --base http://127.0.0.1:8000
```
