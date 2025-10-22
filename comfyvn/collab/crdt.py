from __future__ import annotations

"""
Conflict-free replicated document for collaborative scene authoring.

The CRDT is intentionally conservative: operations use last-writer-wins
registers on top-level fields, per-node payloads, and individual script
lines.  Ordering for script lines is driven by an LWW list that keeps the
latest caller-supplied order.  This keeps merges deterministic while
remaining easy to serialise for WebSocket clients.
"""

import time
import uuid
from collections import deque
from collections.abc import Iterable, MutableMapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


def _now() -> float:
    return time.time()


@dataclass(slots=True)
class CRDTOperation:
    """
    Wire representation for a document mutation.

    * ``op_id`` MUST be globally unique (actor id + monotonic counter).
    * ``clock`` is the actor Lamport clock when the op was emitted.
    * ``kind`` identifies the handler (see ``CRDTDocument._handlers``).
    * ``payload`` carries handler-specific fields.
    """

    op_id: str
    actor: str
    clock: int
    kind: str
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=_now)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "op_id": self.op_id,
            "actor": self.actor,
            "clock": self.clock,
            "kind": self.kind,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class LoggedOperation:
    """Internal record for operations that have passed through the document."""

    operation: CRDTOperation
    version: int
    server_clock: int
    applied: bool
    timestamp: float = field(default_factory=_now)

    def as_dict(self) -> Dict[str, Any]:
        data = self.operation.as_dict()
        data.update(
            {
                "version": self.version,
                "server_clock": self.server_clock,
                "applied": self.applied,
                "processed_at": self.timestamp,
            }
        )
        return data


@dataclass(slots=True)
class OperationResult:
    """Return payload for ``CRDTDocument.apply_operation``."""

    operation: CRDTOperation
    version: int
    server_clock: int
    applied: bool
    duplicate: bool

    def as_dict(self) -> Dict[str, Any]:
        data = self.operation.as_dict()
        data.update(
            {
                "version": self.version,
                "server_clock": self.server_clock,
                "applied": self.applied,
                "duplicate": self.duplicate,
            }
        )
        return data


class LWWRegister:
    """Simple last-writer-wins register."""

    __slots__ = ("value", "clock", "op_id")

    def __init__(self, value: Any = None, *, clock: int = 0, op_id: str = "") -> None:
        self.value = value
        self.clock = int(clock)
        self.op_id = str(op_id)

    def assign(self, value: Any, *, clock: int, op_id: str) -> None:
        self.value = value
        self.clock = int(clock)
        self.op_id = str(op_id)

    def update(self, value: Any, *, clock: int, op_id: str) -> bool:
        clock = int(clock)
        op_id = str(op_id)
        if clock > self.clock or (clock == self.clock and op_id > self.op_id):
            changed = value != self.value
            self.value = value
            self.clock = clock
            self.op_id = op_id
            return changed
        return False


class OrderRegister:
    """LWW register specialised for maintaining deterministic order."""

    __slots__ = ("ids", "clock", "op_id")

    def __init__(self, ids: Optional[Sequence[str]] = None) -> None:
        self.ids: List[str] = list(ids or [])
        self.clock = 0
        self.op_id = ""

    def assign(self, ids: Sequence[str], *, clock: int, op_id: str) -> None:
        self.ids = list(dict.fromkeys(str(i) for i in ids if i))
        self.clock = int(clock)
        self.op_id = str(op_id)

    def update(self, ids: Sequence[str], *, clock: int, op_id: str) -> bool:
        clock = int(clock)
        op_id = str(op_id)
        incoming = list(dict.fromkeys(str(i) for i in ids if i))
        if clock > self.clock or (clock == self.clock and op_id > self.op_id):
            changed = incoming != self.ids
            self.ids = incoming
            self.clock = clock
            self.op_id = op_id
            return changed
        return False


def _node_payload(raw: MutableMapping[str, Any]) -> Dict[str, Any]:
    payload = {key: value for key, value in raw.items() if key != "id"}
    payload["id"] = str(raw.get("id") or raw.get("node_id") or uuid.uuid4().hex)
    return payload


def _line_payload(
    raw: MutableMapping[str, Any], *, fallback_prefix: str
) -> Dict[str, Any]:
    payload = dict(raw)
    line_id = payload.get("line_id") or payload.get("id")
    if not isinstance(line_id, str) or not line_id:
        line_id = f"{fallback_prefix}{uuid.uuid4().hex}"
    payload["line_id"] = line_id
    return payload


class CRDTDocument:
    """
    Collaboration-friendly scene representation.

    The document keeps a Lamport clock (``clock``) and a monotonically increasing
    ``version`` for consumers that expect simple numeric revisions.
    """

    def __init__(
        self,
        scene_id: str,
        *,
        max_history: int = 512,
        initial: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.scene_id = scene_id
        self.clock = 0
        self.version = 0
        self.max_history = max_history

        self._title = LWWRegister(scene_id, clock=0, op_id="init")
        self._start = LWWRegister("", clock=0, op_id="init")
        self._meta: Dict[str, LWWRegister] = {}
        self._nodes: Dict[str, LWWRegister] = {}
        self._lines: Dict[str, LWWRegister] = {}
        self._line_order = OrderRegister([])

        self._history: Deque[LoggedOperation] = deque()
        self._log_index: Dict[str, LoggedOperation] = {}

        self._handlers = {
            "scene.field.set": self._op_scene_field_set,
            "scene.meta.update": self._op_scene_meta_update,
            "graph.node.upsert": self._op_graph_node_upsert,
            "graph.node.remove": self._op_graph_node_remove,
            "script.line.upsert": self._op_script_line_upsert,
            "script.line.remove": self._op_script_line_remove,
            "script.order.replace": self._op_script_order_replace,
        }

        if initial:
            self.bootstrap(initial)

    # ------------------------------------------------------------------
    # Bootstrap & snapshots
    # ------------------------------------------------------------------
    def bootstrap(self, initial: Dict[str, Any]) -> None:
        """
        Load initial state from disk without logging operations.
        """
        self.clock = int(initial.get("clock") or initial.get("lamport") or 0)
        self.version = int(initial.get("version") or 0)

        title = str(initial.get("title") or initial.get("name") or self.scene_id)
        self._title.assign(title, clock=self.clock, op_id="bootstrap")

        start = str(initial.get("start") or "")
        self._start.assign(start, clock=self.clock, op_id="bootstrap")

        for key, value in (initial.get("meta") or {}).items():
            if not isinstance(key, str):
                continue
            self._meta.setdefault(key, LWWRegister()).assign(
                value, clock=self.clock, op_id="bootstrap"
            )

        nodes = initial.get("nodes") or initial.get("graph", {}).get("nodes")
        if isinstance(nodes, Iterable):
            for raw in nodes:
                if not isinstance(raw, MutableMapping):
                    continue
                payload = _node_payload(raw)
                node_id = payload["id"]
                self._nodes.setdefault(node_id, LWWRegister()).assign(
                    payload, clock=self.clock, op_id="bootstrap"
                )

        lines = initial.get("lines") or initial.get("script", {}).get("lines")
        if isinstance(lines, Iterable):
            prefix = f"{self.scene_id}_"
            order_ids: List[str] = []
            for raw in lines:
                if not isinstance(raw, MutableMapping):
                    continue
                payload = _line_payload(raw, fallback_prefix=prefix)
                line_id = payload["line_id"]
                order_ids.append(line_id)
                self._lines.setdefault(line_id, LWWRegister()).assign(
                    payload, clock=self.clock, op_id="bootstrap"
                )
            if order_ids:
                self._line_order.assign(order_ids, clock=self.clock, op_id="bootstrap")

    def snapshot(self) -> Dict[str, Any]:
        """Return the current document payload."""
        nodes = [
            entry.value
            for entry in self._nodes.values()
            if isinstance(entry.value, MutableMapping)
        ]
        nodes.sort(key=lambda item: str(item.get("id")))

        order_ids = list(self._line_order.ids)
        existing_ids = [
            line_id for line_id, entry in self._lines.items() if entry.value
        ]
        extra_ids = [lid for lid in existing_ids if lid not in order_ids]
        all_ids = order_ids + extra_ids

        lines: List[Dict[str, Any]] = []
        for line_id in all_ids:
            entry = self._lines.get(line_id)
            if not entry or not isinstance(entry.value, MutableMapping):
                continue
            lines.append(dict(entry.value))

        meta: Dict[str, Any] = {}
        for key, reg in self._meta.items():
            if reg.value is not None:
                meta[key] = reg.value

        return {
            "scene_id": self.scene_id,
            "title": self._title.value,
            "start": self._start.value or "",
            "version": self.version,
            "clock": self.clock,
            "nodes": nodes,
            "lines": lines,
            "order": list(self._line_order.ids),
            "meta": meta,
        }

    def persistable(self) -> Dict[str, Any]:
        """Return payload for storage (includes version and lamport clock)."""
        payload = self.snapshot()
        payload["lamport"] = self.clock
        return payload

    # ------------------------------------------------------------------
    # Operation handling
    # ------------------------------------------------------------------
    def apply_operation(self, operation: CRDTOperation) -> OperationResult:
        existing = self._log_index.get(operation.op_id)
        if existing is not None:
            return OperationResult(
                operation=existing.operation,
                version=existing.version,
                server_clock=existing.server_clock,
                applied=False,
                duplicate=True,
            )

        handler = self._handlers.get(operation.kind)
        incoming_clock = max(0, int(operation.clock))
        self.clock = max(self.clock, incoming_clock) + 1
        server_clock = self.clock

        applied = False
        if handler:
            try:
                applied = bool(handler(operation, server_clock))
            except Exception:
                applied = False
        # Unknown operations are simply marked as observed so they won't be retried.

        if applied:
            self.version += 1

        record = LoggedOperation(
            operation=operation,
            version=self.version,
            server_clock=server_clock,
            applied=applied,
        )
        self._remember(record)

        return OperationResult(
            operation=operation,
            version=self.version,
            server_clock=server_clock,
            applied=applied,
            duplicate=False,
        )

    def apply_many(self, operations: Sequence[CRDTOperation]) -> List[OperationResult]:
        results: List[OperationResult] = []
        for op in operations:
            results.append(self.apply_operation(op))
        return results

    def operations_since(self, version: int) -> List[LoggedOperation]:
        """Return operation records with version strictly greater than ``version``."""
        return [record for record in self._history if record.version > version]

    # ------------------------------------------------------------------
    # Internal bookkeeping
    # ------------------------------------------------------------------
    def _remember(self, record: LoggedOperation) -> None:
        self._history.append(record)
        self._log_index[record.operation.op_id] = record
        # Trim index if history rolled over
        while len(self._history) > self.max_history:
            popped = self._history.popleft()
            self._log_index.pop(popped.operation.op_id, None)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _op_scene_field_set(self, op: CRDTOperation, server_clock: int) -> bool:
        field = str(op.payload.get("field") or "")
        value = op.payload.get("value")
        if field not in {"title", "start"}:
            return False
        register = self._title if field == "title" else self._start
        return register.update(value, clock=server_clock, op_id=op.op_id)

    def _op_scene_meta_update(self, op: CRDTOperation, server_clock: int) -> bool:
        meta = op.payload.get("meta")
        if not isinstance(meta, MutableMapping):
            return False
        changed = False
        for key, value in meta.items():
            if not isinstance(key, str):
                continue
            reg = self._meta.setdefault(key, LWWRegister())
            if reg.update(value, clock=server_clock, op_id=f"{op.op_id}:{key}"):
                changed = True
        return changed

    def _op_graph_node_upsert(self, op: CRDTOperation, server_clock: int) -> bool:
        raw = op.payload.get("node")
        if not isinstance(raw, MutableMapping):
            return False
        node = _node_payload(raw)
        node_id = node["id"]
        reg = self._nodes.setdefault(node_id, LWWRegister())
        return reg.update(node, clock=server_clock, op_id=op.op_id)

    def _op_graph_node_remove(self, op: CRDTOperation, server_clock: int) -> bool:
        node_id = str(op.payload.get("node_id") or "")
        if not node_id:
            return False
        reg = self._nodes.setdefault(node_id, LWWRegister())
        return reg.update(None, clock=server_clock, op_id=op.op_id)

    def _op_script_line_upsert(self, op: CRDTOperation, server_clock: int) -> bool:
        raw = op.payload.get("line")
        if not isinstance(raw, MutableMapping):
            return False
        after = op.payload.get("after")
        index = op.payload.get("index")

        fallback_prefix = f"{self.scene_id}_"
        payload = _line_payload(raw, fallback_prefix=fallback_prefix)
        line_id = payload["line_id"]

        reg = self._lines.setdefault(line_id, LWWRegister())
        changed = reg.update(payload, clock=server_clock, op_id=op.op_id)

        # Ensure line is registered in order if not already present
        if line_id not in self._line_order.ids:
            if isinstance(index, int):
                new_ids = list(self._line_order.ids)
                index = max(0, min(len(new_ids), index))
                new_ids.insert(index, line_id)
            elif isinstance(after, str) and after in self._line_order.ids:
                new_ids = list(self._line_order.ids)
                idx = new_ids.index(after) + 1
                new_ids.insert(idx, line_id)
            else:
                new_ids = list(self._line_order.ids) + [line_id]
            if self._line_order.update(
                new_ids, clock=server_clock, op_id=f"{op.op_id}:order"
            ):
                changed = True
        return changed

    def _op_script_line_remove(self, op: CRDTOperation, server_clock: int) -> bool:
        line_id = str(op.payload.get("line_id") or "")
        if not line_id:
            return False
        reg = self._lines.setdefault(line_id, LWWRegister())
        changed = reg.update(None, clock=server_clock, op_id=op.op_id)
        if line_id in self._line_order.ids:
            new_ids = [lid for lid in self._line_order.ids if lid != line_id]
            if self._line_order.update(
                new_ids, clock=server_clock, op_id=f"{op.op_id}:order"
            ):
                changed = True
        return changed

    def _op_script_order_replace(self, op: CRDTOperation, server_clock: int) -> bool:
        order = op.payload.get("order")
        if not isinstance(order, Sequence):
            return False
        return self._line_order.update(order, clock=server_clock, op_id=op.op_id)


__all__ = ["CRDTDocument", "CRDTOperation", "OperationResult", "LoggedOperation"]
