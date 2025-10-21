from __future__ import annotations

from typing import Any

import requests
from PySide6.QtGui import QAction

try:
    from comfyvn.core.log_bus import log  # optional
except Exception:

    class _L:
        def info(self, *a, **k):
            print(*a)

        def error(self, *a, **k):
            print(*a)

    log = _L()


def send_job(endpoint: str, payload: dict[str, Any]):
    """Send a render/offload job to a remote endpoint; returns {ok, status, error?}."""
    try:
        r = requests.post(f"{endpoint.rstrip('/')}/render", json=payload, timeout=10)
        ok = r.status_code < 400
        log.info(f"[remote] POST {endpoint}/render -> {r.status_code}")
        return {"ok": ok, "status": r.status_code, "body": (r.json() if ok else None)}
    except Exception as e:
        log.error(f"[remote] send_job failed: {e}")
        return {"ok": False, "error": str(e)}
