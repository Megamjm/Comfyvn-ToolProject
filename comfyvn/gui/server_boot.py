from __future__ import annotations

import logging
import os
import pathlib
import platform
import socket
import subprocess
import sys
import threading
import time
from typing import Optional

import requests

from comfyvn.config import ports as ports_config
from comfyvn.config.baseurl_authority import (
    current_authority,
    default_base_url,
    find_open_port,
    write_runtime_authority,
)

try:
    from comfyvn.config import runtime_paths
except Exception:  # pragma: no cover - defensive
    runtime_paths = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)
_LOCAL_BIND_HOSTS = {
    "127.0.0.1",
    "localhost",
    "0.0.0.0",
    "0",
    "*",
    "::",
    "[::]",
    "::1",
}


def _resolve_repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _default_log_path() -> pathlib.Path:
    if runtime_paths and callable(getattr(runtime_paths, "logs_dir", None)):
        return pathlib.Path(runtime_paths.logs_dir("server_detached.log"))
    return _resolve_repo_root() / "logs" / "server_detached.log"


def _apply_env_for_detached(host: str, port: int, env: Optional[dict] = None) -> dict:
    env = dict(env or os.environ)
    base = f"http://{host}:{port}"
    env.setdefault("COMFYVN_HOST", str(host))
    env.setdefault("COMFYVN_PORT", str(port))
    env.setdefault("COMFYVN_BASE_URL", base)
    env.setdefault("COMFYVN_SERVER_BASE", base)
    env.setdefault("COMFYVN_SERVER_HOST", str(host))
    env.setdefault("COMFYVN_SERVER_PORT", str(port))
    return env


def _creationflags() -> int:
    if platform.system() != "Windows":
        return 0
    detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    return int(detached) | int(new_group)


def start_detached_server(
    host: str,
    port: int,
    *,
    reload: bool = False,
    log_file: str | os.PathLike[str] | None = None,
) -> subprocess.Popen:
    """Launch the FastAPI backend via ``uvicorn`` as a detached process."""

    # Phase 2/2 Project Integration Chat — Live Fix Stub
    repo_root = _resolve_repo_root()
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    path_prefix = str(repo_root)
    if pythonpath:
        env["PYTHONPATH"] = f"{path_prefix}{os.pathsep}{pythonpath}"
    else:
        env["PYTHONPATH"] = path_prefix
    env = _apply_env_for_detached(host, port, env)

    args = [
        sys.executable,
        "-m",
        "uvicorn",
        "comfyvn.app:app",
        "--host",
        str(host),
        "--port",
        str(port),
    ]
    if reload:
        args.append("--reload")

    target_log = pathlib.Path(log_file) if log_file else _default_log_path()
    target_log.parent.mkdir(parents=True, exist_ok=True)
    creationflags = _creationflags()

    log_handle = open(target_log, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(repo_root),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    finally:
        log_handle.close()
    logging.getLogger(__name__).info(
        "Detached server launched via uvicorn (pid=%s, host=%s, port=%s, reload=%s)",
        getattr(proc, "pid", "unknown"),
        host,
        port,
        reload,
    )
    return proc


def _connect_host(host: str) -> str:
    lowered = host.strip().lower()
    if lowered in {"0.0.0.0", "0", "*"}:
        return "127.0.0.1"
    if lowered in {"::", "[::]"}:
        return "localhost"
    return host


def _normalise_ports(values) -> list[int]:
    ports: list[int] = []
    if not isinstance(values, (list, tuple)):
        values = [values]
    for value in values:
        try:
            port = int(value)
        except (TypeError, ValueError):
            continue
        if not 0 < port < 65536:
            continue
        if port not in ports:
            ports.append(port)
    if not ports:
        ports = [8001, 8000]
    return ports


def _port_open(host: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.2)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def _pick_bridge():
    try:
        from . import server_bridge as sb  # type: ignore

        authority = current_authority()
        host = getattr(sb, "SERVER_HOST", authority.host)
        port = int(getattr(sb, "SERVER_PORT", authority.port))
        for name in (
            "start_server_thread",
            "launch_server_thread",
            "start_embedded_server",
            "start_server",
            "run_server",
        ):
            fn = getattr(sb, name, None)
            if callable(fn):
                return host, port, fn
        uv_fn = getattr(sb, "uvicorn_run_app", None)
        if callable(uv_fn):

            def _wrap():
                uv_fn()

            return host, port, _wrap
        return host, port, None
    except Exception:
        return "127.0.0.1", 8001, None


def _fallback_uvicorn(host: str, port: int):
    import uvicorn

    try:
        from comfyvn.server.app import app
    except Exception:
        from comfyvn.server.app import create_app as _mk

        app = _mk()
    uvicorn.run(app, host=host, port=port, log_level="info")


def _ensure_started(host: str, port: int, starter):
    if _port_open(host, port):
        return
    if starter is None:
        try:
            start_detached_server(host, port)
            return
        except Exception:
            LOGGER.exception(
                "Detached server launch failed; falling back to inline uvicorn."
            )
        t = threading.Thread(target=_fallback_uvicorn, args=(host, port), daemon=True)
        t.start()
    else:
        starter()  # assume it spawns its own thread


def wait_for_server(
    base: str | None = None, autostart: bool = True, deadline: float = 12.0
) -> bool:
    host, port, starter = _pick_bridge()
    port_config = ports_config.get_config()
    config_host = str(port_config.get("host") or host or "127.0.0.1").strip()
    connect_host = _connect_host(config_host or host or "127.0.0.1")
    candidate_ports = _normalise_ports(port_config.get("ports") or [])
    public_base = port_config.get("public_base")
    active_port = int(port)
    if active_port not in candidate_ports:
        candidate_ports = [
            active_port,
            *[p for p in candidate_ports if p != active_port],
        ]
    target_base = (base or default_base_url()).rstrip("/")
    if autostart:
        lowered = config_host.strip().lower()
        if lowered in _LOCAL_BIND_HOSTS:
            search_order = [
                active_port,
                *[p for p in candidate_ports if p != active_port],
            ]
            resolved_port = None
            for candidate in search_order:
                opened = find_open_port(connect_host, candidate)
                if opened == candidate:
                    resolved_port = candidate
                    break
            if resolved_port is None:
                resolved_port = find_open_port(connect_host, active_port)
            if resolved_port != active_port:
                LOGGER.info(
                    "Requested port %s unavailable on %s; rolling to %s.",
                    active_port,
                    connect_host,
                    resolved_port,
                )
                active_port = resolved_port
        if public_base:
            target_base = str(public_base).rstrip("/")
        else:
            target_base = f"http://{connect_host}:{active_port}"
        try:
            write_runtime_authority(connect_host, active_port)
        except Exception as exc:
            LOGGER.warning("Failed to persist runtime state: %s", exc)
        else:
            current_authority(refresh=True)
            try:
                ports_config.record_runtime_state(
                    host=config_host or connect_host,
                    ports=candidate_ports or [active_port],
                    active_port=int(active_port),
                    base_url=target_base.rstrip("/"),
                    public_base=str(public_base) if public_base else None,
                )
            except Exception:
                LOGGER.debug("Failed to update port runtime state", exc_info=True)
            try:  # keep GUI bridge globals aligned with the resolved endpoint
                import comfyvn.gui.services.server_bridge as sb  # type: ignore

                sb.SERVER_HOST = connect_host
                sb.SERVER_PORT = active_port
                sb.DEFAULT_BASE = target_base
                refresh = getattr(sb, "refresh_authority_cache", None)
                if callable(refresh):
                    refresh(refresh=True)
            except Exception:
                pass
        os.environ["COMFYVN_SERVER_BASE"] = target_base
        os.environ["COMFYVN_BASE_URL"] = target_base
        os.environ["COMFYVN_SERVER_HOST"] = connect_host
        os.environ["COMFYVN_SERVER_PORT"] = str(active_port)
        _ensure_started(host, active_port, starter)
    t0 = time.time()
    while time.time() - t0 < deadline:
        try:
            r = requests.get(target_base + "/system/ping", timeout=0.5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False
