from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView

logger = logging.getLogger(__name__)

Hook = Callable[[Dict[str, Any]], None]


@dataclass
class StageState:
    """Tracks the latest snapshot emitted by the WebGL stage."""

    payload: Dict[str, Any] = field(default_factory=dict)
    html_path: Path = field(
        default_factory=lambda: Path(__file__).with_name("viewport.html")
    )
    config: Dict[str, Any] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


class _StageBridgeProxy(QObject):
    """Qt <-> JavaScript shim registered as `StageBridge` inside the web view."""

    ready = Signal(dict)
    event = Signal(str, dict)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    @Slot(str)
    def notifyReady(self, payload: str) -> None:
        try:
            data = json.loads(payload) if payload else {"ok": True}
        except json.JSONDecodeError:
            data = {"ok": False, "error": payload}
        self.ready.emit(data)

    @Slot(str, str)
    def notifyEvent(self, name: str, payload: str) -> None:
        try:
            data = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            data = {"raw": payload}
        self.event.emit(name, data)


class Stage3DView(QWebEngineView):
    """Embeds the WebGL playground stage (Tier-1) inside Qt."""

    stage_ready = Signal(dict)
    stage_event = Signal(str, dict)
    stage_snapshot = Signal(dict)
    stage_log = Signal(dict)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        auto_load: bool = True,
        on_stage_snapshot: Optional[Hook] = None,
        on_stage_load: Optional[Hook] = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_AlwaysStackOnTop, False)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True
        )
        self.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, False
        )
        self._channel = QWebChannel(self.page())
        self._proxy = _StageBridgeProxy()
        self._channel.registerObject("StageBridge", self._proxy)
        self.page().setWebChannel(self._channel)
        self._hooks: Dict[str, List[Hook]] = {
            "on_stage_snapshot": [],
            "on_stage_load": [],
            "on_stage_log": [],
        }
        if on_stage_snapshot:
            self.register_hook("on_stage_snapshot", on_stage_snapshot)
        if on_stage_load:
            self.register_hook("on_stage_load", on_stage_load)
        self._state = StageState()
        self._last_ready: Dict[str, Any] = {}

        self._proxy.ready.connect(self._handle_ready)
        self._proxy.event.connect(self._handle_event)

        if auto_load:
            self.reload_stage()

    # ------------------------------------------------------------------ hooks
    def register_hook(self, name: str, callback: Hook) -> None:
        if name not in self._hooks:
            raise ValueError(f"Unknown Stage3D hook '{name}'")
        self._hooks[name].append(callback)

    def _emit(self, name: str, payload: Dict[str, Any]) -> None:
        for callback in self._hooks.get(name, []):
            try:
                callback(dict(payload))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Stage3D hook '%s' failed: %s", name, exc, exc_info=True)

    # ------------------------------------------------------------------ lifecycle
    def reload_stage(self) -> None:
        html_path = self._state.html_path
        url = QUrl.fromLocalFile(str(html_path.resolve()))
        logger.debug("Loading Stage3D viewport HTML from %s", url.toString())
        self.load(url)

    # ------------------------------------------------------------------ event handlers
    def _handle_ready(self, payload: Dict[str, Any]) -> None:
        self._last_ready = payload
        logger.info("Stage3D ready: %s", payload)
        self.stage_ready.emit(payload)
        self._emit("on_stage_load", {"event": "stage.ready", "payload": payload})

    def _handle_event(self, name: str, payload: Dict[str, Any]) -> None:
        logger.debug("Stage3D event '%s': %s", name, payload)
        self.stage_event.emit(name, payload)
        if name == "stage.snapshot":
            if self._state.config and "config" not in payload:
                payload["config"] = dict(self._state.config)
            self._state.payload = payload
            self.stage_snapshot.emit(payload)
            self._emit("on_stage_snapshot", payload)
        elif name == "stage.load":
            config = payload.get("config")
            if isinstance(config, dict):
                self._state.config = dict(config)
            self._emit("on_stage_load", {"event": name, "payload": payload})
        elif name == "stage.log":
            self.stage_log.emit(payload)
            self._emit("on_stage_log", payload)

    # ------------------------------------------------------------------ utilities
    def send(self, method: str, payload: Any = None) -> None:
        data = json.dumps(payload if payload is not None else {})
        script = (
            "if (window.codexStage && typeof window.codexStage['{method}'] === 'function') "
            "{{ window.codexStage['{method}']({data}); }}".format(
                method=method, data=data
            )
        )
        logger.debug("Stage3D send -> %s payload=%s", method, payload)
        self.page().runJavaScript(script)

    def load_scene(self, config: Dict[str, Any]) -> None:
        payload = config or {}
        data = json.dumps(payload)
        script = (
            "if (window.codexStage) {{ "
            "const cfg = {data}; "
            "window.codexStage.loadScene(cfg); }}"
        ).format(data=data)
        logger.debug("Stage3D load_scene: %s", config)
        try:
            self._state.config = json.loads(data)
        except json.JSONDecodeError:
            self._state.config = dict(payload)
        self.page().runJavaScript(script)

    def request_snapshot(self, callback: Optional[Hook] = None) -> None:
        def _receive(result: Any) -> None:
            payload: Dict[str, Any]
            if isinstance(result, str):
                try:
                    payload = json.loads(result)
                except json.JSONDecodeError:
                    payload = {"raw": result}
            elif isinstance(result, dict):
                payload = result
            else:
                payload = {}

            if payload:
                self._state.payload = payload
                self.stage_snapshot.emit(payload)
                self._emit("on_stage_snapshot", payload)
            if callback:
                callback(payload)

        logger.debug("Stage3D snapshot requested")
        script = "window.codexStage ? window.codexStage.takeSnapshot() : ({})"
        self.page().runJavaScript(script, _receive)

    def last_snapshot(self) -> Dict[str, Any]:
        return dict(self._state.payload)

    def debug_state(self, callback: Optional[Hook] = None) -> None:
        def _receive(result: Any) -> None:
            data: Dict[str, Any] = {}
            if isinstance(result, str):
                try:
                    data = json.loads(result)
                except json.JSONDecodeError:
                    data = {"raw": result}
            elif isinstance(result, dict):
                data = result
            if data:
                self._state.debug = data
            if callback:
                callback(data)

        script = "window.codexStage ? window.codexStage.debugState() : ({});"
        logger.debug("Stage3D debug_state requested")
        self.page().runJavaScript(script, _receive)

    def configure_lights(self, entries: List[Dict[str, Any]]) -> None:
        self.send("configureLights", entries)

    def stage_info(self) -> Dict[str, Any]:
        info = dict(self._last_ready)
        info["snapshot"] = self.last_snapshot()
        if self._state.config:
            info["config"] = dict(self._state.config)
        if self._state.debug:
            info["debug"] = dict(self._state.debug)
        return info


__all__ = ["Stage3DView"]
