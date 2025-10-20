from __future__ import annotations
from PySide6.QtGui import QAction
import asyncio, time, uuid
from typing import Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Body

jobs = APIRouter(prefix="/jobs", tags=["Jobs"])
root = APIRouter(tags=["Jobs"])

_QUEUE: List[Dict[str, Any]] = []
_SUBS: List[WebSocket] = []

def _event(e: Dict[str, Any]):
    for ws in list(_SUBS):
        try:
            asyncio.create_task(ws.send_json(e))
        except Exception:
            try:
                _SUBS.remove(ws)
            except ValueError:
                pass

@jobs.get("/poll")
def poll():
    return {"items": list(_QUEUE)}

@jobs.post("/submit")
def submit(payload: Dict[str, Any] = Body(...)):
    jid = str(uuid.uuid4())
    item = {"id": jid, "status": "queued", "payload": payload, "ts": int(time.time())}
    _QUEUE.append(item)
    _event({"type": "queued", "job": item})
    return {"ok": True, "id": jid}

async def _ws_handler(ws: WebSocket):
    await ws.accept()
    _SUBS.append(ws)
    i = 0
    try:
        await ws.send_json({"type": "hello", "queued": len(_QUEUE)})
        while True:
            await ws.send_json({"type": "heartbeat", "n": i, "ts": int(time.time())})
            i += 1
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _SUBS:
            _SUBS.remove(ws)

@jobs.websocket("/ws")
async def ws_jobs_prefixed(ws: WebSocket):
    await _ws_handler(ws)

@root.websocket("/ws/jobs")
async def ws_jobs_root(ws: WebSocket):
    await _ws_handler(ws)

from fastapi import APIRouter as _APIR
router = _APIR()
router.include_router(jobs)
router.include_router(root)