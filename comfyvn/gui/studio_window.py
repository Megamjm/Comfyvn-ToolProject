"""
Studio window prototype for ComfyVN.

Provides a lightweight toolbar hooked into the new /api/studio endpoints.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from typing import Any, Dict

from PySide6.QtWidgets import (
    QAction,
    QInputDialog,
    QLabel,
    QMainWindow,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.services.server_bridge import ServerBridge

logger = logging.getLogger(__name__)


class StudioWindow(QMainWindow):
    """Prototype Studio shell window using the new Studio REST endpoints."""

    def __init__(self, bridge: ServerBridge | None = None):
        super().__init__()
        self.setWindowTitle("ComfyVN Studio Shell")
        self.resize(1280, 820)

        self.bridge = bridge or ServerBridge("http://127.0.0.1:8001")
        self.bridge.status_updated.connect(self._on_metrics)
        self.bridge.start_polling()

        self._current_project = "default"
        self._current_view = "Modules"

        self._init_toolbar()
        self._init_central()
        self._init_status()

    def _init_toolbar(self) -> None:
        toolbar = QToolBar("Studio Controls")
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        self._project_action = QAction("Open Project…", self)
        self._project_action.triggered.connect(self._prompt_project)
        toolbar.addAction(self._project_action)

        self._view_action = QAction("Switch View…", self)
        self._view_action.triggered.connect(self._prompt_view)
        toolbar.addAction(self._view_action)

        self._export_action = QAction("Export Bundle…", self)
        self._export_action.triggered.connect(self._prompt_export)
        toolbar.addAction(self._export_action)

    def _init_central(self) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)

        self._info_label = QLabel(self)
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)
        self._info_label.setText(
            "Studio Shell ready.\n"
            "Use the toolbar to open a project, switch views, or export a bundle stub."
        )

        self.setCentralWidget(container)

    def _init_status(self) -> None:
        status = QStatusBar(self)
        self._metrics_label = QLabel("Server metrics: pending", self)
        status.addPermanentWidget(self._metrics_label, 1)
        self.setStatusBar(status)

    # -----------------
    # Toolbar handlers
    # -----------------
    def _prompt_project(self) -> None:
        text, ok = QInputDialog.getText(self, "Open Project", "Project ID:", text=self._current_project)
        if not ok or not text.strip():
            return
        project_id = text.strip()
        logger.info("Requesting project switch -> %s", project_id)
        self.bridge.post("/api/studio/open_project", {"project_id": project_id}, cb=self._on_project_opened)

    def _prompt_view(self) -> None:
        text, ok = QInputDialog.getText(self, "Switch View", "View name:", text=self._current_view)
        if not ok or not text.strip():
            return
        view = text.strip()
        logger.info("Requesting view switch -> %s", view)
        self.bridge.post("/api/studio/switch_view", {"view": view}, cb=self._on_view_switched)

    def _prompt_export(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Export Bundle",
            "Raw scene JSON path (optional).\nLeave blank to use sample payload.",
        )
        if not ok:
            return
        payload: dict
        if text.strip():
            payload = {"raw_path": text.strip()}
        else:
            payload = {
                "raw": {
                    "id": "studio-preview",
                    "dialogue": [
                        {"type": "line", "speaker": "Guide", "text": "Welcome to the Studio shell!"}
                    ],
                }
            }
        logger.info("Requesting bundle export")
        self.bridge.post("/api/studio/export_bundle", payload, cb=self._on_bundle_exported)

    # -----------------
    # Bridge callbacks
    # -----------------
    def _on_project_opened(self, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            logger.warning("Open project failed: %s", result)
            return
        self._current_project = result.get("project_id", self._current_project)
        self._info_label.setText(f"Active project: {self._current_project}\nActive view: {self._current_view}")
        logger.info("Active project set to %s", self._current_project)

    def _on_view_switched(self, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            logger.warning("Switch view failed: %s", result)
            return
        self._current_view = result.get("view", self._current_view)
        self._info_label.setText(f"Active project: {self._current_project}\nActive view: {self._current_view}")
        logger.info("Active view set to %s", self._current_view)

    def _on_bundle_exported(self, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            logger.warning("Bundle export failed: %s", result)
            return
        bundle_info = result.get("bundle", {})
        summary = bundle_info if isinstance(bundle_info, dict) else {"bundle": bundle_info}
        self._info_label.setText(
            f"Active project: {self._current_project}\n"
            f"Active view: {self._current_view}\n"
            f"Bundle export: {summary}"
        )
        logger.info("Bundle export result: %s", summary)

    def _on_metrics(self, payload: Dict[str, Any]) -> None:
        if not payload.get("ok"):
            self._metrics_label.setText("Server metrics: offline")
            return
        cpu = payload.get("cpu")
        mem = payload.get("mem")
        disk = payload.get("disk")
        gpus = len(payload.get("gpus", []))
        self._metrics_label.setText(f"Server metrics — CPU: {cpu}% • MEM: {mem}% • DISK: {disk}% • GPUs: {gpus}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.bridge.stop_polling()
        logger.info("Studio window closed; polling stopped")
        super().closeEvent(event)
