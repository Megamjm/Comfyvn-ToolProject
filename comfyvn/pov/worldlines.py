from __future__ import annotations

"""
Worldline registry for managing POV-aware timeline forks.

The registry keeps lightweight metadata for each worldline and provides helpers
for switching the active world so the global POV manager stays in sync.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .manager import POV, POVManager

__all__ = [
    "Worldline",
    "WorldlineRegistry",
    "WORLDLINES",
    "create_world",
    "list_worlds",
    "get_world",
    "switch_world",
    "update_world",
    "active_world",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_nodes(metadata: Mapping[str, Any]) -> List[str]:
    """
    Return a sorted list of branch node identifiers recorded in the metadata.

    Worldline metadata may expose any of the following keys:
    - ``nodes``: canonical list of node identifiers.
    - ``branch_nodes`` / ``touched_nodes``: alternate labels used by older chats.
    - ``timeline``: optional mapping with a ``nodes`` entry.
    """

    candidates: Iterable[Any] = ()
    if isinstance(metadata.get("nodes"), Iterable):
        candidates = metadata.get("nodes")  # type: ignore[assignment]
    elif isinstance(metadata.get("branch_nodes"), Iterable):
        candidates = metadata.get("branch_nodes")  # type: ignore[assignment]
    elif isinstance(metadata.get("touched_nodes"), Iterable):
        candidates = metadata.get("touched_nodes")  # type: ignore[assignment]
    elif isinstance(metadata.get("timeline"), Mapping):
        timeline = metadata.get("timeline")
        if isinstance(timeline, Mapping):
            entry = timeline.get("nodes")
            if isinstance(entry, Iterable):
                candidates = entry  # type: ignore[assignment]

    nodes: List[str] = []
    for value in candidates or []:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            nodes.append(text)
    return sorted(dict.fromkeys(nodes))


def _normalise_choices(metadata: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Return a stable mapping of POV → node_id → choice metadata.

    Expected metadata layouts:
    - ``choices``: {pov_id: {node_id: value}}
    - ``branch_states`` or ``decision_log`` share the same shape.
    """

    raw = metadata.get("choices")
    if not isinstance(raw, Mapping):
        if isinstance(metadata.get("branch_states"), Mapping):
            raw = metadata.get("branch_states")  # type: ignore[assignment]
        elif isinstance(metadata.get("decision_log"), Mapping):
            raw = metadata.get("decision_log")  # type: ignore[assignment]
        else:
            raw = {}

    choices: Dict[str, Dict[str, Any]] = {}
    for pov_key, pov_payload in raw.items():
        pov_id = str(pov_key).strip()
        if not pov_id:
            continue
        pov_choices: Dict[str, Any] = {}
        if isinstance(pov_payload, Mapping):
            for node_id, value in pov_payload.items():
                node_key = str(node_id).strip()
                if not node_key:
                    continue
                pov_choices[node_key] = value
        elif isinstance(pov_payload, Iterable):
            for entry in pov_payload:
                if not isinstance(entry, Mapping):
                    continue
                node_id = str(entry.get("node") or entry.get("id") or "").strip()
                if not node_id:
                    continue
                pov_choices[node_id] = entry.get("value")
        if pov_choices:
            choices[pov_id] = pov_choices
    return choices


@dataclass(slots=True)
class Worldline:
    id: str
    label: str
    pov: str
    root_node: str
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def snapshot(self, *, include_metadata: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "pov": self.pov,
            "root_node": self.root_node,
            "notes": self.notes,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }
        if include_metadata:
            payload["metadata"] = self.metadata.copy()
        return payload

    def update(
        self,
        *,
        label: Optional[str] = None,
        pov: Optional[str] = None,
        root_node: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if label is not None:
            self.label = label
        if pov is not None:
            self.pov = pov
        if root_node is not None:
            self.root_node = root_node
        if notes is not None:
            self.notes = notes
        if metadata is not None:
            self.metadata = dict(metadata)
        self.updated_at = _utc_now()

    def branch_nodes(self) -> List[str]:
        return _normalise_nodes(self.metadata)

    def choice_map(self) -> Dict[str, Dict[str, Any]]:
        return _normalise_choices(self.metadata)


class WorldlineRegistry:
    """
    Thread-safe worldline registry coordinating with the global POV manager.
    """

    def __init__(self, manager: Optional[POVManager] = None) -> None:
        self._lock = RLock()
        self._worlds: Dict[str, Worldline] = {}
        self._active: Optional[str] = None
        self._manager = manager or POV

    # ---------------------------------------------------------------- manager
    def attach_manager(self, manager: POVManager) -> None:
        if not isinstance(manager, POVManager):
            raise TypeError("manager must be a POVManager instance")
        with self._lock:
            self._manager = manager

    # ---------------------------------------------------------------- helpers
    def _ensure_world_id(self, world_id: str) -> str:
        key = str(world_id or "").strip()
        if not key:
            raise ValueError("world id must be a non-empty string")
        return key

    def _activate(self, world: Worldline) -> Dict[str, Any]:
        snapshot = self._manager.set(world.pov)
        self._active = world.id
        world.updated_at = _utc_now()
        return snapshot

    def ensure(self, world_id: str) -> Worldline:
        key = self._ensure_world_id(world_id)
        with self._lock:
            world = self._worlds.get(key)
            if world is None:
                raise KeyError(f"world '{key}' is not registered")
            return world

    # ---------------------------------------------------------------- actions
    def create_or_update(
        self,
        world_id: str,
        *,
        label: Optional[str] = None,
        pov: Optional[str] = None,
        root_node: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        set_active: bool = False,
    ) -> Tuple[Worldline, bool, Optional[Dict[str, Any]]]:
        """
        Add or update a worldline entry.

        Returns (world, created_flag, pov_snapshot_if_activated).
        """

        key = self._ensure_world_id(world_id)
        label_value = label if label is not None else key
        pov_value = pov if pov is not None else "narrator"
        root_value = root_node if root_node is not None else "start"
        with self._lock:
            existing = self._worlds.get(key)
            if existing is None:
                world = Worldline(
                    id=key,
                    label=label_value,
                    pov=pov_value,
                    root_node=root_value,
                    notes=notes or "",
                    metadata=dict(metadata or {}),
                )
                self._worlds[key] = world
                created = True
            else:
                existing.update(
                    label=label,
                    pov=pov,
                    root_node=root_node,
                    notes=notes,
                    metadata=metadata,
                )
                world = existing
                created = False
            pov_snapshot: Optional[Dict[str, Any]] = None
            if set_active:
                pov_snapshot = self._activate(world)
        return world, created, pov_snapshot

    def update(
        self,
        world_id: str,
        *,
        label: Optional[str] = None,
        pov: Optional[str] = None,
        root_node: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Worldline:
        world = self.ensure(world_id)
        with self._lock:
            world.update(
                label=label,
                pov=pov,
                root_node=root_node,
                notes=notes,
                metadata=metadata,
            )
            return world

    def switch(self, world_id: str) -> Tuple[Worldline, Dict[str, Any]]:
        world = self.ensure(world_id)
        with self._lock:
            snapshot = self._activate(world)
            return world, snapshot

    def reset(self) -> None:
        with self._lock:
            self._worlds.clear()
            self._active = None

    # ---------------------------------------------------------------- queries
    def list(self) -> List[Worldline]:
        with self._lock:
            return list(self._worlds.values())

    def list_payloads(self) -> List[Dict[str, Any]]:
        with self._lock:
            active_id = self._active
            payloads: List[Dict[str, Any]] = []
            for world in self._worlds.values():
                snapshot = world.snapshot()
                snapshot["active"] = world.id == active_id
                payloads.append(snapshot)
            return payloads

    def active_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._active:
                return None
            world = self._worlds.get(self._active)
            if world is None:
                return None
            snapshot = world.snapshot()
            snapshot["active"] = True
            return snapshot


WORLDLINES = WorldlineRegistry(POV)


def create_world(
    world_id: str,
    label: Optional[str] = None,
    pov: Optional[str] = None,
    root_node: Optional[str] = None,
    *,
    notes: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    activate: bool = False,
) -> Dict[str, Any]:
    world, _created, _snapshot = WORLDLINES.create_or_update(
        world_id,
        label=label,
        pov=pov,
        root_node=root_node,
        notes=notes,
        metadata=metadata,
        set_active=activate,
    )
    return world.snapshot()


def list_worlds() -> List[Dict[str, Any]]:
    return WORLDLINES.list_payloads()


def get_world(world_id: str) -> Dict[str, Any]:
    world = WORLDLINES.ensure(world_id)
    return world.snapshot()


def switch_world(world_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    world, snapshot = WORLDLINES.switch(world_id)
    return world.snapshot(), snapshot


def update_world(
    world_id: str,
    *,
    label: Optional[str] = None,
    pov: Optional[str] = None,
    root_node: Optional[str] = None,
    notes: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    world = WORLDLINES.update(
        world_id,
        label=label,
        pov=pov,
        root_node=root_node,
        notes=notes,
        metadata=metadata,
    )
    return world.snapshot()


def active_world() -> Optional[Dict[str, Any]]:
    return WORLDLINES.active_snapshot()
