# Viewer Quickstart — 2025-10-30

## Purpose
- Launch or embed a Ren’Py viewer directly from the backend so Studio panels, CI probes, or helper scripts can preview builds without manual CLI steps.
- Provide a unified log/diagnostic path (`logs/viewer/renpy_viewer.log`) regardless of which frontend requested the launch.
- Record the minimal payload contract for `/api/viewer/{start,stop,status}` so automation and GUI features stay in sync.

## Launch Requirements
- A Ren’Py project directory (default `./renpy_project`). Override with `COMFYVN_RENPY_PROJECT_DIR` or by passing `{"project_path": "/abs/path"}`.
- One of the following runtime choices (checked in order):
  1. `renpy_executable` payload key or `COMFYVN_RENPY_EXECUTABLE` env var pointing to the launcher/binary.
  2. `renpy_sdk` payload key or `COMFYVN_RENPY_SDK` env var pointing to the SDK folder (expects `renpy.sh` / `renpy.exe` inside).
  3. `renpy` available on `$PATH`.
  4. Python module `renpy` importable (falls back to `python -m renpy`).
- If none of the above are available, the service launches a Tk stub window so downstream tooling can still succeed. The stub reason is returned in the payload.

## API Surface
### `POST /api/viewer/start`
- Payload keys (all optional):
  - `project_path`: absolute or relative path to a Ren’Py project.
  - `project_id`: custom identifier stored in the process state (defaults to folder name).
  - `renpy_executable`: absolute path to the Ren’Py executable/launcher.
  - `renpy_sdk`: path to the Ren’Py SDK root; auto-resolves to `renpy.sh` / `renpy.exe`.
- Response example:

  ```json
  {
    "status": "running",
    "running": true,
    "pid": 12345,
    "project_path": "/home/user/ComfyVN/renpy_project",
    "project_id": "renpy_project",
    "mode": "renpy-sdk",
    "command": ["/opt/renpy/renpy.sh", "/home/user/ComfyVN/renpy_project"],
    "log_path": "/home/user/.local/share/ComfyVN Studio/logs/viewer/renpy_viewer.log",
    "window_id": null,
    "stub_reason": null,
    "embed_attempted": true
  }
  ```

- The backend spawns a background probe that attempts to capture the viewer window ID (Windows: HWND, Linux: X11 ID via `wmctrl`). When successful it appears in `window_id`.

### `POST /api/viewer/stop`
- Payload: `{}` (optional). Terminates the active viewer process, returns the same status payload with `"status": "stopped"`. Safe to call when no process is running.

### `GET /api/viewer/status`
- Returns the current process snapshot without mutating state. Use this to poll from Studio or CI loops.

## Environment & Tooling
- `COMFYVN_RENPY_PROJECT_DIR` — overrides the default project root.
- `COMFYVN_RENPY_EXECUTABLE` — absolute path to the Ren’Py launcher/binary.
- `COMFYVN_RENPY_SDK` — SDK directory containing `renpy.sh` / `renpy.exe`.
- `RENPY_HOME` is set automatically to the project path when the viewer launches.
- Logs live under `runtime_paths.logs_dir("viewer", "renpy_viewer.log")`. Tail the file or open Panels → Log Hub in Studio for a live feed.
- Pair with the Scenario Runner: launch the viewer, then use `/api/scenario/run/step` snapshots to drive scripted playthroughs while the viewer window stays in sync.

## Troubleshooting
- Missing project directory → `404` with `detail` field. Verify the path and ensure assets are exported.
- Missing runtime → service returns `mode: "stub"` with `stub_reason`. Install Ren’Py or point the payload/env vars to a valid binary and restart.
- Window detection failures are captured in `embed_fail_reason`; on Linux install `wmctrl` for best results.
- Viewer crashes leave the log handle open until `GET /api/viewer/status` is called; the next status poll resets the cached state.

## Related References
- `README.md` — high-level overview of viewer routes and environment flags.
- `docs/POV_DESIGN.md` — outlines Scenario Runner + POV integration that frequently pairs with viewer sessions.
- `comfyvn/server/routes/viewer.py` — reference implementation of the API surface.
