from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/core/limits.py
import os, asyncio
from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse

class BodyLimitMiddleware(BaseHTTPMiddleware):
    """
    Rejects requests over COMFYVN_MAX_BODY_MB (default 25 MB).
    Uses Content-Length when present. Streams otherwise.
    """
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.max_mb = float(os.getenv("COMFYVN_MAX_BODY_MB", "25"))
        self.max_bytes = int(self.max_mb * 1024 * 1024)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return PlainTextResponse("Request entity too large", status_code=413)

        # If no Content-Length, wrap receive to enforce the cap during streaming.
        if not cl:
            received = 0
            receive = request._receive  # type: ignore[attr-defined]
            async def limited_receive() -> Message:
                nonlocal received
                message = await receive()
                if message.get("type") == "http.request":
                    body = message.get("body", b"") or b""
                    received += len(body)
                    if received > self.max_bytes:
                        return {"type": "http.request", "body": b"", "more_body": False}
                return message
            request._receive = limited_receive  # type: ignore[attr-defined]

        response = await call_next(request)
        return response

class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Cancels requests exceeding COMFYVN_REQ_TIMEOUT_S (default 60s).
    Returns 504 Gateway Timeout when exceeded.
    """
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.timeout = float(os.getenv("COMFYVN_REQ_TIMEOUT_S", "60"))

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            return PlainTextResponse("Request timed out", status_code=504)