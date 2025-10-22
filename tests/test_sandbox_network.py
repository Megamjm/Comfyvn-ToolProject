from __future__ import annotations

import socket
import threading

import pytest

from comfyvn.sandbox import runner


def _loopback_server() -> int:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _handler():
        try:
            conn, _ = srv.accept()
            try:
                conn.recv(8)
            finally:
                conn.close()
        except Exception:
            pass
        finally:
            srv.close()

    threading.Thread(target=_handler, daemon=True).start()
    return port


def test_sandbox_blocks_without_allowlist():
    with pytest.raises(RuntimeError, match="network blocked"):
        runner.run(
            "tests.sandbox_helpers",
            "attempt_connect",
            {"host": "127.0.0.1", "port": 9999},
            perms={"network": True},
        )


def test_sandbox_allows_allowlisted_host():
    port = _loopback_server()
    result = runner.run(
        "tests.sandbox_helpers",
        "attempt_connect",
        {"host": "127.0.0.1", "port": port},
        perms={"network": True, "network_allow": [f"127.0.0.1:{port}"]},
    )
    assert result["ok"] is True


def test_sandbox_localhost_alias():
    port = _loopback_server()
    result = runner.run(
        "tests.sandbox_helpers",
        "attempt_connect",
        {"host": "127.0.0.1", "port": port},
        perms={"network": True, "network_allow": ["localhost"]},
    )
    assert result["ok"] is True
