"""
Studio window prototype for ComfyVN.

Provides a lightweight toolbar hooked into the new /api/studio endpoints.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Mapping, Optional

from PySide6.QtCore import Qt, QTimer, Signal

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
from comfyvn.gui.views.metrics_dashboard import MetricsDashboard

logger = logging.getLogger(__name__)


class StudioWindow(QMainWindow):
    """Prototype Studio shell window using the new Studio REST endpoints."""

    autostart_completed = Signal(bool)
    manual_start_completed = Signal(bool)

    def __init__(self, bridge: ServerBridge | None = None):
        super().__init__()
        self.setWindowTitle("ComfyVN Studio Shell")
        self.resize(1280, 820)

        self.bridge = bridge or ServerBridge("http://127.0.0.1:8001")
        self.bridge.status_updated.connect(self._on_metrics)

        self._autostart_enabled = self._resolve_autostart_flag()
        self._autostart_base_delay = 3
        self._autostart_max_delay = 45
        self._autostart_step = 0
        self._autostart_inflight = False
        self._manual_start_in_progress = False
        self._autostart_timer = QTimer(self)
        self._autostart_timer.setSingleShot(True)
        self._autostart_timer.timeout.connect(self._attempt_autostart)
        self.autostart_completed.connect(self._on_autostart_complete)
        self.manual_start_completed.connect(self._on_manual_start_complete)

        self._current_project = "default"
        self._current_view = "Modules"

        self._init_toolbar()
        self._init_central()
        self._init_status()

        self.bridge.start_polling()
        if self._autostart_enabled:
            self._schedule_autostart(initial=True)

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

        self._dashboard = MetricsDashboard(self)
        layout.addWidget(self._dashboard)
        self._dashboard.set_manual_enabled(True)
        self._dashboard.start_button.clicked.connect(self._manual_start_server)
        if not self._autostart_enabled:
            self._dashboard.show_message("Autostart disabled. Use Start Embedded Server to launch the backend manually.")

        layout.addStretch(1)

        self.setCentralWidget(container)

    def _init_status(self) -> None:
        status = QStatusBar(self)
        self._status_indicator = QLabel(self)
        self._status_indicator.setTextFormat(Qt.RichText)
        self._status_indicator.setText(self._format_status_dot(False))
        self._status_indicator.setToolTip("Backend health indicator")
        status.addPermanentWidget(self._status_indicator, 0)

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
        if not isinstance(payload, dict):
            return

        ok = bool(payload.get("ok"))
        health_info = payload.get("health")
        if isinstance(health_info, Mapping):
            health_ok = bool(health_info.get("ok"))
        else:
            health_ok = False

        self._dashboard.update_metrics(payload if ok else None)
        self._dashboard.update_health(health_info if isinstance(health_info, Mapping) else None, fallback_ok=ok)
        self._update_status_indicator(health_ok or ok)
        self._update_metrics_label(payload if ok else None)

        if ok or health_ok:
            self._handle_server_online()
            return

        if self._autostart_enabled and not self._manual_start_in_progress:
            self._schedule_autostart()
        elif not self._autostart_enabled:
            self._dashboard.show_message("Backend offline. Use Start Embedded Server to launch the local backend.")
        self._dashboard.set_manual_enabled(not self._autostart_inflight and not self._manual_start_in_progress)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.bridge.stop_polling()
        logger.info("Studio window closed; polling stopped")
        super().closeEvent(event)
        if self._autostart_timer.isActive():
            self._autostart_timer.stop()

    # -----------------
    # Studio workflows
    # -----------------
    def new_project(self) -> None:
        """Placeholder stub for menu integration."""
        logger.info("New project requested from Studio shell (stub).")
        self._info_label.setText(
            "New project workflow is not yet available in the Studio shell.\n"
            "Switch to the main ComfyVN Studio for full project management."
        )

    # -----------------
    # Internal helpers
    # -----------------
    def _handle_server_online(self) -> None:
        if self._autostart_timer.isActive():
            self._autostart_timer.stop()
        self._dashboard.set_retry_message(0)
        self._dashboard.show_message(None)
        self._dashboard.set_manual_enabled(True)
        self._autostart_inflight = False
        self._manual_start_in_progress = False
        self._autostart_step = 0

    def _update_metrics_label(self, payload: Optional[Mapping[str, Any]]) -> None:
        if not payload:
            self._metrics_label.setText("Server metrics: offline")
            return
        cpu = self._bound_percent(payload.get("cpu"))
        mem = self._bound_percent(payload.get("mem"))
        disk = self._bound_percent(payload.get("disk"))
        gpus = payload.get("gpus")
        gpu_count = len(gpus) if isinstance(gpus, list) else 0
        self._metrics_label.setText(f"Server metrics — CPU {cpu}% • RAM {mem}% • Disk {disk}% • GPUs {gpu_count}")

    def _update_status_indicator(self, ok: bool) -> None:
        self._status_indicator.setText(self._format_status_dot(ok))
        self._status_indicator.setToolTip("Backend online" if ok else "Backend offline")

    @staticmethod
    def _bound_percent(value: Any) -> int:
        if isinstance(value, (int, float)):
            return max(0, min(100, int(round(value))))
        return 0

    @staticmethod
    def _format_status_dot(ok: bool) -> str:
        color = "#2ecc71" if ok else "#e74c3c"
        status = "●" if ok else "●"
        return f'<span style="color:{color};font-weight:600;">{status}</span>'

    def _schedule_autostart(self, *, initial: bool = False) -> None:
        if not self._autostart_enabled or self._autostart_inflight or self._manual_start_in_progress:
            return
        if self._autostart_timer.isActive() and not initial:
            return
        delay = 0 if initial else min(self._autostart_max_delay, self._autostart_base_delay * (2 ** self._autostart_step))
        self._dashboard.set_retry_message(delay)
        self._autostart_timer.start(max(0, int(delay * 1000)))

    def _attempt_autostart(self) -> None:
        if self._autostart_inflight or self._manual_start_in_progress:
            return
        self._autostart_inflight = True
        self._dashboard.show_message("Attempting to start embedded server…")
        self._dashboard.set_manual_enabled(False)

        def worker():
            ok = self.bridge.ensure_online(autostart=True, deadline=20.0)
            self.autostart_completed.emit(ok)

        threading.Thread(target=worker, daemon=True, name="StudioAutoStart").start()

    def _on_autostart_complete(self, ok: bool) -> None:
        self._autostart_inflight = False
        if ok:
            self._handle_server_online()
        else:
            self._dashboard.show_message("Embedded server did not report healthy status.")
            self._dashboard.set_manual_enabled(True)
            self._autostart_step = min(self._autostart_step + 1, 6)
            self._schedule_autostart()

    def _manual_start_server(self) -> None:
        if self._manual_start_in_progress:
            return
        self._manual_start_in_progress = True
        self._dashboard.show_message("Manual server start requested…")
        self._dashboard.set_manual_enabled(False)

        def worker():
            ok = self.bridge.ensure_online(autostart=True, deadline=25.0)
            self.manual_start_completed.emit(ok)

        threading.Thread(target=worker, daemon=True, name="StudioManualStart").start()

    def _on_manual_start_complete(self, ok: bool) -> None:
        self._manual_start_in_progress = False
        if ok:
            self._handle_server_online()
        else:
            self._dashboard.show_message("Manual start failed. Check logs and try again.")
            if self._autostart_enabled:
                self._schedule_autostart()
            else:
                self._dashboard.set_manual_enabled(True)

    @staticmethod
    def _resolve_autostart_flag() -> bool:
        env = os.getenv("COMFYVN_STUDIO_AUTOSTART", "1").strip().lower()
        return env not in {"0", "false", "off", "no"}
