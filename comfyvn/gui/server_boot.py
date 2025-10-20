from __future__ import annotations
from PySide6.QtGui import QAction
import time, threading, socket
import requests

def _port_open(host: str, port: int) -> bool:
    s = socket.socket(); s.settimeout(0.2)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()

def _pick_bridge():
    try:
        from . import server_bridge as sb  # type: ignore
        host = getattr(sb, "SERVER_HOST", "127.0.0.1")
        port = int(getattr(sb, "SERVER_PORT", 8001))
        for name in ("start_server_thread", "launch_server_thread",
                     "start_embedded_server", "start_server", "run_server"):
            fn = getattr(sb, name, None)
            if callable(fn):
                return host, port, fn
        uv_fn = getattr(sb, "uvicorn_run_app", None)
        if callable(uv_fn):
            def _wrap(): uv_fn()
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
        t = threading.Thread(target=_fallback_uvicorn, args=(host, port), daemon=True)
        t.start()
    else:
        starter()  # assume it spawns its own thread

def wait_for_server(base: str = "http://127.0.0.1:8001", autostart: bool = True, deadline: float = 12.0) -> bool:
    host, port, starter = _pick_bridge()
    if autostart:
        _ensure_started(host, port, starter)
    t0 = time.time()
    while time.time() - t0 < deadline:
        try:
            r = requests.get(base + "/system/ping", timeout=0.5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False