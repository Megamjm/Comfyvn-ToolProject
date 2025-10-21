from __future__ import annotations

import hashlib
import hmac
import os
import queue
import threading
import time

import httpx
from PySide6.QtGui import QAction

from comfyvn.ext.plugins import Plugin

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SECRET = os.getenv("WEBHOOK_SECRET", "")
_q: "queue.Queue[tuple[str,dict]]" = queue.Queue()


def _sign(payload: dict) -> str:
    raw = (
        (payload.get("id") or "")
        + (payload.get("type") or "")
        + str(payload.get("p") or "")
        + str(payload.get("ok") or "")
    )
    return hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()


def _worker():
    while True:
        try:
            kind, payload = _q.get()
            if not WEBHOOK_URL:
                continue
            try:
                with httpx.Client(timeout=3.0) as c:
                    c.post(
                        WEBHOOK_URL,
                        json={"kind": kind, "payload": payload},
                        headers={"X-Webhook-Signature": _sign(payload)},
                    )
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(0.02)


threading.Thread(target=_worker, daemon=True).start()


def _on_event(kind: str, payload: dict):
    _q.put((kind, payload))


plugin = Plugin(
    name="webhook",
    on_event=_on_event,
    meta={"builtin": True, "desc": "POST job events to WEBHOOK_URL with signing"},
)
