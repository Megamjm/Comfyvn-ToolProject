from __future__ import annotations

import asyncio
import json
from typing import Optional, Sequence

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import StreamingResponse
from PySide6.QtGui import QAction
from starlette.websockets import WebSocketDisconnect

router = APIRouter()


def _split_topics(raw: Optional[str]) -> Optional[Sequence[str]]:
    if not raw:
        return None
    topics = [token.strip() for token in raw.split(",") if token.strip()]
    return topics or None


def _get_hub(app) -> Optional[object]:
    return getattr(app.state, "event_hub", None)


@router.get("/events/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@router.get("/events/sse")
async def sse(request: Request, topics: Optional[str] = None):
    hub = _get_hub(request.app)
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


async def _ws_stream(ws: WebSocket) -> None:
    await ws.accept()
    try:
        init = await ws.receive_json()
    except Exception:
        init = {}
    topics = None
    if isinstance(init, dict):
        topics = init.get("topics")

    hub = _get_hub(ws.app)
    if not hub:
        await ws.send_json(
            {
                "ok": False,
                "code": "no_event_hub",
                "message": "Event hub unavailable",
            }
        )
        await ws.close()
        return

    queue = await hub.subscribe(topics)
    selected = topics or ["*"]
    await ws.send_json({"ok": True, "topics": selected})
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=10)
                await ws.send_json(item)
            except asyncio.TimeoutError:
                await ws.send_json({"ping": True})
    except WebSocketDisconnect:
        pass
    except Exception:
        await ws.send_json(
            {
                "ok": False,
                "code": "event_stream_error",
                "message": "Event stream interrupted",
            }
        )
    finally:
        hub.unsubscribe(queue, topics)


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    await _ws_stream(ws)


@router.websocket("/events/ws")
async def ws_events_legacy(ws: WebSocket) -> None:
    await _ws_stream(ws)
