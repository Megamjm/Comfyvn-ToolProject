from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url
from comfyvn.presentation.directives import PresentationNode, SceneState


class PresentationPlanPreview(QWidget):
    """Non-blocking preview widget that displays compiled presentation plans."""

    plan_ready = Signal(int, dict)
    error_ready = Signal(int, str)

    def __init__(self, base_url: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._base_url = (base_url or default_base_url()).rstrip("/")
        self._plan_endpoint = f"{self._base_url}/api/presentation/plan"
        self._request_lock = threading.Lock()
        self._seq_counter = 0
        self._active_seq = 0
        self._last_payload: dict[str, Any] | None = None

        self._status = QLabel("Plan preview idle.")
        self._status.setObjectName("presentationPlanStatus")
        self._status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.clicked.connect(self._refresh_clicked)

        header = QHBoxLayout()
        title = QLabel("<b>Directive Plan Preview</b>")
        header.addWidget(title, alignment=Qt.AlignLeft)
        header.addStretch()
        header.addWidget(self._refresh_btn, alignment=Qt.AlignRight)

        top = QVBoxLayout()
        top.addLayout(header)
        top.addWidget(self._status)

        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setMinimumHeight(220)
        self._editor.setObjectName("presentationPlanEditor")
        self._editor.setPlaceholderText("Directive plan will appear here.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(top)
        layout.addWidget(self._editor, stretch=1)

        self.plan_ready.connect(self._apply_plan)
        self.error_ready.connect(self._apply_error)

    # ------------------------------------------------------------------ API
    def set_base_url(self, base_url: str) -> None:
        clean = base_url.rstrip("/")
        if not clean:
            return
        self._base_url = clean
        self._plan_endpoint = f"{clean}/api/presentation/plan"
        self._status.setText(f"Server endpoint set to {self._plan_endpoint}")

    def show_idle(self, message: str = "Plan preview idle.") -> None:
        self._last_payload = None
        self._editor.setPlainText("")
        self._status.setText(message)
        self._refresh_btn.setEnabled(False)

    def update_plan(
        self,
        scene_state: SceneState | dict[str, Any],
        node: PresentationNode | dict[str, Any],
    ) -> None:
        payload = {
            "scene_state": _model_dump(scene_state),
            "node": _model_dump(node),
        }
        self._last_payload = payload
        self._status.setText("Compiling directive plan…")
        self._refresh_btn.setEnabled(False)
        self._spawn_request(payload)

    # ----------------------------------------------------------------- slots
    def _refresh_clicked(self) -> None:
        if not self._last_payload:
            return
        self._status.setText("Refreshing directive plan…")
        self._refresh_btn.setEnabled(False)
        self._spawn_request(dict(self._last_payload))

    def _apply_plan(self, seq: int, data: dict[str, Any]) -> None:
        if seq != self._active_seq:
            return
        plan = data.get("plan", [])
        meta = data.get("meta", {})
        timestamp = time.strftime("%H:%M:%S")
        self._editor.setPlainText(json.dumps(plan, indent=2, sort_keys=True))
        count = meta.get("count", len(plan))
        self._status.setText(f"{count} directives • Updated {timestamp}")
        self._refresh_btn.setEnabled(True)

    def _apply_error(self, seq: int, message: str) -> None:
        if seq != self._active_seq:
            return
        self._editor.setPlainText("")
        self._status.setText(f"Plan request failed: {message}")
        self._refresh_btn.setEnabled(True)

    # ------------------------------------------------------------- internals
    def _spawn_request(self, payload: dict[str, Any]) -> None:
        with self._request_lock:
            self._seq_counter += 1
            seq = self._seq_counter
            self._active_seq = seq

        def worker() -> None:
            try:
                response = _post_json(self._plan_endpoint, payload)
            except Exception as exc:
                self.error_ready.emit(seq, str(exc))
                return
            if response.get("ok") is False and response.get("error"):
                self.error_ready.emit(seq, str(response["error"]))
                return
            if "plan" not in response:
                self.error_ready.emit(seq, "Malformed response from server.")
                return
            self.plan_ready.emit(seq, response)

        threading.Thread(
            target=worker, daemon=True, name=f"PresentationPlanRequest#{seq}"
        ).start()


def _model_dump(obj: SceneState | PresentationNode | dict[str, Any]) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Unsupported payload type: {type(obj)!r}")


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=4.0) as client:
        response = client.post(url, json=payload)
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:  # pragma: no cover - defensive fallback
            detail = response.text
        message = detail.get("detail") if isinstance(detail, dict) else detail
        return {"ok": False, "error": message or f"HTTP {response.status_code}"}
    try:
        data = response.json()
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise RuntimeError(f"Invalid JSON from server: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Server returned non-object payload.")
    data.setdefault("ok", True)
    return data


__all__ = ["PresentationPlanPreview"]
