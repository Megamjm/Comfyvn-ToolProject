from __future__ import annotations

"""Qt collaboration client bridge for the /api/collab WebSocket."""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWebSockets import QWebSocket

from comfyvn.config.baseurl_authority import current_authority, default_base_url

LOGGER = logging.getLogger(__name__)


def _default_base() -> str:
    try:
        authority = current_authority()
        return authority.base_url.rstrip("/")
    except Exception:
        return (os.getenv("COMFYVN_SERVER_BASE") or default_base_url()).rstrip("/")


def _build_ws_url(base: str, path: str) -> str:
    if base.startswith("https://"):
        scheme = "wss://"
        rest = base[len("https://") :]
    elif base.startswith("http://"):
        scheme = "ws://"
        rest = base[len("http://") :]
    else:
        scheme = "ws://"
        rest = base
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}{rest}{path}"


def _dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@dataclass
class _PendingPresence:
    focus: Optional[str] = None
    cursor: Optional[Dict[str, Any]] = None
    selection: Optional[Dict[str, Any]] = None
    typing: bool = False
    capabilities: set[str] = field(default_factory=set)

    def as_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.focus is not None:
            payload["focus"] = self.focus
        if self.cursor is not None:
            payload["cursor"] = self.cursor
        if self.selection is not None:
            payload["selection"] = self.selection
        if self.typing:
            payload["typing"] = True
        if self.capabilities:
            payload["capabilities"] = sorted(self.capabilities)
        return payload


class CollabClient(QObject):
    """Minimal QWebSocket wrapper for collaboration events."""

    state_changed = Signal(str)
    presence_updated = Signal(dict)
    snapshot_received = Signal(dict)
    operations_applied = Signal(dict)
    control_state = Signal(dict)
    error_occurred = Signal(dict)

    def __init__(
        self, base_url: Optional[str] = None, parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.base_url = (base_url or _default_base()).rstrip("/")
        self._scene_id = "default"
        self._actor_name = "anon"
        self._actor_id = f"client:{uuid.uuid4().hex}"
        self._clock = 0
        self._counter = 0
        self._version = 0
        self._feature_flags: Dict[str, Any] = {}
        self._explicit_close = False
        self._pending_presence = _PendingPresence()

        self.socket = QWebSocket()
        self.socket.textMessageReceived.connect(self._on_message)
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.errorOccurred.connect(self._on_error)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(3000)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._open)

    # ------------------------------------------------------------------ API
    def connect_to_scene(
        self,
        scene_id: str,
        *,
        actor_name: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> None:
        self._scene_id = scene_id or "default"
        if actor_name:
            self._actor_name = actor_name
        if actor_id:
            self._actor_id = actor_id
        self._clock = 0
        self._counter = 0
        self._version = 0
        self._explicit_close = False
        self._open()

    def disconnect(self) -> None:
        self._explicit_close = True
        self._reconnect_timer.stop()
        if self.socket.state() != QWebSocket.ClosedState:
            self.socket.close()

    def send_presence(
        self,
        *,
        focus: Optional[str] = None,
        cursor: Optional[Dict[str, Any]] = None,
        selection: Optional[Dict[str, Any]] = None,
        typing: Optional[bool] = None,
        capabilities: Optional[Sequence[str]] = None,
    ) -> None:
        if focus is not None:
            self._pending_presence.focus = focus
        if cursor is not None:
            self._pending_presence.cursor = cursor
        if selection is not None:
            self._pending_presence.selection = selection
        if typing is not None:
            self._pending_presence.typing = typing
        if capabilities is not None:
            self._pending_presence.capabilities = set(str(c) for c in capabilities)
        if self.socket.state() != QWebSocket.ConnectedState:
            return
        payload = self._pending_presence.as_payload()
        if not payload:
            return
        message = {"type": "presence.update", "payload": payload}
        self.socket.sendTextMessage(_dumps(message))

    def apply_operations(
        self,
        operations: Sequence[Dict[str, Any]],
        *,
        include_snapshot: bool = False,
        since: Optional[int] = None,
    ) -> None:
        if self.socket.state() != QWebSocket.ConnectedState:
            return
        prepared: List[Dict[str, Any]] = []
        for raw in operations:
            if not isinstance(raw, dict):
                continue
            if "kind" not in raw:
                continue
            op = dict(raw)
            self._counter += 1
            self._clock += 1
            op.setdefault("op_id", f"{self._actor_id}:{self._counter}")
            op.setdefault("actor", self._actor_id)
            op.setdefault("clock", self._clock)
            op.setdefault("timestamp", time.time())
            prepared.append(op)
        if not prepared:
            return
        payload: Dict[str, Any] = {"type": "doc.apply", "operations": prepared}
        if include_snapshot:
            payload["include_snapshot"] = True
        if since is not None:
            payload["since"] = int(since)
        self.socket.sendTextMessage(_dumps(payload))

    def request_control(self, ttl: Optional[float] = None) -> None:
        message: Dict[str, Any] = {"type": "control.request"}
        if ttl is not None:
            message["ttl"] = float(ttl)
        self._send(message)

    def release_control(self) -> None:
        self._send({"type": "control.release"})

    def pull_snapshot(self) -> None:
        self._send({"type": "doc.pull"})

    def refresh_feature_flags(self) -> None:
        self._send({"type": "feature.refresh"})

    # ------------------------------------------------------------------ Internal
    def _send(self, payload: Dict[str, Any]) -> None:
        if self.socket.state() != QWebSocket.ConnectedState:
            return
        self.socket.sendTextMessage(_dumps(payload))

    def _open(self) -> None:
        self._reconnect_timer.stop()
        url = _build_ws_url(self.base_url, f"/api/collab/ws?scene_id={self._scene_id}")
        request = QNetworkRequest(url)
        request.setRawHeader(b"x-comfyvn-name", self._actor_name.encode("utf-8"))
        request.setRawHeader(b"x-comfyvn-user", self._actor_id.encode("utf-8"))
        LOGGER.debug("Collab socket opening %s", url)
        self.state_changed.emit("connecting")
        self.socket.open(request)

    # Qt slots ---------------------------------------------------------
    def _on_connected(self) -> None:
        LOGGER.info("Collab socket connected (%s)", self._scene_id)
        self.state_changed.emit("connected")
        # send cached presence immediately
        self.send_presence()

    def _on_disconnected(self) -> None:
        self.state_changed.emit("disconnected")
        LOGGER.info("Collab socket disconnected (%s)", self._scene_id)
        if not self._explicit_close:
            self._reconnect_timer.start()

    def _on_error(self, error) -> None:  # pragma: no cover - Qt path
        LOGGER.warning("Collab socket error: %s", error)
        self.state_changed.emit(f"error:{error}")
        if not self._reconnect_timer.isActive() and not self._explicit_close:
            self._reconnect_timer.start()

    def _on_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except Exception:
            LOGGER.debug("Collab client received non-JSON payload")
            return
        msg_type = str(payload.get("type") or "")
        if msg_type == "room.joined":
            self._version = int(payload.get("version") or 0)
            self._clock = int(payload.get("clock") or 0)
            snapshot = payload.get("snapshot")
            if isinstance(snapshot, dict):
                self.snapshot_received.emit(snapshot)
            presence = payload.get("presence")
            if isinstance(presence, dict):
                self.presence_updated.emit(presence)
            flags = payload.get("feature_flags")
            if isinstance(flags, dict):
                self._feature_flags = flags
        elif msg_type in {"presence.update", "presence"}:
            data = payload.get("presence") or payload.get("data")
            if isinstance(data, dict):
                self.presence_updated.emit(data)
        elif msg_type in {"doc.update", "doc.snapshot"}:
            self._version = int(payload.get("version") or self._version)
            self._clock = max(self._clock, int(payload.get("clock") or self._clock))
            if msg_type == "doc.update":
                self.operations_applied.emit(payload)
            snapshot = payload.get("snapshot")
            if isinstance(snapshot, dict):
                self.snapshot_received.emit(snapshot)
        elif msg_type == "control.state":
            state = payload.get("state")
            if isinstance(state, dict):
                self.control_state.emit(state)
        elif msg_type == "feature.flags":
            flags = payload.get("flags")
            if isinstance(flags, dict):
                self._feature_flags = flags
        elif msg_type == "error":
            self.error_occurred.emit(payload)
        elif msg_type == "pong":
            # ignore keepalive
            return
        else:
            LOGGER.debug("Collab client ignored message type %s", msg_type)

    # Helpers ----------------------------------------------------------
    @property
    def scene_id(self) -> str:
        return self._scene_id

    @property
    def actor_id(self) -> str:
        return self._actor_id

    @property
    def actor_name(self) -> str:
        return self._actor_name

    @property
    def clock(self) -> int:
        return self._clock

    @property
    def version(self) -> int:
        return self._version

    @property
    def feature_flags(self) -> Dict[str, Any]:
        return dict(self._feature_flags)


__all__ = ["CollabClient", "SceneCollabAdapter"]


if os.name == "nt":
    _USER_NAME = os.getenv("USERNAME", "user")
else:
    _USER_NAME = os.getenv("USER", "user")
try:
    import getpass  # noqa: E402

    _USER_NAME = getpass.getuser() or _USER_NAME
except Exception:
    pass


class SceneCollabAdapter(QObject):
    """Bridge NodeEditor updates with the collaboration client."""

    def __init__(
        self,
        editor,
        client: CollabClient,
        status_label=None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.editor = editor
        self.client = client
        self.status_label = status_label
        self._actor_name = os.getenv("COMFYVN_ACTOR_NAME", _USER_NAME)
        self._current_scene_id = ""
        self._last_scene: Optional[Dict[str, Any]] = None
        self._suspend = False
        self._connected = False
        self._connection_state = "idle"
        self._last_presence: Dict[str, Any] = {}
        self._last_control: Dict[str, Any] = {}

        editor.sceneChanged.connect(self._on_scene_changed)
        editor.selectionChanged.connect(self._on_selection_changed)
        client.snapshot_received.connect(self._on_snapshot)
        client.presence_updated.connect(self._on_presence)
        client.operations_applied.connect(self._on_operations)
        client.control_state.connect(self._on_control)
        client.state_changed.connect(self._on_state)
        client.error_occurred.connect(self._on_error)

        self._render_status()

    # -------------------------------------------------------------- handlers
    def _on_state(self, state: str) -> None:
        self._connection_state = state
        self._connected = state == "connected"
        if state == "connected":
            self.client.send_presence(
                focus=self.editor.current_node_id(), capabilities=["graph.edit"]
            )
        self._render_status()

    def _on_error(self, payload: Dict[str, Any]) -> None:
        LOGGER.warning("Collab adapter error: %s", payload.get("error"))
        self._render_status(extra="error")

    def _on_scene_changed(self, scene: Dict[str, Any]) -> None:
        scene_id = str(scene.get("id") or scene.get("scene_id") or "scene")
        if scene_id != self._current_scene_id:
            self._connect(scene_id)
        if self._suspend or not self._connected:
            self._last_scene = self._clone_scene(scene)
            return
        ops = self._diff_scenes(self._last_scene or {}, scene)
        if ops:
            self.client.apply_operations(ops)
        self._last_scene = self._clone_scene(scene)
        self.client.send_presence(focus=self.editor.current_node_id())

    def _on_selection_changed(self, node_id: str) -> None:
        if node_id:
            self.client.send_presence(focus=node_id)

    def _on_snapshot(self, snapshot: Dict[str, Any]) -> None:
        scene_id = str(snapshot.get("scene_id") or snapshot.get("id") or "")
        if scene_id and scene_id != self._current_scene_id:
            self._current_scene_id = scene_id
        self._suspend = True
        try:
            self.editor.load_scene(snapshot)
            self._last_scene = self._clone_scene(self.editor.scene())
        finally:
            self._suspend = False
        self._render_status()

    def _on_presence(self, presence: Dict[str, Any]) -> None:
        self._last_presence = presence
        self._render_status()

    def _on_operations(self, payload: Dict[str, Any]) -> None:
        # operations already applied; snapshots handled separately
        self._render_status()

    def _on_control(self, state: Dict[str, Any]) -> None:
        self._last_control = state
        self._render_status()

    # -------------------------------------------------------------- helpers
    def _connect(self, scene_id: str) -> None:
        self._current_scene_id = scene_id
        self.client.connect_to_scene(scene_id, actor_name=self._actor_name)
        self._render_status()

    def _render_status(self, *, extra: Optional[str] = None) -> None:
        if not self.status_label:
            return
        participants = (
            self._last_presence.get("participants", [])
            if isinstance(self._last_presence, dict)
            else []
        )
        names = (
            ", ".join(
                p.get("user_name") or p.get("client_id") or "?" for p in participants
            )
            or "solo"
        )
        control = self._last_presence.get("control") or self._last_control or {}
        owner = control.get("owner") if isinstance(control, dict) else None
        owner_name = (
            next(
                (
                    p.get("user_name")
                    for p in participants
                    if p.get("client_id") == owner
                ),
                owner,
            )
            if owner
            else "open"
        )
        if owner:
            queue = control.get("queue") or []
            lock_text = f"lock: {owner_name}"
            if queue:
                lock_text += f" (+{len(queue)})"
        else:
            lock_text = "lock: open"
        status = self._connection_state
        if extra:
            status = f"{status}/{extra}"
        scene_tag = self._current_scene_id or "?"
        self.status_label.setText(
            f"Collab [{scene_tag}]: {names} · {lock_text} · {status}"
        )

    def _diff_scenes(
        self, old: Dict[str, Any], new: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        operations: List[Dict[str, Any]] = []
        if (old.get("start") or "") != (new.get("start") or ""):
            operations.append(
                {
                    "kind": "scene.field.set",
                    "payload": {"field": "start", "value": new.get("start") or ""},
                }
            )
        if (old.get("title") or "") != (new.get("title") or ""):
            operations.append(
                {
                    "kind": "scene.field.set",
                    "payload": {"field": "title", "value": new.get("title") or ""},
                }
            )
        old_nodes = {
            node.get("id"): node
            for node in old.get("nodes") or []
            if isinstance(node, dict) and node.get("id")
        }
        new_nodes = {
            node.get("id"): node
            for node in new.get("nodes") or []
            if isinstance(node, dict) and node.get("id")
        }
        for node_id, node in new_nodes.items():
            ref_old = old_nodes.get(node_id)
            if ref_old != node:
                operations.append(
                    {"kind": "graph.node.upsert", "payload": {"node": node}}
                )
        for node_id in old_nodes:
            if node_id not in new_nodes:
                operations.append(
                    {"kind": "graph.node.remove", "payload": {"node_id": node_id}}
                )
        return operations

    def _clone_scene(self, scene: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return json.loads(json.dumps(scene))
        except Exception:
            return dict(scene)
