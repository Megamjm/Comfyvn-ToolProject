from __future__ import annotations

import json
import random
import time

# comfyvn/gui/services/render_service.py
from pathlib import Path

from PySide6.QtGui import QAction

from comfyvn.config.baseurl_authority import default_base_url

DB = Path("data/jobs.json")
DB.parent.mkdir(parents=True, exist_ok=True)
if not DB.exists():
    DB.write_text("[]", encoding="utf-8")


def _load():
    try:
        return json.loads(DB.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(rows):
    DB.write_text(json.dumps(rows, indent=2), encoding="utf-8")


class RenderService:
    def __init__(self, base: str | None = None):
        self.base = (base or default_base_url()).rstrip("/")

    def submit_dummy(self) -> dict:
        rows = _load()
        jid = f"job-{int(time.time())}-{random.randint(100,999)}"
        rows.append({"id": jid, "status": "queued", "progress": 0, "ts": time.time()})
        _save(rows)
        return {"ok": True, "id": jid}

    def status(self, jid: str) -> dict:
        rows = _load()
        for r in rows:
            if r["id"] == jid:
                # naive progress
                dt = time.time() - r.get("ts", time.time())
                prog = min(100, int(dt * 20))
                r["progress"] = prog
                r["status"] = "done" if prog >= 100 else "running"
                _save(rows)
                return {"ok": True, "job": r}
        return {"ok": False, "error": "not found"}
