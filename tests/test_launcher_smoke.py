from __future__ import annotations

import socket
import sys
import threading
import time
import types

import httpx
import pytest
import uvicorn

if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui

import run_comfyvn


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_launcher_server_smoke():
    port = _find_open_port()
    args = run_comfyvn.parse_arguments(["--server-only", "--server-port", str(port)])
    run_comfyvn.apply_launcher_environment(args)

    config = uvicorn.Config(
        args.uvicorn_app,
        host=args.server_host,
        port=args.server_port,
        log_level="warning",
        factory=args.uvicorn_factory,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2.0)
    try:
        for _ in range(50):
            try:
                health_resp = client.get("/health")
                if health_resp.status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.fail("launcher server did not respond to /health")

        body = health_resp.json()
        assert health_resp.status_code == 200
        assert body.get("ok") is True or body.get("status") == "ok"

        status_resp = client.get("/status")
        assert status_resp.status_code == 200
        assert status_resp.json().get("ok") is True
    finally:
        client.close()
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive(), "server thread failed to stop"
