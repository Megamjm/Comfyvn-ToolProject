# comfyvn/server/modules/events_api.py
# 🛰 Events API — Real-time updates via WebSocket + SSE
# [Server Core Production Chat | ComfyVN v3.1.1 Integration Sync]

from __future__ import annotations
import asyncio, json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/events", tags=["Events"])


# -------------------------------------------------------------------
# WebSocket event hub
# -------------------------------------------------------------------
@router.websocket("/ws")
async def ws_events(websocket: WebSocket):
    """
    WebSocket endpoint for real-time job and system events.
    GUI connects here for TaskManagerDock and Playground consoles.
    """
    await websocket.accept()
    app = websocket.app
    event_bus = getattr(app.state, "event_bus", None)
    if not event_bus:
        await websocket.send_text(json.dumps({"error": "event_bus unavailable"}))
        await websocket.close()
        return

    # Subscribe client to event bus
    queue = asyncio.Queue()
    event_bus.subscribe(queue)

    try:
        while True:
            data = await queue.get()
            await websocket.send_text(data)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass
    finally:
        event_bus.unsubscribe(queue)
        await websocket.close()


# -------------------------------------------------------------------
# SSE stream endpoint
# -------------------------------------------------------------------
@router.get("/sse")
async def sse_events(request: Request):
    """
    SSE endpoint used by lightweight clients or web dashboards.
    Streams text/event-stream lines from the same event bus.
    """
    event_bus = getattr(request.app.state, "event_bus", None)
    if not event_bus:

        async def error_stream():
            yield "event: error\ndata: event_bus unavailable\n\n"

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    queue = asyncio.Queue()
    event_bus.subscribe(queue)

    async def stream():
        try:
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


# -------------------------------------------------------------------
# Diagnostics (optional)
# -------------------------------------------------------------------
@router.get("/status")
async def status(request: Request):
    event_bus = getattr(request.app.state, "event_bus", None)
    count = len(getattr(event_bus, "subscribers", [])) if event_bus else 0
    return {"ok": True, "subscribers": count}
