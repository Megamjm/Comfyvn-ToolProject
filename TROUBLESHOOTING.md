# Troubleshooting
- Ensure ComfyUI at `COMFY_HOST` is running.
- Download required models listed in each preset and place into ComfyUI `models/`.
- For low VRAM, use Wan 2.2 5B preset and lower resolution/steps.
- If gallery thumbnail missing, use **Ingest PNG** to pair a render to its sidecar.
- Delete `.venv` if pip issues, then relaunch.

## Logs & Health Checks
- Review `logs/server.log`, `logs/gui.log`, and `logs/launcher.log` after a failure; CLI runs add timestamped directories under `logs/run-*/run.log`.
- Use `curl http://127.0.0.1:8001/health` (FastAPI) and `curl http://127.0.0.1:8001/healthz` (legacy probe) to confirm the backend is reachable.
- Run `pytest tests/test_server_entrypoint.py` whenever routers change to ensure `/health`, `/healthz`, and `/status` remain wired.
- Execute `python smoke_checks.py` for a quick sweep of scheduler limits and the collaboration WebSocket; capture its output when reporting issues.
