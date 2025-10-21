from __future__ import annotations

import logging
import time
import traceback
import uuid

# comfyvn/server/core/errors.py
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PySide6.QtGui import QAction
from starlette.exceptions import HTTPException as StarletteHTTPException

_log = logging.getLogger("comfyvn.errors")


def _problem(
    status: int,
    title: str,
    detail: str | None,
    request: Request,
    type_: str = "about:blank",
) -> JSONResponse:
    rid = request.headers.get("X-Request-ID") or getattr(
        getattr(request, "state", object()), "X-Request-ID", None
    )
    body = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "request_id": rid,
        "ts": time.time(),
    }
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def register_exception_handlers(app):
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        return _problem(exc.status_code, exc.detail or "HTTP error", None, request)

    @app.exception_handler(RequestValidationError)
    async def _val_exc(request: Request, exc: RequestValidationError):
        _log.debug("validation error: %s", exc)
        body = {
            "type": "https://example.com/validation-error",
            "title": "Request validation failed",
            "status": 422,
            "detail": "One or more fields are invalid",
            "instance": request.url.path,
            "errors": exc.errors(),
            "request_id": request.headers.get("X-Request-ID"),
            "ts": time.time(),
        }
        return JSONResponse(
            body, status_code=422, media_type="application/problem+json"
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        err_id = str(uuid.uuid4())
        tb = "".join(traceback.format_exception(exc))
        _log.error("unhandled %s id=%s\n%s", type(exc).__name__, err_id, tb)
        return _problem(
            500,
            "Internal Server Error",
            f"error_id={err_id}",
            request,
            type_="https://example.com/internal-error",
        )
