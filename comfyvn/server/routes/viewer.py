from __future__ import annotations

import importlib.util
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Optional

from fastapi import APIRouter, HTTPException

from comfyvn.config import runtime_paths

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/viewer", tags=["viewer"])


@dataclass
class _ViewerState:
    process: subprocess.Popen[Any] | None = None
    project_path: Path | None = None
    project_id: str | None = None
    mode: str = "unknown"
    command: list[str] = field(default_factory=list)
    started_at: float | None = None
    log_path: Path | None = None
    log_handle: IO[bytes] | None = None
    window_id: int | None = None
    last_error: str | None = None
    stub_reason: str | None = None
    embed_attempted: bool = False
    embed_fail_reason: str | None = None


_STATE = _ViewerState()
_LOCK = threading.Lock()


def _resolve_project(payload: dict[str, Any] | None) -> tuple[Path, str]:
    payload = payload or {}
    raw_path = str(payload.get("project_path") or "").strip()
    project_id = str(payload.get("project_id") or "").strip()

    if raw_path:
        project_path = Path(raw_path).expanduser().resolve()
        if not project_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Project path not found: {project_path}"
            )
    else:
        default = os.getenv("COMFYVN_RENPY_PROJECT_DIR") or "renpy_project"
        project_path = Path(default)
        if not project_path.is_absolute():
            project_path = (Path.cwd() / project_path).resolve()
        if not project_path.exists():
            raise HTTPException(
                status_code=404,
                detail=(
                    "Ren'Py project directory not found. "
                    "Set COMFYVN_RENPY_PROJECT_DIR or export a Ren'Py project."
                ),
            )
    if not project_id:
        project_id = project_path.name
    return project_path, project_id


def _resolve_command(
    project_dir: Path, project_id: str, payload: dict[str, Any] | None
) -> tuple[list[str], str, Optional[str]]:
    payload = payload or {}
    explicit = payload.get("renpy_executable") or os.getenv("COMFYVN_RENPY_EXECUTABLE")
    if explicit:
        exe = Path(str(explicit)).expanduser()
        if not exe.exists():
            raise HTTPException(
                status_code=404, detail=f"Ren'Py executable not found: {exe}"
            )
        return [str(exe), str(project_dir)], "renpy-exec", None

    sdk_root = payload.get("renpy_sdk") or os.getenv("COMFYVN_RENPY_SDK")
    if sdk_root:
        sdk_path = Path(str(sdk_root)).expanduser()
        if sdk_path.is_dir():
            candidate = (
                sdk_path / ("renpy.exe" if os.name == "nt" else "renpy.sh")
            ).resolve()
            if candidate.exists():
                return [str(candidate), str(project_dir)], "renpy-sdk", None

    renpy_bin = shutil.which("renpy")
    if renpy_bin:
        return [renpy_bin, str(project_dir)], "renpy-bin", None

    if importlib.util.find_spec("renpy") is not None:
        return (
            [
                sys.executable,
                "-m",
                "renpy",
                str(project_dir),
            ],
            "renpy-module",
            None,
        )

    title = f"ComfyVN Viewer — {project_id or 'Project'}"
    message = (
        "Ren'Py runtime not configured. "
        "Launched a minimal preview window so the viewer remains usable."
    )
    script = (
        "import tkinter as tk; "
        f"root=tk.Tk(); root.title({title!r}); "
        "root.geometry('960x540'); "
        "label=tk.Label(root, text='ComfyVN Viewer', font=('Helvetica', 18)); "
        "label.pack(expand=True, fill='both'); "
        f"note=tk.Label(root, text={message!r}, wraplength=720, justify='center'); "
        "note.pack(pady=16); "
        "root.mainloop()"
    )
    return [sys.executable, "-c", script], "stub", message


def _cleanup_locked() -> None:
    if _STATE.process and _STATE.process.poll() is None:
        try:
            _STATE.process.terminate()
            _STATE.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _STATE.process.kill()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Viewer termination warning: %s", exc)
    if _STATE.log_handle:
        try:
            _STATE.log_handle.close()
        except Exception:  # pragma: no cover - defensive
            pass
    _STATE.process = None
    _STATE.project_path = None
    _STATE.project_id = None
    _STATE.mode = "unknown"
    _STATE.command = []
    _STATE.started_at = None
    _STATE.log_path = None
    _STATE.log_handle = None
    _STATE.window_id = None
    _STATE.stub_reason = None
    _STATE.embed_attempted = False
    _STATE.embed_fail_reason = None


def _status_payload() -> dict[str, Any]:
    with _LOCK:
        proc = _STATE.process
        running = bool(proc and proc.poll() is None)
        if proc and not running:
            LOGGER.debug("Viewer process finished; cleaning up state")
            _cleanup_locked()
            running = False

        payload = {
            "running": running,
            "pid": proc.pid if running and proc else None,
            "project_path": str(_STATE.project_path) if _STATE.project_path else None,
            "project_id": _STATE.project_id,
            "mode": _STATE.mode,
            "command": list(_STATE.command),
            "started_at": _STATE.started_at,
            "log_path": str(_STATE.log_path) if _STATE.log_path else None,
            "window_id": _STATE.window_id,
            "embed_attempted": _STATE.embed_attempted,
            "embed_fail_reason": _STATE.embed_fail_reason,
            "stub_reason": _STATE.stub_reason,
            "last_error": _STATE.last_error,
        }
    return payload


def _monitor_window(pid: int) -> None:
    time.sleep(0.5)  # allow the window manager to create the window
    attempts = 12
    fail_reason: Optional[str] = None
    for _ in range(attempts):
        if pid <= 0:
            fail_reason = "invalid pid"
            break
        with _LOCK:
            proc = _STATE.process
            if not proc or proc.pid != pid or proc.poll() is not None:
                return
        window_id, fail_reason = _find_window_id(pid)
        if window_id:
            with _LOCK:
                if _STATE.process and _STATE.process.pid == pid:
                    _STATE.window_id = window_id
                    _STATE.embed_attempted = True
                    _STATE.embed_fail_reason = None
            LOGGER.debug("Viewer window detected (pid=%s, wid=%s)", pid, window_id)
            return
        time.sleep(0.5)
    with _LOCK:
        if _STATE.process and _STATE.process.pid == pid:
            _STATE.embed_attempted = True
            _STATE.embed_fail_reason = fail_reason or "window handle not found"
    LOGGER.debug("Viewer window detection failed: %s", fail_reason)


def _spawn_window_probe(pid: int) -> None:
    thread = threading.Thread(target=_monitor_window, args=(pid,), daemon=True)
    thread.start()


def _find_window_id(pid: int) -> tuple[Optional[int], Optional[str]]:
    system = platform.system().lower()
    try:
        if system == "windows":
            return _find_window_id_windows(pid)
        if system == "linux":
            return _find_window_id_linux(pid)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.debug("Window probe failed: %s", exc)
        return None, str(exc)
    return None, "window detection not implemented for this platform"


def _find_window_id_windows(pid: int) -> tuple[Optional[int], Optional[str]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found_hwnd: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        lpdw_process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_process_id))
        if lpdw_process_id.value != pid:
            return True
        found_hwnd.append(hwnd)
        return False

    if not user32.EnumWindows(enum_proc, 0):
        if found_hwnd:
            return int(found_hwnd[0]), None
        return None, "EnumWindows terminated without handle"
    if not found_hwnd:
        return None, "no visible window for process"
    return int(found_hwnd[0]), None


def _find_window_id_linux(pid: int) -> tuple[Optional[int], Optional[str]]:
    wmctrl = shutil.which("wmctrl")
    if not wmctrl:
        return None, "wmctrl not available"
    try:
        result = subprocess.run(
            [wmctrl, "-lp"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - system dependent
        return None, f"wmctrl failed: {exc}"
    if result.returncode != 0:
        return None, f"wmctrl exited with {result.returncode}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        hex_id, _, pid_str, *_rest = parts + [None] * (4 - len(parts))
        try:
            line_pid = int(pid_str)
        except (TypeError, ValueError):
            continue
        if line_pid == pid:
            try:
                win_id = int(hex_id, 16)
            except ValueError:
                continue
            return win_id, None
    return None, "window for pid not listed"


@router.post("/start")
def start_viewer(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_dir, project_id = _resolve_project(payload)

    with _LOCK:
        if _STATE.process and _STATE.process.poll() is None:
            LOGGER.info("Viewer already running (pid=%s)", _STATE.process.pid)
            return {"status": "running", **_status_payload()}

        _cleanup_locked()

        command, mode, stub_reason = _resolve_command(project_dir, project_id, payload)
        log_path = runtime_paths.logs_dir("viewer", "renpy_viewer.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            log_handle = open(log_path, "ab", buffering=0)
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"Unable to open viewer log: {exc}"
            ) from exc

        env = os.environ.copy()
        env.setdefault("RENPY_HOME", str(project_dir))

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(project_dir),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        except FileNotFoundError as exc:
            log_handle.close()
            raise HTTPException(
                status_code=404, detail=f"Launch failed: {exc.filename or exc}"
            ) from exc
        except Exception as exc:
            log_handle.close()
            LOGGER.exception("Failed to launch viewer: %s", exc)
            raise HTTPException(
                status_code=500, detail=f"Failed to launch viewer: {exc}"
            ) from exc

        _STATE.process = proc
        _STATE.project_path = project_dir
        _STATE.project_id = project_id
        _STATE.mode = mode
        _STATE.command = list(command)
        _STATE.started_at = time.time()
        _STATE.log_path = log_path
        _STATE.log_handle = log_handle
        _STATE.window_id = None
        _STATE.stub_reason = stub_reason
        _STATE.embed_attempted = False
        _STATE.embed_fail_reason = None
        _STATE.last_error = None

    LOGGER.info(
        "Viewer launch requested (pid=%s, project=%s, mode=%s)",
        _STATE.process.pid if _STATE.process else "?",
        project_id,
        mode,
    )
    _spawn_window_probe(proc.pid)
    data = _status_payload()
    data["status"] = "running"
    return data


@router.post("/stop")
def stop_viewer(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    with _LOCK:
        if not _STATE.process:
            LOGGER.info("Viewer stop requested but no process is active")
            return {"status": "stopped", **_status_payload()}
        proc = _STATE.process
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            LOGGER.warning("Viewer graceful stop timed out; killing process")
            proc.kill()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Viewer stop error: %s", exc)
        finally:
            _cleanup_locked()
    payload = _status_payload()
    payload["status"] = "stopped"
    return payload


@router.get("/status")
def viewer_status() -> dict[str, Any]:
    return _status_payload()
