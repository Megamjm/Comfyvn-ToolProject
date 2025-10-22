from __future__ import annotations

import copy
import importlib.util
import logging
import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from comfyvn.config import feature_flags, runtime_paths
from comfyvn.viewer.minivn.player import MiniVNPlayer
from comfyvn.viewer.minivn.thumbnailer import MiniVNThumbnail

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
    runtime_mode: str = "idle"
    web_root: Path | None = None
    web_token: str | None = None
    mini_snapshot: dict[str, Any] | None = None
    mini_digest: str | None = None
    mini_seed: int = 0
    mini_pov: str | None = None
    mini_token: str | None = None
    mini_thumbnails: dict[str, MiniVNThumbnail] = field(default_factory=dict)
    mini_timeline_id: str | None = None
    stop_requested: bool = False


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
    _STATE.last_error = None
    _STATE.runtime_mode = "idle"
    _STATE.web_root = None
    _STATE.web_token = None
    _STATE.mini_snapshot = None
    _STATE.mini_digest = None
    _STATE.mini_seed = 0
    _STATE.mini_pov = None
    _STATE.mini_token = None
    _STATE.mini_thumbnails = {}
    _STATE.mini_timeline_id = None
    _STATE.stop_requested = False


def _status_payload() -> dict[str, Any]:
    fallback_params: Optional[tuple[Path, str, str]] = None
    with _LOCK:
        proc = _STATE.process
        running = bool(proc and proc.poll() is None)
        if proc and not running:
            LOGGER.debug("Viewer process finished; cleaning up state")
            project_path = _STATE.project_path
            project_id = _STATE.project_id or (
                project_path.name if project_path else None
            )
            exit_code = proc.returncode
            if not _STATE.stop_requested and project_path and project_id:
                reason = (
                    f"native viewer exited ({exit_code})"
                    if exit_code is not None
                    else "native viewer exited"
                )
                fallback_params = (project_path, project_id, reason)
            _cleanup_locked()

    if fallback_params:
        project_path, project_id, reason = fallback_params
        LOGGER.info(
            "Native viewer exited for project %s; attempting fallback: %s",
            project_id,
            reason,
        )
        if _activate_webview(project_path, project_id, reason=reason):
            return _status_payload()
        if _activate_mini_vn(
            project_path,
            project_id,
            seed=0,
            pov=None,
            timeline_id=None,
            reason=reason,
        ):
            return _status_payload()
        LOGGER.info("Viewer fallback unavailable for project %s", project_id)

    with _LOCK:
        proc = _STATE.process
        running = bool(proc and proc.poll() is None)
        runtime_mode = _STATE.runtime_mode
        virtual_running = runtime_mode in {"webview", "mini-vn"} and bool(
            _STATE.started_at
        )
        running = running or virtual_running
        payload = {
            "running": running,
            "pid": proc.pid if running and proc else None,
            "project_path": str(_STATE.project_path) if _STATE.project_path else None,
            "project_id": _STATE.project_id,
            "mode": _STATE.mode,
            "mode_detail": _STATE.mode,
            "runtime_mode": runtime_mode,
            "command": list(_STATE.command),
            "started_at": _STATE.started_at,
            "log_path": str(_STATE.log_path) if _STATE.log_path else None,
            "window_id": _STATE.window_id,
            "embed_attempted": _STATE.embed_attempted,
            "embed_fail_reason": _STATE.embed_fail_reason,
            "stub_reason": _STATE.stub_reason,
            "last_error": _STATE.last_error,
        }
        if runtime_mode == "webview" and _STATE.web_root and _STATE.web_token:
            payload["webview"] = {
                "token": _STATE.web_token,
                "entry": f"/api/viewer/web/{_STATE.web_token}/index.html",
            }
        if runtime_mode == "mini-vn" and _STATE.mini_snapshot:
            payload["mini_vn"] = _hydrate_mini_snapshot(
                _STATE.mini_snapshot, _STATE.mini_token
            )
            payload["mini_digest"] = _STATE.mini_digest
    return payload


def _build_thumbnail_url(token: str, key: str, digest: Optional[str]) -> str:
    query = ""
    if digest:
        query = f"?v={str(digest)[:12]}"
    return f"/api/viewer/mini/thumbnail/{token}/{key}{query}"


def _hydrate_mini_snapshot(
    snapshot: Optional[dict[str, Any]], token: Optional[str]
) -> Optional[dict[str, Any]]:
    if not snapshot:
        return None
    hydrated = copy.deepcopy(snapshot)

    def _decorate(entry: dict[str, Any]) -> None:
        if not token:
            return
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            return
        digest = entry.get("digest")
        entry["url"] = _build_thumbnail_url(
            token, key, str(digest) if isinstance(digest, str) else None
        )

    for thumb in hydrated.get("thumbnails", []) or []:
        if isinstance(thumb, dict):
            _decorate(thumb)

    for scene in hydrated.get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        thumb = scene.get("thumbnail")
        if isinstance(thumb, dict):
            _decorate(thumb)

    hydrated["token"] = token
    return hydrated


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


class NativeViewerUnavailable(RuntimeError):
    def __init__(self, message: str, *, stub_reason: Optional[str] = None) -> None:
        super().__init__(message)
        self.stub_reason = stub_reason or message


def _attempt_native_launch(
    project_dir: Path, project_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    with _LOCK:
        _cleanup_locked()
        command, mode, stub_reason = _resolve_command(project_dir, project_id, payload)
        if mode == "stub":
            raise NativeViewerUnavailable(
                stub_reason or "native runtime unavailable", stub_reason=stub_reason
            )

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
            raise NativeViewerUnavailable(
                f"Launch failed: {exc.filename or exc}",
                stub_reason=str(exc.filename or exc),
            ) from exc
        except Exception as exc:
            log_handle.close()
            LOGGER.exception("Failed to launch viewer: %s", exc)
            raise

        pid = proc.pid
        _STATE.process = proc
        _STATE.project_path = project_dir
        _STATE.project_id = project_id
        _STATE.mode = mode
        _STATE.command = list(command)
        _STATE.started_at = time.time()
        _STATE.log_path = log_path
        _STATE.log_handle = log_handle
        _STATE.window_id = None
        _STATE.stub_reason = None
        _STATE.embed_attempted = False
        _STATE.embed_fail_reason = None
        _STATE.last_error = None
        _STATE.runtime_mode = "native"
        _STATE.web_root = None
        _STATE.web_token = None
        _STATE.mini_snapshot = None
        _STATE.mini_digest = None
        _STATE.mini_seed = 0
        _STATE.mini_pov = None
        _STATE.mini_token = None
        _STATE.mini_thumbnails = {}
        _STATE.mini_timeline_id = None

    LOGGER.info(
        "Viewer launch requested (pid=%s, project=%s, mode=%s)", pid, project_id, mode
    )
    _spawn_window_probe(pid)
    data = _status_payload()
    data["status"] = "running"
    return data


def _activate_webview(
    project_dir: Path, project_id: str, *, reason: Optional[str] = None
) -> bool:
    if not feature_flags.is_enabled("enable_viewer_webmode", default=True):
        return False

    candidates = [
        project_dir / "web" / "index.html",
        project_dir / "game" / "web" / "index.html",
    ]
    web_root: Optional[Path] = None
    for candidate in candidates:
        if candidate.exists():
            web_root = candidate.parent
            break
    if not web_root:
        return False

    token = secrets.token_urlsafe(16)
    with _LOCK:
        _cleanup_locked()
        _STATE.project_path = project_dir
        _STATE.project_id = project_id
        _STATE.mode = "webview"
        _STATE.runtime_mode = "webview"
        _STATE.started_at = time.time()
        _STATE.stub_reason = reason
        _STATE.web_root = web_root
        _STATE.web_token = token
        _STATE.command = []
        _STATE.log_path = None
        _STATE.log_handle = None
        _STATE.last_error = None

    LOGGER.info("Viewer fallback to webview for project %s", project_id)
    return True


def _rebuild_mini_snapshot(
    project_dir: Path,
    project_id: str,
    *,
    seed: int,
    pov: Optional[str],
    timeline_id: Optional[str],
) -> Tuple[dict[str, Any], Dict[str, MiniVNThumbnail]]:
    player = MiniVNPlayer(
        project_id=project_id,
        project_path=project_dir,
        timeline_id=timeline_id,
    )
    return player.generate_snapshot(seed=seed, pov=pov, timeline_id=timeline_id)


def _activate_mini_vn(
    project_dir: Path,
    project_id: str,
    *,
    seed: int,
    pov: Optional[str],
    timeline_id: Optional[str],
    reason: Optional[str] = None,
) -> bool:
    if not feature_flags.is_enabled("enable_mini_vn", default=True):
        return False
    try:
        snapshot, thumbnails = _rebuild_mini_snapshot(
            project_dir,
            project_id,
            seed=seed,
            pov=pov,
            timeline_id=timeline_id,
        )
    except Exception as exc:
        LOGGER.exception("Mini-VN fallback failed: %s", exc)
        return False

    token = secrets.token_urlsafe(16)
    with _LOCK:
        _cleanup_locked()
        _STATE.project_path = project_dir
        _STATE.project_id = project_id
        _STATE.mode = "mini-vn"
        _STATE.runtime_mode = "mini-vn"
        _STATE.started_at = time.time()
        _STATE.mini_snapshot = snapshot
        _STATE.mini_digest = snapshot.get("digest")
        _STATE.mini_seed = seed
        _STATE.mini_pov = pov
        _STATE.mini_token = token
        _STATE.mini_thumbnails = {key: record for key, record in thumbnails.items()}
        _STATE.mini_timeline_id = snapshot.get("timeline_id")
        _STATE.stub_reason = reason
        _STATE.command = []
        _STATE.log_path = None
        _STATE.log_handle = None
        _STATE.last_error = None

    LOGGER.info("Viewer fallback to Mini-VN for project %s", project_id)
    return True


@router.post("/start")
def start_viewer(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_dir, project_id = _resolve_project(payload)
    seed = int(payload.get("seed") or 0)
    pov = payload.get("pov")
    timeline_override = payload.get("timeline") or payload.get("timeline_id")

    with _LOCK:
        native_running = bool(_STATE.process and _STATE.process.poll() is None)
        virtual_running = (
            not native_running
            and _STATE.runtime_mode in {"webview", "mini-vn"}
            and bool(_STATE.started_at)
        )
    if native_running or virtual_running:
        data = _status_payload()
        data["status"] = "running"
        return data

    try:
        return _attempt_native_launch(project_dir, project_id, payload)
    except NativeViewerUnavailable as exc:
        reason = exc.stub_reason or str(exc)
        LOGGER.info(
            "Native viewer unavailable for project %s: %s; attempting fallbacks",
            project_id,
            reason,
        )
        if _activate_webview(project_dir, project_id, reason=reason):
            data = _status_payload()
            data["status"] = "running"
            return data
        if _activate_mini_vn(
            project_dir,
            project_id,
            seed=seed,
            pov=pov,
            timeline_id=timeline_override,
            reason=reason,
        ):
            data = _status_payload()
            data["status"] = "running"
            return data
        raise HTTPException(
            status_code=503, detail=reason or "viewer unavailable"
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("Viewer launch failure: %s", exc)
        if _activate_mini_vn(
            project_dir,
            project_id,
            seed=seed,
            pov=pov,
            timeline_id=timeline_override,
            reason=str(exc),
        ):
            data = _status_payload()
            data["status"] = "running"
            return data
        raise HTTPException(
            status_code=500, detail=f"Failed to launch viewer: {exc}"
        ) from exc


@router.post("/stop")
def stop_viewer(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    with _LOCK:
        _STATE.stop_requested = True
        proc = _STATE.process
        if not proc:
            if _STATE.runtime_mode in {"webview", "mini-vn"} and _STATE.started_at:
                LOGGER.info(
                    "Viewer stop requested for %s fallback", _STATE.runtime_mode
                )
                _cleanup_locked()
            else:
                LOGGER.info("Viewer stop requested but no process is active")
        else:
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


@router.get("/web/{token}/{path:path}")
def viewer_web_asset(token: str, path: str = "index.html") -> FileResponse:
    with _LOCK:
        active_token = _STATE.web_token
        root = _STATE.web_root
    if not active_token or token != active_token or root is None:
        raise HTTPException(status_code=404, detail="web viewer not active")
    relative = path.strip("/") or "index.html"
    target = (root / relative).resolve()
    try:
        root_resolved = root.resolve()
    except Exception:
        root_resolved = root
    if not str(target).startswith(str(root_resolved)):
        raise HTTPException(status_code=403, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target)


@router.get("/mini/snapshot")
def mini_snapshot() -> dict[str, Any]:
    with _LOCK:
        snapshot = _STATE.mini_snapshot
        token = _STATE.mini_token
        digest = _STATE.mini_digest
    if not snapshot:
        raise HTTPException(status_code=404, detail="mini viewer not active")
    hydrated = _hydrate_mini_snapshot(snapshot, token)
    return {
        "ok": True,
        "data": hydrated,
        "digest": digest,
    }


@router.post("/mini/refresh")
def mini_refresh(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    with _LOCK:
        if _STATE.runtime_mode != "mini-vn" or not _STATE.project_id:
            raise HTTPException(status_code=409, detail="mini viewer not active")
        project_id = _STATE.project_id
        project_dir = _STATE.project_path
        current_seed = _STATE.mini_seed or 0
        current_pov = _STATE.mini_pov
        current_timeline = _STATE.mini_timeline_id
    if not project_dir:
        project_dir = Path(payload.get("project_path") or ".").resolve()
    seed = int(payload.get("seed") or current_seed)
    pov = payload.get("pov") or current_pov
    timeline_id = (
        payload.get("timeline_id") or payload.get("timeline") or current_timeline
    )

    try:
        snapshot, thumbnails = _rebuild_mini_snapshot(
            project_dir, project_id, seed=seed, pov=pov, timeline_id=timeline_id
        )
    except Exception as exc:
        LOGGER.exception("Mini-VN refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    token = secrets.token_urlsafe(16)
    with _LOCK:
        _STATE.mini_snapshot = snapshot
        _STATE.mini_digest = snapshot.get("digest")
        _STATE.mini_seed = seed
        _STATE.mini_pov = pov
        _STATE.mini_token = token
        _STATE.mini_thumbnails = {key: record for key, record in thumbnails.items()}
        _STATE.mini_timeline_id = snapshot.get("timeline_id")

    hydrated = _hydrate_mini_snapshot(snapshot, token)
    return {
        "ok": True,
        "data": hydrated,
        "digest": snapshot.get("digest"),
    }


@router.get("/mini/thumbnail/{token}/{key}")
def mini_thumbnail(token: str, key: str) -> FileResponse:
    with _LOCK:
        if not _STATE.mini_token or token != _STATE.mini_token:
            raise HTTPException(status_code=404, detail="thumbnail token invalid")
        record = _STATE.mini_thumbnails.get(key)
    if not record or not record.path.exists():
        raise HTTPException(status_code=404, detail="thumbnail not available")
    return FileResponse(record.path, media_type="image/png")
