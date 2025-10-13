# comfyvn/server/core/ws_handlers.py
# 🔌 Shared WebSocket & SSE handler registration for Playground & Jobs

import asyncio, json, time
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

PLAYGROUND_QUEUE: asyncio.Queue = asyncio.Queue()
ACTIVE_WS: list[WebSocket] = []
JOBS_WS: list[WebSocket] = []


def register_ws_endpoints(app):
    """Attach WebSocket and SSE endpoints to a FastAPI app."""

    # SSE stream for Playground
    @app.get("/playground/stream")
    async def playground_stream():
        async def generator():
            while True:
                ev = await PLAYGROUND_QUEUE.get()
                yield f"data: {json.dumps(ev)}\n\n"

        headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
        return StreamingResponse(
            generator(), media_type="text/event-stream", headers=headers
        )

    # Playground WebSocket
    @app.websocket("/playground/ws")
    async def playground_ws(ws: WebSocket):
        await ws.accept()
        ACTIVE_WS.append(ws)
        await PLAYGROUND_QUEUE.put({"type": "connect", "clients": len(ACTIVE_WS)})
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                except Exception:
                    data = {"text": msg}
                await PLAYGROUND_QUEUE.put({"type": "message", "data": data})
        except WebSocketDisconnect:
            if ws in ACTIVE_WS:
                ACTIVE_WS.remove(ws)
            await PLAYGROUND_QUEUE.put(
                {"type": "disconnect", "clients": len(ACTIVE_WS)}
            )

    # Jobs WebSocket
    @app.websocket("/ws/jobs")
    async def ws_jobs(ws: WebSocket):
        await ws.accept()
        JOBS_WS.append(ws)
        try:
            while True:
                msg = await ws.receive_text()
                if msg.strip().lower() in ("ping", "health"):
                    await ws.send_text(json.dumps({"type": "pong", "ts": time.time()}))
        except WebSocketDisconnect:
            if ws in JOBS_WS:
                JOBS_WS.remove(ws)
