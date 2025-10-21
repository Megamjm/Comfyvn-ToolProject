"""Central warning/event bus shared between backend and GUI."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class WarningRecord:
    """Represents a structured warning surfaced from the backend."""

    id: str
    level: str
    message: str
    source: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class WarningBus:
    """Thread-safe in-memory store for recent warnings."""

    def __init__(self, *, max_items: int = 200) -> None:
        self._max_items = max_items
        self._records: List[WarningRecord] = []
        self._lock = threading.Lock()
        self._handler_attached = False

    def record(
        self,
        message: str,
        *,
        level: str = "warning",
        source: str = "server",
        details: Optional[Dict[str, Any]] = None,
    ) -> WarningRecord:
        record = WarningRecord(
            id=str(uuid.uuid4()),
            level=level.lower(),
            message=message,
            source=source,
            details=dict(details or {}),
        )
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_items:
                self._records = self._records[-self._max_items :]
        return record

    def extend(self, records: Iterable[WarningRecord]) -> None:
        with self._lock:
            for record in records:
                self._records.append(record)
            if len(self._records) > self._max_items:
                self._records = self._records[-self._max_items :]

    def list(self, limit: int = 20) -> List[WarningRecord]:
        with self._lock:
            return list(self._records[-limit:])

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    # ------------------------------------------------------------------
    # Logging capture integration
    # ------------------------------------------------------------------
    def attach_logging_handler(self, logger: Optional[logging.Logger] = None) -> None:
        with self._lock:
            if self._handler_attached:
                return
            self._handler_attached = True
        handler = _WarningLoggingHandler(self)
        target = logger or logging.getLogger()
        target.addHandler(handler)


class _WarningLoggingHandler(logging.Handler):
    """Logging handler that forwards warning+ records to the WarningBus."""

    def __init__(self, bus: WarningBus) -> None:
        super().__init__(level=logging.WARNING)
        self._bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        details = {
            "logger": record.name,
            "levelno": record.levelno,
            "pathname": record.pathname,
            "lineno": record.lineno,
        }
        self._bus.record(
            message, level=record.levelname.lower(), source="logging", details=details
        )


warning_bus = WarningBus()
