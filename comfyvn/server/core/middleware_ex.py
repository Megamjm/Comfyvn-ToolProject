from __future__ import annotations

import logging
# comfyvn/server/core/middleware_ex.py
import time
import uuid

from PySide6.QtGui import QAction
from starlette.middleware.base import (BaseHTTPMiddleware,
                                       RequestResponseEndpoint)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_log = logging.getLogger("comfyvn.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = request.headers.get(self.header_name) or str(uuid.uuid4())
        response = await call_next(request)
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
                '{"path":"%s","method":"%s","status":%s,"dt":%.6f}',
                request.url.path,
                request.method,
                getattr(response, "status_code", 0),
                dt,
            )
        except Exception:
            pass
        return response
