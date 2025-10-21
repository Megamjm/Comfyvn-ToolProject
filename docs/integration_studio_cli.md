# Studio Integration Notes

## CLI (`comfyvn/cli.py`)
- Subcommands: `login`, `scenes`, `check`, `manifest`, `bundle`.
- Each command initialises logging via `init_logging(<command>)`.
- `bundle` ensures output directories exist and logs the raw → bundle conversion.

## Studio API (`comfyvn/server/modules/studio_api.py`)
- Endpoints emit structured `INFO`/`ERROR` entries.
- `export_bundle` falls back to inline JSON if `raw_path` is not provided.

## GUI Shell (`comfyvn/gui/studio_window.py`)
- Toolbar actions send POST requests through `ServerBridge.post`.
- Metrics polling logs transitions and ensures QTimer stop on close.

### Debugging Checklist
1. Run `python setup/apply_phase06_rebuild.py --recreate-all` to refresh schema.
2. Start server via `python -m comfyvn.server.app`. Tail `system.log` in the user log directory.
3. Launch GUI (`python run_comfyvn.py`) or instantiate `StudioWindow` from another PySide6 harness.
4. Use `pytest -q` to run Studio API tests (skips if `httpx` unavailable).
