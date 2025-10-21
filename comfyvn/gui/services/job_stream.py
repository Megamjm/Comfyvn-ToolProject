from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket

LOGGER = logging.getLogger(__name__)


class JobStreamClient(QObject):
    """Reconnect-friendly websocket client for the /jobs/ws stream."""

    event_received = Signal(dict)
    state_changed = Signal(str)

    def __init__(
        self, base: str, parent: QObject | None = None, *, path: str = "/jobs/ws"
    ):
        super().__init__(parent)
        self.base = base.rstrip("/")
        self.path = path

        self.socket = QWebSocket()
        self.socket.textMessageReceived.connect(self._on_message)
        self.socket.errorOccurred.connect(self._on_error)
        self.socket.connected.connect(lambda: self.state_changed.emit("connected"))
        self.socket.disconnected.connect(self._schedule_reconnect)

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(5000)
        self.reconnect_timer.timeout.connect(self._open)

    def start(self) -> None:
        self.state_changed.emit("connecting")
        self._open()

    def stop(self) -> None:
        self.reconnect_timer.stop()
        if self.socket.state() != QAbstractSocket.UnconnectedState:
            self.socket.close()
        self.state_changed.emit("stopped")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _open(self) -> None:
        url = self._build_url()
        self.reconnect_timer.stop()
        LOGGER.debug("Job stream opening %s", url.toString())
        self.socket.open(url)

    def _schedule_reconnect(self) -> None:
        self.state_changed.emit("disconnected")
        if not self.reconnect_timer.isActive():
            self.reconnect_timer.start()
            LOGGER.warning(
                "Job stream disconnected; retrying in %ss",
                self.reconnect_timer.interval() / 1000,
            )

    def _build_url(self) -> QUrl:
        if self.base.startswith("https://"):
            scheme = "wss://"
            rest = self.base[len("https://") :]
        elif self.base.startswith("http://"):
            scheme = "ws://"
            rest = self.base[len("http://") :]
        else:
            scheme = "ws://"
            rest = self.base
        if not self.path.startswith("/"):
            stream_path = f"/{self.path}"
        else:
            stream_path = self.path
        return QUrl(f"{scheme}{rest}{stream_path}")

    def _on_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except Exception:
            LOGGER.debug("Job stream received non-JSON payload")
            return
        LOGGER.debug("Job stream event <- %s", payload.get("type"))
        self.event_received.emit(payload)

    def _on_error(self, error: QAbstractSocket.SocketError) -> None:
        self.state_changed.emit(f"error:{error}")
        self._schedule_reconnect()
        LOGGER.warning("Job stream error: %s", error)
