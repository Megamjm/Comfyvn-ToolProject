from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.services.server_bridge import ServerBridge


class PlaygroundPanel(QDockWidget):
    """Lightweight control surface for free-mode (“playground”) adjustments."""

    def __init__(self, bridge: ServerBridge):
        super().__init__("Playground")
        self.bridge = bridge
        self.setAllowedAreas(Qt.AllDockWidgetAreas)

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.state_view = QTextEdit(root)
        self.state_view.setReadOnly(True)
        self.state_view.setPlaceholderText("Active persona state will appear here…")

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh State", root)
        self.btn_playground = QPushButton("Enter Playground Mode", root)
        self.btn_vn = QPushButton("Return to VN Mode", root)
        self.btn_metrics = QPushButton("Fetch /system/metrics", root)
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_playground)
        btn_row.addWidget(self.btn_vn)
        btn_row.addWidget(self.btn_metrics)

        layout.addLayout(btn_row)
        layout.addWidget(QLabel("State / Metrics", root))
        layout.addWidget(self.state_view, 1)

        root.setLayout(layout)
        self.setWidget(root)

        self.btn_refresh.clicked.connect(self._refresh_state)
        self.btn_playground.clicked.connect(lambda: self._set_mode("playground"))
        self.btn_vn.clicked.connect(lambda: self._set_mode("vn"))
        self.btn_metrics.clicked.connect(self._fetch_metrics)

        self._refresh_state()

    # ------------------------------------------------------------------
    def _extract_payload(self, result: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict) or not result.get("ok"):
            error = (result or {}).get("error") if isinstance(result, dict) else "unknown error"
            self.state_view.setPlainText(f"⚠️ Request failed: {error}")
            return None
        payload = result.get("data")
        if not isinstance(payload, dict):
            self.state_view.setPlainText("⚠️ Unexpected server response format.")
            return None
        return payload

    def _refresh_state(self) -> None:
        payload = self._extract_payload(self.bridge.get_json("/player/state", timeout=5.0, default=None))
        if payload is None:
            return
        try:
            pretty = json.dumps(payload, indent=2, ensure_ascii=False)
        except Exception:
            pretty = str(payload)
        self.state_view.setPlainText(pretty)

    def _set_mode(self, mode: str) -> None:
        state = self._extract_payload(self.bridge.get_json("/player/state", timeout=5.0, default=None))
        persona_id = state.get("persona_id") if state else None
        payload: Dict[str, Any] = {"mode": mode}
        if persona_id:
            payload["persona"] = persona_id
        result = self.bridge.post_json("/player/select", payload, timeout=5.0, default=None)
        if self._extract_payload(result) is not None:
            self._refresh_state()

    def _fetch_metrics(self) -> None:
        result = self.bridge.get_json("/system/metrics", timeout=5.0, default=None)
        if not isinstance(result, dict) or not result.get("ok"):
            error = (result or {}).get("error") if isinstance(result, dict) else "unknown error"
            self.state_view.setPlainText(f"⚠️ Metrics request failed: {error}")
            return
        data = result.get("data")
        try:
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
        except Exception:
            pretty = str(data)
        self.state_view.setPlainText(pretty)


__all__ = ["PlaygroundPanel"]

