from __future__ import annotations

import logging
import traceback
import uuid
from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PySide6.QtGui import QAction
from starlette.exceptions import HTTPException as StarletteHTTPException

from comfyvn.logging_config import reset_request_id, set_request_id

_log = logging.getLogger("comfyvn.errors")


def _request_id(request: Request) -> Optional[str]:
    state_rid = getattr(request.state, "request_id", None)
    header_rid = request.headers.get("X-Request-ID")
    return state_rid or header_rid or None


def _activate_context(rid: Optional[str]):
    if not rid:
        return None
    return set_request_id(rid)


def _clear_context(token) -> None:
    if token is None:
        return
    reset_request_id(token)


def _error_response(
    request: Request,
    *,
    status: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    rid = _request_id(request)
    body = {"ok": False, "code": code, "message": message}
    if details is not None:
        body["details"] = details
    if rid:
        body["request_id"] = rid

    response = JSONResponse(body, status_code=status)
    if rid:
        response.headers["X-Request-ID"] = rid
    return response


def register_exception_handlers(app):
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        rid = _request_id(request)
        token = _activate_context(rid)
        try:
            detail = exc.detail
            message = str(detail) if detail else "Request failed"
            details = detail if isinstance(detail, (dict, list)) else None
            code = getattr(exc, "error_code", None) or f"http_{exc.status_code}"
            return _error_response(
                request,
                status=exc.status_code,
                code=code,
                message=message,
                details=details,
            )
        finally:
            _clear_context(token)

    @app.exception_handler(RequestValidationError)
    async def _val_exc(request: Request, exc: RequestValidationError):
        rid = _request_id(request)
        token = _activate_context(rid)
        try:
            _log.debug("validation error: %s", exc)
            return _error_response(
                request,
                status=422,
                code="validation_error",
                message="Request validation failed",
                details=exc.errors(),
            )
        finally:
            _clear_context(token)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        rid = _request_id(request)
        token = _activate_context(rid)
        err_id = uuid.uuid4().hex
        try:
            tb = "".join(traceback.format_exception(exc))
            _log.error(
                "Unhandled exception [%s]: %s",
                err_id,
                tb,
            )
            return _error_response(
                request,
                status=500,
                code="internal_error",
                message="Internal server error",
                details={"error_id": err_id},
            )
        finally:
            _clear_context(token)
