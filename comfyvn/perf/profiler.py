from __future__ import annotations

"""
Lightweight profiler utilities used by both server endpoints and tooling.

The ``PerfProfiler`` aggregates timing + memory deltas and exposes helper
context managers so callers can instrument hot paths.  The profiler stores a
bounded history for dashboards and emits modder hook envelopes for observers.
"""

import contextlib
import logging
import threading
import time
import tracemalloc
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, Iterator, List, Optional, Tuple

try:
    from comfyvn.core import modder_hooks
except Exception:  # pragma: no cover - defensive fallback
    modder_hooks = None  # type: ignore

LOGGER = logging.getLogger(__name__)


# --------------------------------------------------------------------------- Data
@dataclass
class SpanRecord:
    name: str
    category: str
    duration_ms: float
    memory_kb: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregateStats:
    name: str
    category: str
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    total_kb: float = 0.0
    max_kb: float = 0.0
    last_timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        avg_ms = self.total_ms / self.count if self.count else 0.0
        avg_kb = self.total_kb / self.count if self.count else 0.0
        return {
            "name": self.name,
            "category": self.category,
            "count": self.count,
            "total_ms": round(self.total_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "avg_ms": round(avg_ms, 3),
            "total_kb": round(self.total_kb, 3),
            "max_kb": round(self.max_kb, 3),
            "avg_kb": round(avg_kb, 3),
            "last_timestamp": self.last_timestamp,
        }


# --------------------------------------------------------------------- ProfilerCtx
class _ProfilerContext(contextlib.AbstractContextManager):
    def __init__(
        self,
        profiler: "PerfProfiler",
        name: str,
        *,
        category: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._profiler = profiler
        self._name = name
        self._category = category
        self._metadata = dict(metadata or {})
        self._start_time = 0.0
        self._start_alloc = 0

    def __enter__(self) -> "_ProfilerContext":
        self._start_time = time.perf_counter()
        try:
            current, _peak = tracemalloc.get_traced_memory()
        except RuntimeError:
            current = 0
        self._start_alloc = current
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> bool:
        duration_ms = (time.perf_counter() - self._start_time) * 1000.0
        try:
            current, _peak = tracemalloc.get_traced_memory()
        except RuntimeError:
            current = self._start_alloc
        memory_kb = max(current - self._start_alloc, 0) / 1024.0
        metadata = dict(self._metadata)
        if exc:
            metadata["exception"] = repr(exc)
        self._profiler.record_span(
            self._name,
            category=self._category,
            duration_ms=duration_ms,
            memory_kb=memory_kb,
            metadata=metadata,
        )
        # Propagate exceptions to the caller.
        return False


# -------------------------------------------------------------------- PerfProfiler
class PerfProfiler:
    """Thread-safe profiler that tracks timing and memory deltas."""

    def __init__(
        self, *, history_size: int = 256, enable_tracemalloc: bool = True
    ) -> None:
        self._lock = threading.RLock()
        self._history: Deque[SpanRecord] = deque(maxlen=history_size)
        self._aggregates: Dict[Tuple[str, str], AggregateStats] = {}
        self._marks: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._enable_tracemalloc = enable_tracemalloc
        if enable_tracemalloc and not tracemalloc.is_tracing():
            tracemalloc.start(15)

    # --------------------------------------------------------------- Instrumentation
    def profile(
        self,
        name: str,
        *,
        category: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> _ProfilerContext:
        return _ProfilerContext(self, name, category=category, metadata=metadata)

    def record_span(
        self,
        name: str,
        *,
        category: str = "general",
        duration_ms: float,
        memory_kb: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SpanRecord:
        record = SpanRecord(
            name=name,
            category=category,
            duration_ms=max(duration_ms, 0.0),
            memory_kb=max(memory_kb, 0.0),
            timestamp=time.time(),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._history.append(record)
            key = (category, name)
            stats = self._aggregates.get(key)
            if stats is None:
                stats = AggregateStats(name=name, category=category)
                self._aggregates[key] = stats
            stats.count += 1
            stats.total_ms += record.duration_ms
            stats.total_kb += record.memory_kb
            stats.max_ms = max(stats.max_ms, record.duration_ms)
            stats.max_kb = max(stats.max_kb, record.memory_kb)
            stats.last_timestamp = record.timestamp
        LOGGER.debug(
            "Recorded span %s/%s duration=%.3fms memory=%.3fKB",
            category,
            name,
            record.duration_ms,
            record.memory_kb,
        )
        self._emit_profiler_event("span.recorded", {"span": record.__dict__})
        return record

    def mark(
        self,
        name: str,
        *,
        category: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "name": name,
            "category": category,
            "timestamp": time.time(),
            "metadata": dict(metadata or {}),
        }
        with self._lock:
            self._marks.append(entry)
        LOGGER.debug("Profiler mark %s/%s", category, name)
        self._emit_profiler_event("mark.emitted", {"mark": entry})
        return entry

    # --------------------------------------------------------------------- Reporting
    def history(self, *, limit: int = 20) -> List[SpanRecord]:
        with self._lock:
            return list(self._history)[-min(limit, len(self._history)) :]

    def aggregates(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [stats.to_dict() for stats in self._aggregates.values()]

    def marks(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._marks)[-min(limit, len(self._marks)) :]

    def top_offenders(
        self,
        *,
        limit: int = 5,
        by: str = "time",
    ) -> List[Dict[str, Any]]:
        aggregates = self.aggregates()

        def key_for(item: Dict[str, Any]) -> float:
            return item["max_kb"] if by == "memory" else item["max_ms"]

        return sorted(aggregates, key=key_for, reverse=True)[:limit]

    def dashboard(self, *, limit: int = 5) -> Dict[str, Any]:
        aggregates = self.aggregates()
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in aggregates:
            grouped[item["category"]].append(item)
        for category, items in grouped.items():
            grouped[category] = sorted(
                items, key=lambda entry: entry["max_ms"], reverse=True
            )[:limit]
        snapshot = {
            "top_time": self.top_offenders(limit=limit, by="time"),
            "top_memory": self.top_offenders(limit=limit, by="memory"),
            "aggregates": aggregates,
            "marks": self.marks(limit=limit),
            "timestamp": time.time(),
        }
        self._emit_profiler_event("snapshot.generated", snapshot)
        snapshot["categories"] = grouped
        return snapshot

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
            self._marks.clear()
            self._aggregates.clear()
        self._emit_profiler_event("reset", {"timestamp": time.time()})
        LOGGER.info("PerfProfiler reset")

    # ---------------------------------------------------------------- Internal hooks
    def _emit_profiler_event(self, trigger: str, payload: Dict[str, Any]) -> None:
        if modder_hooks is None:
            return
        try:
            modder_hooks.emit(
                "on_perf_profiler_snapshot",
                {"trigger": trigger, "payload": payload, "timestamp": time.time()},
            )
        except Exception:  # pragma: no cover - defensive
            LOGGER.warning(
                "Profiler hook emission failed for %s", trigger, exc_info=True
            )


perf_profiler = PerfProfiler()

__all__ = [
    "AggregateStats",
    "PerfProfiler",
    "SpanRecord",
    "perf_profiler",
]
