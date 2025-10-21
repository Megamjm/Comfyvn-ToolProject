import time
from typing import Callable

from fastapi import Request
from PySide6.QtGui import QAction
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class TokenBucket:
    def __init__(self, capacity: int, refill_per_min: int):
        self.capacity = max(1, capacity)
        self.tokens = float(capacity)
        self.refill_rate = float(refill_per_min) / 60.0
        self.last = time.time()

    def allow(self) -> bool:
        now = time.time()
        self.tokens = min(
            self.capacity, self.tokens + (now - self.last) * self.refill_rate
        )
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, capacity: int = 240, refill_per_min: int = 240):
        super().__init__(app)
        self.bucket = TokenBucket(capacity, refill_per_min)

    async def dispatch(self, request: Request, call_next: Callable):
        if request.url.path.startswith("/artifacts/download"):
            return await call_next(request)
        if not self.bucket.allow():
            return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=429)
        return await call_next(request)
