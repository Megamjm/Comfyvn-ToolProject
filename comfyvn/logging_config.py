# [ComfyVN AutoPatch | Final Stage Sweep v0.4-pre | 2025-10-13]
from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_FILE = "server.log"
_REQUEST_ID_VAR: ContextVar[str | None] = ContextVar("comfyvn_request_id", default=None)
_CONTEXT_FILTER: logging.Filter | None = None

_RESERVED_ATTRS: frozenset[str] = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "request_id",
    }
)


class StructuredJsonFormatter(logging.Formatter):
    """Render log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_ATTRS
        }
        if extras:
            payload["extra"] = _serialise_extra(extras)

        return json.dumps(payload, ensure_ascii=True)


class RequestContextFilter(logging.Filter):
    """Inject the current request id into each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = get_request_id()
        if rid:
            record.request_id = rid
        elif not hasattr(record, "request_id"):
            record.request_id = None
        return True


def _serialise_extra(data: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort serialisation for logging extras."""
    serialised: Dict[str, Any] = {}
    for key, value in data.items():
        try:
            json.dumps(value)
            serialised[key] = value
        except (TypeError, ValueError):
            serialised[key] = repr(value)
    return serialised


def set_request_id(value: str | None) -> Token:
    """Set the current request id for log records."""
    return _REQUEST_ID_VAR.set(value)


def get_request_id() -> str | None:
    """Return the current request id."""
    return _REQUEST_ID_VAR.get()


def reset_request_id(token: Token) -> None:
    """Restore the previous request id context."""
    try:
        _REQUEST_ID_VAR.reset(token)
    except (RuntimeError, ValueError):
        pass


def _coerce_level(level: str) -> int:
    try:
        return getattr(logging, level.upper())
    except AttributeError:
        return logging.INFO


def _resolve_base(path: Path) -> Path:
    if not path.is_absolute():
        return (REPO_ROOT / path).resolve()
    return path.resolve()


def default_log_dir() -> Path:
    for env_name in ("LOG_DIR", "COMFYVN_LOG_DIR", "COMFYVN_SERVER_LOG_DIR"):
        override = os.getenv(env_name)
        if override:
            return _resolve_base(Path(override).expanduser())
    return _resolve_base(Path("logs"))


def _apply_context_filter(logger: logging.Logger) -> None:
    global _CONTEXT_FILTER
    if _CONTEXT_FILTER is None:
        _CONTEXT_FILTER = RequestContextFilter()
    if _CONTEXT_FILTER not in logger.filters:
        logger.addFilter(_CONTEXT_FILTER)


def init_logging(
    log_dir: str | os.PathLike[str] | None = None,
    *,
    level: str = "INFO",
    filename: str = DEFAULT_LOG_FILE,
) -> Path:
    """Initialise root logging with structured JSON output."""

    base = _resolve_base(Path(log_dir).expanduser()) if log_dir else default_log_dir()
    base.mkdir(parents=True, exist_ok=True)
    log_path = base / filename

    root_logger = logging.getLogger()
    root_logger.setLevel(_coerce_level(level))
    _apply_context_filter(root_logger)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = StructuredJsonFormatter()
    file_handler = RotatingFileHandler(
        str(log_path),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RequestContextFilter())
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RequestContextFilter())
    root_logger.addHandler(stream_handler)

    security_logger = logging.getLogger("comfyvn.security")
    security_logger.setLevel(logging.INFO)
    security_logger.propagate = False
    _apply_context_filter(security_logger)
    security_path = base / "security.log"
    if not any(
        getattr(h, "_comfyvn_security", False) for h in security_logger.handlers
    ):
        security_handler = RotatingFileHandler(
            str(security_path),
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        security_handler.setFormatter(formatter)
        security_handler.addFilter(RequestContextFilter())
        security_handler._comfyvn_security = True  # type: ignore[attr-defined]
        security_logger.addHandler(security_handler)

    os.environ.setdefault("COMFYVN_SECURITY_LOG_FILE", str(security_path))
    os.environ.setdefault("COMFYVN_LOG_FILE", str(log_path))
    os.environ.setdefault("LOG_DIR", str(base))
    return log_path
