from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import httpx
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication, QTextOption
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass
class PanelAction:
    label: str
    method: str
    path: str
    description: str = ""
    payload: Any = None


class _RequestWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        base_url: str,
        method: str,
        path: str,
        payload: Any,
        timeout: float = 15.0,
    ) -> None:
        super().__init__()
        self.base_url = base_url.rstrip("/") + "/"
        self.method = method.upper()
        self.path = path.strip()
        self.payload = payload
        self.timeout = timeout

    def run(self) -> None:
        url = urljoin(self.base_url, self.path.lstrip("/"))
        request_kwargs: Dict[str, Any] = {
            "method": self.method,
            "url": url,
            "timeout": self.timeout,
        }
        if self.method not in {"GET", "HEAD"} and self.payload is not None:
            request_kwargs["json"] = self.payload

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(**request_kwargs)
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        try:
            data = response.json()
        except Exception:
            data = response.text

        payload = {
            "url": url,
            "status": response.status_code,
            "headers": dict(response.headers),
            "json": data if isinstance(data, (dict, list)) else None,
            "text": response.text if isinstance(data, (dict, list)) else str(data),
        }
        self.finished.emit(payload)


class JsonEndpointPanel(QWidget):
    """Reusable JSON endpoint tester used by the Live Fix panels."""

    def __init__(
        self,
        base_url: str,
        *,
        title: str,
        description: str,
        actions: Optional[Iterable[PanelAction]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url.rstrip("/")
        self._threads: List[QThread] = []
        self.setWindowTitle(title)
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)

        self._desc_label = QLabel(textwrap.dedent(description).strip())
        self._desc_label.setWordWrap(True)
        self._desc_label.setObjectName("json-endpoint-description")
        root.addWidget(self._desc_label)

        self._action_box = None
        actions_list = list(actions or [])
        if actions_list:
            self._action_box = QComboBox()
            for action in actions_list:
                self._action_box.addItem(action.label, action)
            self._action_box.currentIndexChanged.connect(self._populate_from_action)
            root.addWidget(self._action_box)

        form = QFormLayout()
        self._method = QComboBox()
        for verb in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            self._method.addItem(verb)
        form.addRow("Method", self._method)

        self._path = QLineEdit("/health")
        self._path.setPlaceholderText("/api/... or relative path")
        form.addRow("Path", self._path)
        root.addLayout(form)

        controls = QHBoxLayout()
        self._load_file_button = QPushButton("Load From File…")
        self._load_file_button.clicked.connect(self._load_payload_from_file)
        controls.addWidget(self._load_file_button)

        self._load_button = QPushButton("Send Request")
        self._load_button.clicked.connect(self._send_request)
        controls.addWidget(self._load_button)

        self._copy_url_button = QPushButton("Copy URL")
        self._copy_url_button.clicked.connect(self._copy_full_url)
        controls.addWidget(self._copy_url_button)
        controls.addStretch(1)
        root.addLayout(controls)

        self._payload = QPlainTextEdit()
        self._payload.setPlaceholderText('{\n  "example": true\n}')
        self._payload.document().setDefaultFont(self.font())
        self._payload.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._payload.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self._payload.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._payload.setFixedHeight(140)
        root.addWidget(self._payload)

        self._status = QLabel("Ready")
        root.addWidget(self._status)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setWordWrapMode(QTextOption.NoWrap)
        root.addWidget(self._output, 1)

        if actions_list:
            self._populate_from_action(0)

    # ─────────────────────────────
    # UI helpers
    # ─────────────────────────────
    def _populate_from_action(self, index: int) -> None:
        if self._action_box is None:
            return
        action = self._action_box.itemData(index)
        if not isinstance(action, PanelAction):
            return
        self._method.setCurrentText(action.method.upper())
        self._path.setText(action.path)
        payload = action.payload
        if payload is None:
            self._payload.clear()
        else:
            try:
                self._payload.setPlainText(
                    json.dumps(payload, indent=2, ensure_ascii=False)
                )
            except Exception:
                self._payload.setPlainText(str(payload))
        if action.description:
            self._status.setText(action.description)

    def select_action(self, label: Optional[str]) -> None:
        if not label or self._action_box is None:
            return
        index = self._action_box.findText(label)
        if index >= 0:
            self._action_box.setCurrentIndex(index)

    def _copy_full_url(self) -> None:
        url = urljoin(
            self._base_url.rstrip("/") + "/", self._path.text().strip().lstrip("/")
        )
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(url)

    def _load_payload_from_file(self) -> None:
        start_dir = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Request Payload",
            start_dir,
            "JSON Files (*.json *.jsonl *.txt);;All Files (*)",
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Load Payload", f"Failed to read file:\n{exc}")
            return

        try:
            payload = json.loads(text)
            formatted = json.dumps(payload, indent=2, ensure_ascii=False)
        except Exception:
            formatted = text
        self._payload.setPlainText(formatted)
        self._status.setText(f"Loaded payload from {path}")

    def _send_request(self) -> None:
        path = self._path.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing path", "Enter an endpoint path.")
            return

        body_text = self._payload.toPlainText().strip()
        payload: Any = None
        if body_text:
            try:
                payload = json.loads(body_text)
            except json.JSONDecodeError as exc:
                QMessageBox.warning(
                    self,
                    "Invalid JSON",
                    f"Failed to parse request payload: {exc}",
                )
                return

        worker = _RequestWorker(
            self._base_url,
            self._method.currentText(),
            path,
            payload,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_finished)
        worker.failed.connect(self._handle_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_threads)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        self._status.setText(f"{self._method.currentText()} {path} — requesting…")
        self._load_button.setEnabled(False)
        thread.start()

    def _handle_finished(self, payload: Dict[str, Any]) -> None:
        self._load_button.setEnabled(True)
        status = payload.get("status")
        url = payload.get("url")
        self._status.setText(f"HTTP {status} — {url}")
        if payload.get("json") is not None:
            try:
                text = json.dumps(payload["json"], indent=2, ensure_ascii=False)
            except Exception:
                text = str(payload["json"])
        else:
            text = str(payload.get("text", ""))
        self._output.setPlainText(text)

    def _handle_failed(self, message: str) -> None:
        self._load_button.setEnabled(True)
        self._status.setText(f"Request failed: {message}")
        self._output.setPlainText(message)

    def _cleanup_threads(self) -> None:
        alive = []
        for thread in self._threads:
            if thread.isRunning():
                alive.append(thread)
        self._threads = alive
