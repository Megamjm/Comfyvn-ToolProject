"""
Studio window prototype for ComfyVN.

Provides a lightweight toolbar hooked into the new /api/studio endpoints.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Mapping, Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAction,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.panels.characters_panel import CharactersPanel
from comfyvn.gui.panels.scenes_panel import ScenesPanel
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.gui.views import AssetSummaryView, ImportsJobsView, TimelineSummaryView
from comfyvn.gui.views.metrics_dashboard import MetricsDashboard
from comfyvn.studio.core.asset_registry import AssetRegistry
from comfyvn.studio.core.character_registry import CharacterRegistry
from comfyvn.studio.core.scene_registry import SceneRegistry
from comfyvn.studio.core.timeline_registry import TimelineRegistry

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
        self._current_view = "Scenes"

        self._scene_registry = SceneRegistry(project_id=self._current_project)
        self._character_registry = CharacterRegistry(project_id=self._current_project)
        self._timeline_registry = TimelineRegistry(project_id=self._current_project)
        self._asset_registry = AssetRegistry(project_id=self._current_project)
        self._info_default = "Use the navigation on the left to open Studio views."

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
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._info_label = QLabel(self)
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)
        self._info_extra = self._info_default

        content_row = QHBoxLayout()
        content_row.setSpacing(12)
        layout.addLayout(content_row, 1)

        self._nav = QListWidget(self)
        self._nav.setObjectName("studioNav")
        self._nav.setIconSize(QSize(20, 20))
        self._nav.setUniformItemSizes(True)
        self._nav.setSpacing(4)
        self._nav.setFixedWidth(180)
        content_row.addWidget(self._nav, 0)

        self._view_stack = QStackedWidget(self)
        content_row.addWidget(self._view_stack, 1)

        self._build_views()

        self._dashboard = MetricsDashboard(self)
        layout.addWidget(self._dashboard)
        self._dashboard.set_manual_enabled(True)
        self._dashboard.start_button.clicked.connect(self._manual_start_server)
        if not self._autostart_enabled:
            self._dashboard.show_message(
                "Autostart disabled. Use Start Embedded Server to launch the backend manually."
            )

        self._update_info_label()

        self.setCentralWidget(container)

    def _build_views(self) -> None:
        icons = {
            "Scenes": QStyle.SP_FileIcon,
            "Characters": QStyle.SP_FileDialogContentsView,
            "Timeline": QStyle.SP_DirOpenIcon,
            "Assets": QStyle.SP_DriveHDIcon,
            "Imports": QStyle.SP_BrowserReload,
        }

        self._scene_view = ScenesPanel(self._scene_registry, self)
        self._characters_view = CharactersPanel(self._character_registry, self)
        self._timeline_view = TimelineSummaryView(self._timeline_registry, self)
        self._asset_view = AssetSummaryView(self._asset_registry, self)
        self._imports_view = ImportsJobsView(self.bridge.base_url, self)

        self._view_map: dict[str, QWidget] = {
            "Scenes": self._scene_view,
            "Characters": self._characters_view,
            "Timeline": self._timeline_view,
            "Assets": self._asset_view,
            "Imports": self._imports_view,
        }
        self._view_order = list(self._view_map.keys())

        for name in self._view_order:
            icon = self.style().standardIcon(icons.get(name, QStyle.SP_FileIcon))
            item = QListWidgetItem(icon, name)
            self._nav.addItem(item)
            widget = self._view_map[name]
            self._view_stack.addWidget(widget)

        self._nav.currentRowChanged.connect(self._on_nav_changed)
        if self._view_order:
            self._nav.blockSignals(True)
            self._nav.setCurrentRow(0)
            self._nav.blockSignals(False)
            self._activate_view(self._view_order[0], notify_server=False)

    def _update_info_label(self) -> None:
        lines = [
            f"Active project: {self._current_project}",
            f"Active view: {self._current_view}",
        ]
        if getattr(self, "_info_extra", None):
            lines.append(self._info_extra)
        self._info_label.setText("\n".join(lines))

    def _set_info_extra(self, text: str | None) -> None:
        self._info_extra = text or self._info_default
        self._update_info_label()

    def _on_nav_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._view_order):
            return
        label = self._view_order[index]
        self._activate_view(label, notify_server=True)

    def _activate_view(self, label: str, *, notify_server: bool) -> None:
        widget = self._view_map.get(label)
        if widget is None:
            logger.debug("Unknown view requested: %s", label)
            return
        if self._view_stack.currentWidget() is not widget:
            self._view_stack.setCurrentWidget(widget)
        self._current_view = label
        self._refresh_view(label)
        if notify_server:
            self.bridge.post(
                "/api/studio/switch_view", {"view": label}, cb=self._on_view_switched
            )

    def _refresh_view(self, label: str) -> None:
        view = self._view_map.get(label)
        if view is None:
            return
        refresh = getattr(view, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:
                logger.warning("Refresh for view %s failed: %s", label, exc)
        self._update_info_label()

    def _select_view(self, label: str) -> None:
        widget = self._view_map.get(label)
        if widget is None:
            self._current_view = label
            self._update_info_label()
            return
        target_index = self._view_order.index(label)
        if self._nav.currentRow() != target_index:
            self._nav.blockSignals(True)
            self._nav.setCurrentRow(target_index)
            self._nav.blockSignals(False)
        self._view_stack.setCurrentWidget(widget)
        self._current_view = label
        self._refresh_view(label)

    def _reload_registries(self) -> None:
        logger.info("Reloading registries for project %s", self._current_project)
        self._scene_registry = SceneRegistry(project_id=self._current_project)
        self._character_registry = CharacterRegistry(project_id=self._current_project)
        self._timeline_registry = TimelineRegistry(project_id=self._current_project)
        self._asset_registry = AssetRegistry(project_id=self._current_project)

        self._scene_view.set_registry(self._scene_registry)
        self._characters_view.set_registry(self._character_registry)
        self._timeline_view.set_registry(self._timeline_registry)
        self._asset_view.set_registry(self._asset_registry)
        # Imports view is project-agnostic (jobs feed), so no changes needed.
        self._refresh_view(self._current_view)

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
        text, ok = QInputDialog.getText(
            self, "Open Project", "Project ID:", text=self._current_project
        )
        if not ok or not text.strip():
            return
        project_id = text.strip()
        logger.info("Requesting project switch -> %s", project_id)
        self.bridge.post(
            "/api/studio/open_project",
            {"project_id": project_id},
            cb=self._on_project_opened,
        )

    def _prompt_view(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Switch View", "View name:", text=self._current_view
        )
        if not ok or not text.strip():
            return
        view = text.strip()
        logger.info("Requesting view switch -> %s", view)
        self.bridge.post(
            "/api/studio/switch_view", {"view": view}, cb=self._on_view_switched
        )

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
                        {
                            "type": "line",
                            "speaker": "Guide",
                            "text": "Welcome to the Studio shell!",
                        }
                    ],
                }
            }
        logger.info("Requesting bundle export")
        self.bridge.post(
            "/api/studio/export_bundle", payload, cb=self._on_bundle_exported
        )

    # -----------------
    # Bridge callbacks
    # -----------------
    def _on_project_opened(self, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            logger.warning("Open project failed: %s", result)
            return
        project_id = result.get("project_id") or self._current_project
        self._current_project = project_id
        self._reload_registries()
        self._set_info_extra(f"Project ready: {project_id}")
        logger.info("Active project set to %s", self._current_project)

    def _on_view_switched(self, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            logger.warning("Switch view failed: %s", result)
            return
        view_name = result.get("view", self._current_view)
        self._select_view(view_name)
        logger.info("Active view set to %s", self._current_view)

    def _on_bundle_exported(self, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            logger.warning("Bundle export failed: %s", result)
            return
        bundle_info = result.get("bundle", {})
        summary = (
            bundle_info if isinstance(bundle_info, dict) else {"bundle": bundle_info}
        )
        summary_text = summary if isinstance(summary, str) else repr(summary)
        self._set_info_extra(f"Bundle export: {summary_text}")
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
        self._dashboard.update_health(
            health_info if isinstance(health_info, Mapping) else None, fallback_ok=ok
        )
        self._update_status_indicator(health_ok or ok)
        self._update_metrics_label(payload if ok else None)

        if ok or health_ok:
            self._handle_server_online()
            return

        if self._autostart_enabled and not self._manual_start_in_progress:
            self._schedule_autostart()
        elif not self._autostart_enabled:
            self._dashboard.show_message(
                "Backend offline. Use Start Embedded Server to launch the local backend."
            )
        self._dashboard.set_manual_enabled(
            not self._autostart_inflight and not self._manual_start_in_progress
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.bridge.stop_polling()
        logger.info("Studio window closed; polling stopped")
        if hasattr(self, "_imports_view"):
            try:
                self._imports_view.close()
            except Exception:
                logger.debug("Imports view close handling failed", exc_info=True)
        super().closeEvent(event)
        if self._autostart_timer.isActive():
            self._autostart_timer.stop()

    # -----------------
    # Studio workflows
    # -----------------
    def new_project(self) -> None:
        """Placeholder stub for menu integration."""
        logger.info("New project requested from Studio shell (stub).")
        self._set_info_extra(
            "New project workflow is not yet available in the Studio shell. "
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
        self._metrics_label.setText(
            f"Server metrics — CPU {cpu}% • RAM {mem}% • Disk {disk}% • GPUs {gpu_count}"
        )

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
        if (
            not self._autostart_enabled
            or self._autostart_inflight
            or self._manual_start_in_progress
        ):
            return
        if self._autostart_timer.isActive() and not initial:
            return
        delay = (
            0
            if initial
            else min(
                self._autostart_max_delay,
                self._autostart_base_delay * (2**self._autostart_step),
            )
        )
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
            self._dashboard.show_message(
                "Embedded server did not report healthy status."
            )
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
            self._dashboard.show_message(
                "Manual start failed. Check logs and try again."
            )
            if self._autostart_enabled:
                self._schedule_autostart()
            else:
                self._dashboard.set_manual_enabled(True)

    @staticmethod
    def _resolve_autostart_flag() -> bool:
        env = os.getenv("COMFYVN_STUDIO_AUTOSTART", "1").strip().lower()
        return env not in {"0", "false", "off", "no"}
