from __future__ import annotations

"""
Room orchestration for collaborative editing sessions.

Each room owns a ``CRDTDocument`` instance alongside presence bookkeeping,
lock/request-control state, and per-client cursors/selection metadata.
"""

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence

from .crdt import CRDTDocument, CRDTOperation, OperationResult

LOGGER = logging.getLogger(__name__)


def _now() -> float:
    return time.time()


@dataclass
class CollabClientState:
    client_id: str
    user_name: str
    websocket: Any
    clock: int = 0
    cursor: Optional[Dict[str, Any]] = None
    selection: Optional[Dict[str, Any]] = None
    focus: Optional[str] = None
    typing: bool = False
    capabilities: set[str] = field(default_factory=set)
    last_seen: float = field(default_factory=_now)

    def presence_payload(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "user_name": self.user_name,
            "cursor": self.cursor,
            "selection": self.selection,
            "focus": self.focus,
            "typing": self.typing,
            "last_seen": self.last_seen,
            "caps": sorted(self.capabilities),
        }


@dataclass
class CollabPresence:
    scene_id: str
    participants: List[Dict[str, Any]]
    control: Dict[str, Any]
    timestamp: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "participants": self.participants,
            "control": self.control,
            "timestamp": self.timestamp,
        }


class CollabRoom:
    def __init__(
        self,
        scene_id: str,
        document: CRDTDocument,
        *,
        persist_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        feature_flags: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.scene_id = scene_id
        self.document = document
        self.clients: Dict[str, CollabClientState] = {}

        self._persist_callback = persist_callback
        self._persist_lock = asyncio.Lock()
        self._persisted_version = document.version
        self._dirty = False

        self.feature_flags = feature_flags or {}

        self.control_owner: Optional[str] = None
        self.control_expires: float = 0.0
        self.control_queue: List[str] = []
        self.control_ttl: float = 30.0

    # Presence -----------------------------------------------------------------
    def presence(self) -> CollabPresence:
        self._expire_control_if_needed()
        participants = [state.presence_payload() for state in self.clients.values()]
        control = {
            "owner": self.control_owner,
            "expires": self.control_expires,
            "queue": list(self.control_queue),
            "mode": "exclusive" if self.control_owner else "open",
        }
        return CollabPresence(
            scene_id=self.scene_id,
            participants=participants,
            control=control,
            timestamp=_now(),
        )

    def update_presence(self, client_id: str, payload: Dict[str, Any]) -> None:
        state = self.clients.get(client_id)
        if not state:
            return
        state.last_seen = _now()
        cursor = payload.get("cursor")
        if isinstance(cursor, dict):
            state.cursor = cursor
        selection = payload.get("selection")
        if isinstance(selection, dict):
            state.selection = selection
        focus = payload.get("focus")
        if isinstance(focus, str) or focus is None:
            state.focus = focus
        typing = payload.get("typing")
        if isinstance(typing, bool):
            state.typing = typing
        caps = payload.get("capabilities")
        if isinstance(caps, Iterable):
            state.capabilities = {str(item) for item in caps if str(item)}

    # Control ------------------------------------------------------------------
    def request_control(
        self, client_id: str, *, ttl: Optional[float] = None
    ) -> Dict[str, Any]:
        now = _now()
        ttl = float(ttl or self.control_ttl)
        self._expire_control_if_needed(now=now)
        if self.control_owner in {None, client_id}:
            self.control_owner = client_id
            self.control_expires = now + ttl
            if client_id in self.control_queue:
                self.control_queue.remove(client_id)
            return {
                "granted": True,
                "owner": client_id,
                "expires": self.control_expires,
                "queue": list(self.control_queue),
            }
        if client_id not in self.control_queue:
            self.control_queue.append(client_id)
        return {
            "granted": False,
            "owner": self.control_owner,
            "expires": self.control_expires,
            "queue": list(self.control_queue),
        }

    def release_control(self, client_id: str) -> Dict[str, Any]:
        now = _now()
        if client_id == self.control_owner:
            self.control_owner = None
            self.control_expires = 0.0
            self._promote_next_owner(now=now)
        elif client_id in self.control_queue:
            self.control_queue.remove(client_id)
        return {
            "owner": self.control_owner,
            "expires": self.control_expires,
            "queue": list(self.control_queue),
        }

    def _promote_next_owner(self, *, now: Optional[float] = None) -> None:
        now = now or _now()
        while self.control_queue:
            candidate = self.control_queue.pop(0)
            if candidate in self.clients:
                self.control_owner = candidate
                self.control_expires = now + self.control_ttl
                return
        self.control_owner = None
        self.control_expires = 0.0

    def _expire_control_if_needed(self, *, now: Optional[float] = None) -> None:
        now = now or _now()
        if self.control_owner and self.control_expires and self.control_expires <= now:
            LOGGER.debug(
                "Control expired for scene %s (owner %s)",
                self.scene_id,
                self.control_owner,
            )
            self.control_owner = None
            self.control_expires = 0.0
            self._promote_next_owner(now=now)

    # Client management --------------------------------------------------------
    def join(self, client: CollabClientState) -> None:
        self.clients[client.client_id] = client
        client.last_seen = _now()

    def leave(self, client_id: str) -> None:
        if client_id in self.clients:
            self.clients.pop(client_id)
        if self.control_owner == client_id:
            self.control_owner = None
            self.control_expires = 0.0
            self._promote_next_owner()
        else:
            if client_id in self.control_queue:
                self.control_queue.remove(client_id)

    # Operations ---------------------------------------------------------------
    def apply_operations(
        self, client_id: str, operations: Sequence[CRDTOperation]
    ) -> List[OperationResult]:
        results: List[OperationResult] = []
        for op in operations:
            res = self.document.apply_operation(op)
            results.append(res)
            if res.applied:
                self._dirty = True
        state = self.clients.get(client_id)
        if state and operations:
            state.clock = max(state.clock, max(op.clock for op in operations))
            state.last_seen = _now()
        return results

    @property
    def dirty(self) -> bool:
        return self._dirty and self.document.version != self._persisted_version

    async def flush(self) -> bool:
        if not self.dirty:
            return False
        if not self._persist_callback:
            self._persisted_version = self.document.version
            self._dirty = False
            return False
        payload = self.document.persistable()
        async with self._persist_lock:
            if self.document.version == self._persisted_version:
                self._dirty = False
                return False
            await self._persist_callback(payload)
            self._persisted_version = self.document.version
            self._dirty = False
            return True

    # Convenience --------------------------------------------------------------
    def touch(self, client_id: str) -> None:
        state = self.clients.get(client_id)
        if state:
            state.last_seen = _now()


class CollabHub:
    """
    Registry for active collaboration rooms.

    The hub lazily initialises rooms with supplied factories to avoid loading
    every scene upfront.
    """

    def __init__(
        self,
        *,
        loader: Callable[[str], Any],
        saver: Callable[[Dict[str, Any]], Any],
        feature_flags: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._rooms: Dict[str, CollabRoom] = {}
        self._lock = asyncio.Lock()
        self._loader = loader
        self._saver = saver
        self._feature_flags = feature_flags or {}

    async def room(self, scene_id: str) -> CollabRoom:
        async with self._lock:
            room = self._rooms.get(scene_id)
            if room:
                return room

            initial_raw = self._loader(scene_id)
            if inspect.isawaitable(initial_raw):
                initial = await initial_raw
            else:
                initial = initial_raw
            document = CRDTDocument(scene_id, initial=initial)

            async def _persist(payload: Dict[str, Any]) -> None:
                result = self._saver(payload)
                if inspect.isawaitable(result):
                    await result

            room = CollabRoom(
                scene_id,
                document,
                persist_callback=_persist,
                feature_flags=self._feature_flags,
            )
            self._rooms[scene_id] = room
            return room

    async def flush_all(self) -> None:
        async with self._lock:
            flushes = [room.flush() for room in self._rooms.values()]
        if flushes:
            await asyncio.gather(*flushes, return_exceptions=True)

    def discard_empty(self) -> None:
        empty = [scene_id for scene_id, room in self._rooms.items() if not room.clients]
        for scene_id in empty:
            self._rooms.pop(scene_id, None)

    def update_feature_flags(self, feature_flags: Dict[str, Any]) -> None:
        self._feature_flags = dict(feature_flags)
        for room in self._rooms.values():
            room.feature_flags = dict(feature_flags)

    def stats(self) -> Dict[str, Any]:
        rooms = list(self._rooms.values())
        return {
            "rooms": len(rooms),
            "clients": sum(len(room.clients) for room in rooms),
            "dirty": sum(1 for room in rooms if room.dirty),
        }


__all__ = [
    "CollabClientState",
    "CollabPresence",
    "CollabRoom",
    "CollabHub",
]
