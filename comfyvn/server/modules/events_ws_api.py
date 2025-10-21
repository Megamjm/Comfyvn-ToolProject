from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import StreamingResponse
from PySide6.QtGui import QAction

router = APIRouter()


def _split_topics(raw: Optional[str]):
    if not raw:
        return None
    return [t.strip() for t in raw.split(",") if t.strip()]


@router.get("/events/health")
def health():
    return {"ok": True}


@router.get("/events/sse")
async def sse(request: Request, topics: Optional[str] = None):
    hub = getattr(request.app.state, "event_hub", None)
    if not hub:
        return StreamingResponse(iter([b""]), media_type="text/event-stream")
    topic_list = _split_topics(topics)

    async def stream():
        q = await hub.subscribe(topic_list)
        yield b": ok\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=5)
                except asyncio.TimeoutError:
                    yield b": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(item)}\n\n".encode()
        finally:
            hub.unsubscribe(q, topic_list)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.websocket("/events/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    try:
        init = await ws.receive_json()
        topics = init.get("topics") if isinstance(init, dict) else None
    except Exception:
        topics = None

    hub = getattr(ws.app.state, "event_hub", None)
    if not hub:
        await ws.send_json({"ok": False, "error": "no event hub"})
        await ws.close()
        return

    q = await hub.subscribe(topics)
    await ws.send_json({"ok": True, "topics": topics or ["*"]})
    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=10)
                await ws.send_json(item)
            except asyncio.TimeoutError:
                await ws.send_json({"ping": True})
    except Exception:
        pass
    finally:
        hub.unsubscribe(q, topics)
