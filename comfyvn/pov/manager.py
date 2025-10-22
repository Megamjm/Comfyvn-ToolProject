from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional


@dataclass
class POVState:
    """Persisted POV payload shared across GUI + server surfaces."""

    current: str
    history: List[str] = field(default_factory=list)


class POVManager:
    """
    Tracks the active narrative perspective (POV) and assists with branching.

    The manager keeps a lightweight state payload (current POV + history) and
    exposes helpers for deriving save slot identifiers and POV candidates.
    """

    def __init__(self, default_pov: str = "narrator") -> None:
        self._default = default_pov
        self._state = POVState(current=default_pov)
        self._slot_counters: Dict[tuple[str, str], int] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------ state
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pov": self._state.current,
                "history": list(self._state.history),
            }

    def get(self) -> str:
        with self._lock:
            return self._state.current

    def set(self, char_id: Optional[str]) -> Dict[str, Any]:
        if not char_id:
            char_id = self._default
        char_id = str(char_id)
        with self._lock:
            if self._state.current != char_id:
                self._state.history.append(self._state.current)
                self._state.current = char_id
            return {
                "pov": self._state.current,
                "history": list(self._state.history),
            }

    def reset(self) -> None:
        with self._lock:
            self._state = POVState(current=self._default)
            self._slot_counters.clear()

    # ------------------------------------------------------------------ forks
    def fork_id(self, base_slot: str, pov: Optional[str] = None) -> str:
        if not base_slot:
            raise ValueError("base_slot must be a non-empty string")
        pov_id = str(pov or self.get() or self._default)
        slot_key = (base_slot, pov_id)
        with self._lock:
            counter = self._slot_counters.get(slot_key, 0) + 1
            self._slot_counters[slot_key] = counter
        suffix = f"{base_slot}__pov_{pov_id}"
        if counter > 1:
            suffix = f"{suffix}_{counter}"
        return suffix

    # --------------------------------------------------------------- candidates
    def candidates(self, scene: Mapping[str, Any]) -> List[Dict[str, str]]:
        if not isinstance(scene, Mapping):
            return []
        seen: Dict[str, Dict[str, str]] = {}

        def _register(
            entry_id: Optional[str], name: Optional[str], source: str
        ) -> None:
            if not entry_id:
                return
            key = str(entry_id)
            if key not in seen:
                display = str(name or entry_id)
                seen[key] = {"id": key, "name": display, "source": source}

        cast = scene.get("cast")
        if isinstance(cast, Iterable):
            for member in cast:
                if isinstance(member, Mapping):
                    _register(member.get("id"), member.get("name"), "cast")

        nodes = scene.get("nodes")
        if isinstance(nodes, Iterable):
            for node in nodes:
                if not isinstance(node, Mapping):
                    continue
                meta = node.get("metadata")
                if isinstance(meta, Mapping):
                    _register(meta.get("pov"), meta.get("pov_name"), "node.meta")
                    _register(
                        meta.get("speaker_id"), meta.get("speaker_name"), "node.meta"
                    )
                _register(node.get("pov"), node.get("pov_name"), "node")
                _register(node.get("speaker"), node.get("speaker"), "node")
        return list(seen.values())

    # ------------------------------------------------------------------ helpers
    def ensure_mapping(self, payload: Any, *, detail: str) -> MutableMapping[str, Any]:
        if isinstance(payload, MutableMapping):
            return payload
        raise ValueError(detail)


POV = POVManager()

__all__ = ["POV", "POVManager", "POVState"]
