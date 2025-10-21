from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from pathlib import Path

import httpx
from PySide6.QtGui import QAction

HOOKS_FILE = Path("./data/webhooks.json")


def _load():
    try:
        return json.loads(HOOKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items):
    HOOKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOOKS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def list_hooks():
    return {"ok": True, "items": _load()}


def put_hook(event: str, url: str, secret: str | None = None):
    items = _load()
    for it in items:
        if it.get("event") == event and it.get("url") == url:
            it["secret"] = secret or ""
            _save(items)
            return {"ok": True}
    items.append({"event": event, "url": url, "secret": secret or ""})
    _save(items)
    return {"ok": True}


def delete_hook(event: str, url: str):
    items = [
        it for it in _load() if not (it.get("event") == event and it.get("url") == url)
    ]
    _save(items)
    return {"ok": True}


def _sign(secret: str, body: bytes) -> str:
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def emit(event: str, payload: dict):
    items = [it for it in _load() if it.get("event") == event]
    if not items:
        return
    body = json.dumps({"event": event, "ts": time.time(), "data": payload}).encode(
        "utf-8"
    )

    def _send(it):
        try:
            sig = _sign(it.get("secret", ""), body)
            headers = {"Content-Type": "application/json"}
            if sig:
                headers["X-Comfy-Signature"] = sig
            with httpx.Client(timeout=5.0) as c:
                c.post(it["url"], content=body, headers=headers)
        except Exception:
            pass

    for it in items:
        threading.Thread(target=_send, args=(it,), daemon=True).start()
