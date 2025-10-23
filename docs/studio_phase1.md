## ComfyVN Studio Phase 1 Notes

### Overview

- **Part A — Server health & bootstrap**  
  Status: ✅ (2025-10-20)  
  - `comfyvn/server/app.py` exposes `create_app()` factory.  
  - `/health` and `/status` endpoints registered.  
  - Logging initialised to `system.log` in the user log directory; CORS enabled.
  - Launcher resolves the FastAPI port via `--server-port` → `COMFYVN_SERVER_PORT` → `data/settings/config.json` (`server.local_port`) → fallback `8001`, keeping GUI + backend aligned.

- **Part B — GUI shell & metrics**  
  Status: ✅ (2025-10-20)  
  - Menubar rebuild guard and “Modules” menu established.  
  - `ServerBridge` hooks for `set_host()` and `save_settings()` added.  
  - Metrics polling from `/system/metrics` every 3s with dock tabbing safeguards.

- **Part C — Logging & config normalisation**  
  Status: ✅ (2025-10-20)  
  - Unified logging (`launcher.log`, `gui.log`, `server.log`).  
  - Logging configuration documented in `run_comfyvn.py` and `comfyvn/server/app.py`.

### Next Steps
- Phase 2 migration extensions (`tools/apply_migrations.py`).  
- Studio registries expansion (`comfyvn/studio/core`).  
- CLI consolidation for bundle/manifest workflows.
- ~~Silence the `RegisterAssetRequest.copy` Pydantic warning and add regression coverage for `/system/settings` deep-merge semantics.~~ ✅ 2025-10-23 — Field renamed to `copy_file` and regression tests added for settings deep-merge and launcher smoke checks.
