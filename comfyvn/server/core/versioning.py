from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/core/versioning.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Callable

class LegacyDeprecationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request, call_next: Callable):
        resp = await call_next(request)
        path = request.url.path or "/"
        if not path.startswith("/v1/"):
            resp.headers.setdefault("Deprecation", "true")
            resp.headers.setdefault("Link", f"</v1{path}>; rel=\"successor-version\"")
        return resp