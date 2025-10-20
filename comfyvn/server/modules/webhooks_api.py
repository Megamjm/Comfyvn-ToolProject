from __future__ import annotations
from PySide6.QtGui import QAction
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pathlib import Path
import json, time
from comfyvn.server.core.authz import require_api_key

router = APIRouter()
_REG = Path("./data/webhooks.json")

def _load():
    if _REG.exists():
        try: return json.loads(_REG.read_text(encoding="utf-8"))
        except Exception: return []
    return []

def _save(items):
    _REG.write_text(json.dumps(items, indent=2), encoding="utf-8")

@router.get("/list")
async def list_hooks():
    return {"ok": True, "items": _load()}

@router.post("/put")
async def put_hook(body: dict, _=Depends(require_api_key)):
    items = _load()
    ev = str(body.get("event") or "")
    url = str(body.get("url") or "")
    if not ev or not url:
        return JSONResponse({"ok": False, "error": "missing event or url"}, status_code=400)
    # upsert
    found = False
    for it in items:
        if it.get("event")==ev and it.get("url")==url:
            it["updated_at"] = time.time(); found = True; break
    if not found:
        items.append({"event": ev, "url": url, "created_at": time.time(), "updated_at": time.time()})
    _save(items)
    return {"ok": True, "count": len(items)}

@router.post("/emit")
async def emit(body: dict, _=Depends(require_api_key)):
    # local-only emitter: just append to an event log file; no outbound HTTP
    Path("./data/events").mkdir(parents=True, exist_ok=True)
    p = Path("./data/events")/f"emit_{int(time.time()*1000)}.json"
    p.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return {"ok": True, "stored": p.name}