from __future__ import annotations

import logging
import time
import uuid

from PySide6.QtGui import QAction
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from comfyvn.logging_config import reset_request_id, set_request_id

_log = logging.getLogger("comfyvn.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = request.headers.get(self.header_name) or str(uuid.uuid4())
        token = set_request_id(rid)
        setattr(request.state, "request_id", rid)
        setattr(request.state, self.header_name.replace("-", "_"), rid)
        request.scope["request_id"] = rid
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[self.header_name] = rid
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Process-Time"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        dt = time.perf_counter() - t0
        try:
            response.headers[self.header_name] = f"{dt:.6f}s"
        except Exception:
            pass
        try:
            _log.info(
                "http_request",
                extra={
                    "http": {
                        "path": request.url.path,
                        "method": request.method,
                        "status_code": getattr(response, "status_code", 0),
                        "duration_ms": round(dt * 1000, 3),
                    }
                },
            )
        except Exception:
            pass
        return response
