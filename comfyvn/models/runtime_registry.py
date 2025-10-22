"""
Runtime LLM adapter registry.

Provides an in-memory registry so the API layer can register temporary adapters
without mutating the on-disk JSON registry. Useful for developer tooling and
modders who want to experiment with proxies or local adapters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional


@dataclass(slots=True)
class RuntimeAdapter:
    adapter_id: str
    provider: str
    label: str
    modes: tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        # asdict will convert tuples to lists; restore tuple for readability
        modes = payload.get("modes")
        if isinstance(modes, list):
            payload["modes"] = list(modes)
        return payload


class RuntimeRegistry:
    """Thread-safe adapter registry."""

    def __init__(self) -> None:
        self._entries: Dict[str, RuntimeAdapter] = {}
        self._lock = RLock()

    def register(self, entry: RuntimeAdapter) -> RuntimeAdapter:
        with self._lock:
            self._entries[entry.adapter_id] = entry
        return entry

    def remove(self, adapter_id: str) -> None:
        with self._lock:
            self._entries.pop(adapter_id, None)

    def get(self, adapter_id: str) -> Optional[RuntimeAdapter]:
        with self._lock:
            return self._entries.get(adapter_id)

    def list(self) -> List[RuntimeAdapter]:
        with self._lock:
            return list(self._entries.values())

    def snapshot(self) -> List[Dict[str, Any]]:
        return [entry.to_dict() for entry in self.list()]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


runtime_registry = RuntimeRegistry()


def register_runtime_adapter(
    adapter_id: str,
    provider: str,
    *,
    label: Optional[str] = None,
    modes: Iterable[str] | None = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> RuntimeAdapter:
    entry = RuntimeAdapter(
        adapter_id=adapter_id,
        provider=provider,
        label=label or adapter_id,
        modes=tuple(str(mode) for mode in (modes or ())),
        metadata=dict(metadata or {}),
    )
    return runtime_registry.register(entry)


__all__ = [
    "RuntimeAdapter",
    "RuntimeRegistry",
    "register_runtime_adapter",
    "runtime_registry",
]
