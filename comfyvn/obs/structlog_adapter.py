"""
Minimal structured logging adapter built on ``logging.LoggerAdapter``.

The goal is to provide JSON-formatted log messages without introducing a hard
dependency on ``structlog`` while still offering a familiar small API surface.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, MutableMapping

Serializer = Callable[[Mapping[str, Any]], str]
_DEFAULT_EVENT = "log"


def _default_serializer(payload: Mapping[str, Any]) -> str:
    def _coerce(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (list, tuple)):
            return [_coerce(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): _coerce(item) for key, item in value.items()}
        return repr(value)

    coerced = {str(key): _coerce(value) for key, value in payload.items()}
    return json.dumps(coerced, ensure_ascii=False, sort_keys=True)


class StructLogAdapter(logging.LoggerAdapter):
    """Adapter that encodes log calls as structured JSON strings."""

    def __init__(
        self,
        logger: logging.Logger,
        context: Mapping[str, Any] | None = None,
        *,
        serializer: Serializer | None = None,
    ) -> None:
        super().__init__(logger, dict(context or {}))
        self._serializer: Serializer = serializer or _default_serializer

    # ``LoggerAdapter`` stores context in ``self.extra``.  We expose a ``bind``
    # helper to mirror structlog-lite ergonomics.
    def bind(self, **context: Any) -> "StructLogAdapter":
        merged = dict(self.extra)
        merged.update(context)
        return StructLogAdapter(
            self.logger,
            merged,
            serializer=self._serializer,
        )

    def unbind(self, *keys: str) -> "StructLogAdapter":
        filtered = {key: value for key, value in self.extra.items() if key not in keys}
        return StructLogAdapter(
            self.logger,
            filtered,
            serializer=self._serializer,
        )

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[str, dict]:
        event = kwargs.pop("event", None)
        payload = {}
        payload.update(self.extra)

        extra_fields = kwargs.pop("extra", None)
        if isinstance(extra_fields, Mapping):
            payload.update(extra_fields)

        if event is None:
            if isinstance(msg, str):
                event = msg
            else:
                payload["message"] = repr(msg)
                event = _DEFAULT_EVENT
        payload.setdefault("event", event or _DEFAULT_EVENT)

        if "timestamp" not in payload:
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        payload.setdefault("logger", self.logger.name)

        serialized = self._serializer(payload)
        return serialized, dict(kwargs)


def get_logger(name: str, **context: Any) -> StructLogAdapter:
    """Return an adapter bound to ``logging.getLogger(name)``."""
    logger = logging.getLogger(name)
    return StructLogAdapter(logger, context)


def serialize_event(payload: Mapping[str, Any]) -> str:
    """Serialise payloads with the adapter's default JSON encoder."""
    return _default_serializer(payload)


__all__ = ["StructLogAdapter", "get_logger", "serialize_event"]
