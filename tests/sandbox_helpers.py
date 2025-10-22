from __future__ import annotations

import socket
from typing import Any, Dict


def attempt_connect(payload: Dict[str, Any], _job_id: str | None) -> Dict[str, Any]:
    host = str(payload.get("host", "127.0.0.1"))
    port = int(payload.get("port", 0))
    with socket.create_connection((host, port), timeout=1.0) as sock:
        sock.sendall(b"ping")
    return {"ok": True}
