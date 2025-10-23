"""
Studio window prototype for ComfyVN.

Provides a lightweight toolbar hooked into the new /api/studio endpoints.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Mapping, Optional

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config import runtime_paths
from comfyvn.core.theme_manager import apply_theme
from comfyvn.gui.panels.advisory_panel import AdvisoryPanel
from comfyvn.gui.panels.debug_integrations import DebugIntegrationsPanel
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.gui.statusbar_metrics import StatusBarMetrics
from comfyvn.gui.studio_config import StudioConfig
from comfyvn.gui.views import (
    AssetSummaryView,
    AudioView,
    CharactersView,
    ComputeSummaryView,
    ExportStatusView,
    ImportsJobsView,
    ScenesView,
    TimelineView,
)
from comfyvn.gui.views.metrics_dashboard import MetricsDashboard
from comfyvn.gui.widgets.log_hub import LogHub
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

        self._config = StudioConfig()
        cfg_snapshot = self._config.load()
        layout_snapshot = cfg_snapshot.get("layout")
        self._layout_state = (
            dict(layout_snapshot) if isinstance(layout_snapshot, dict) else {}
        )
        host_override = cfg_snapshot.get("host")
        base_override = (
            host_override.strip()
            if isinstance(host_override, str) and host_override.strip()
            else None
        )

        if bridge is not None:
            self.bridge = bridge
            if base_override:
                try:
                    self.bridge.set_host(base_override)
                except Exception as exc:
                    logger.debug("Unable to apply stored host override: %s", exc)
        else:
            self.bridge = ServerBridge(base=base_override)
        self.bridge.status_updated.connect(self._on_metrics)
        self._active_base = self.bridge.base_url

        self._theme_preference = str(cfg_snapshot.get("theme") or "system")
        self._pending_view_label = (
            str(self._layout_state.get("current_view"))
            if isinstance(self._layout_state.get("current_view"), str)
            else None
        )
        if self._pending_view_label == "Import Processing":
            self._pending_view_label = "Imports / Jobs"
        self._apply_theme_preference()

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
        self._update_base_dependent_views()
        self._restore_layout_state()

        self._diagnostics_dialog: QDialog | None = None
        self._diagnostics_tabs: QTabWidget | None = None
        self._diagnostics_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self._diagnostics_shortcut.setContext(Qt.ApplicationShortcut)
        self._diagnostics_shortcut.activated.connect(self._open_diagnostics)

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

        self._build_views(initial_view=self._pending_view_label)

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

    def _build_views(self, *, initial_view: str | None = None) -> None:
        imports_label = "Imports / Jobs"
        icons = {
            "Scenes": QStyle.SP_FileIcon,
            "Characters": QStyle.SP_FileDialogContentsView,
            "Timeline": QStyle.SP_DirOpenIcon,
            "Assets": QStyle.SP_DriveHDIcon,
            imports_label: QStyle.SP_BrowserReload,
            "Compute": QStyle.SP_ComputerIcon,
            "Audio": QStyle.SP_MediaVolume,
            "Advisory": QStyle.SP_FileDialogDetailedView,
            "Export": QStyle.SP_DialogSaveButton,
            "Logs": QStyle.SP_FileDialogInfoView,
        }

        self._scene_view = ScenesView(self.bridge, self)
        self._characters_view = CharactersView(self.bridge, self)
        self._timeline_view = TimelineView(self.bridge, self)
        self._asset_view = AssetSummaryView(self._asset_registry, self)
        self._imports_view = ImportsJobsView(self.bridge.base_url, self)
        self._compute_view = ComputeSummaryView(self.bridge.base_url, self)
        self._audio_view = AudioView(parent=self)
        self._advisory_view = AdvisoryPanel(self.bridge.base_url)
        self._export_view = ExportStatusView(self.bridge, self)
        self._log_view = LogHub(runtime_paths.logs_dir(), parent=self)

        self._view_map: dict[str, QWidget] = {
            "Scenes": self._scene_view,
            "Characters": self._characters_view,
            "Timeline": self._timeline_view,
            "Assets": self._asset_view,
            imports_label: self._imports_view,
            "Compute": self._compute_view,
            "Audio": self._audio_view,
            "Advisory": self._advisory_view,
            "Export": self._export_view,
            "Logs": self._log_view,
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
            target_label = (
                initial_view if initial_view in self._view_map else self._view_order[0]
            )
            target_index = self._view_order.index(target_label)
            self._nav.blockSignals(True)
            self._nav.setCurrentRow(target_index)
            self._nav.blockSignals(False)
            self._activate_view(target_label, notify_server=False)

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

    def _remember_layout_state(self) -> None:
        if not isinstance(getattr(self, "_view_order", None), list):
            return
        layout = (
            dict(self._layout_state) if isinstance(self._layout_state, dict) else {}
        )
        layout["current_view"] = self._current_view
        if self._current_view in self._view_order:
            layout["nav_index"] = self._view_order.index(self._current_view)
        self._layout_state = layout

    def _update_base_dependent_views(self) -> None:
        base = self.bridge.base_url.rstrip("/")
        if not base or getattr(self, "_active_base", None) == base:
            return
        self._active_base = base
        if hasattr(self, "_metrics_display"):
            self._metrics_display.set_base_url(base)
        if hasattr(self, "_imports_view"):
            self._imports_view.set_base_url(base)
        if hasattr(self, "_compute_view"):
            self._compute_view.set_base_url(base)
        if hasattr(self, "_advisory_view"):
            self._advisory_view.set_base_url(base)
        if hasattr(self, "_export_view"):
            self._export_view.set_base_url(base)

    def _restore_layout_state(self) -> None:
        if not isinstance(self._layout_state, dict):
            self._layout_state = {}
            return
        geometry_blob = self._layout_state.get("geometry")
        state_blob = self._layout_state.get("window_state")
        geometry = self._decode_bytes(geometry_blob)
        if geometry:
            try:
                self.restoreGeometry(geometry)
            except Exception as exc:
                logger.debug("Unable to restore studio geometry: %s", exc)
        window_state = self._decode_bytes(state_blob)
        if window_state:
            try:
                self.restoreState(window_state)
            except Exception as exc:
                logger.debug("Unable to restore studio window state: %s", exc)

    def _persist_config(self) -> None:
        if not hasattr(self, "_config"):
            return
        layout = (
            dict(self._layout_state) if isinstance(self._layout_state, dict) else {}
        )
        layout["current_view"] = self._current_view
        if hasattr(self, "_view_order") and self._current_view in self._view_order:
            layout["nav_index"] = self._view_order.index(self._current_view)
        geometry = self._encode_bytes(self.saveGeometry())
        if geometry:
            layout["geometry"] = geometry
        window_state = self._encode_bytes(self.saveState())
        if window_state:
            layout["window_state"] = window_state
        self._layout_state = layout
        try:
            self._config.update(
                host=self.bridge.base_url,
                theme=self._theme_preference,
                layout=layout,
            )
        except Exception as exc:
            logger.debug("Failed to persist studio config: %s", exc)

    def _apply_theme_preference(self) -> None:
        theme = (self._theme_preference or "").strip()
        if theme.lower() in {"", "system"}:
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            apply_theme(app, theme)
        except Exception as exc:
            logger.warning("Unable to apply theme %s: %s", theme, exc)

    def _open_diagnostics(self) -> None:
        dialog = self._diagnostics_dialog
        if dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Studio Diagnostics")
            dialog.resize(900, 600)
            container = QVBoxLayout(dialog)
            tabs = QTabWidget(dialog)
            compute_panel = DebugIntegrationsPanel(self.bridge.base_url, tabs)
            logs_panel = LogHub(runtime_paths.logs_dir(), tabs)
            tabs.addTab(compute_panel, "Compute")
            tabs.addTab(logs_panel, "Logs")
            container.addWidget(tabs)
            close_button = QPushButton("Close", dialog)
            close_button.clicked.connect(dialog.close)
            container.addWidget(close_button, alignment=Qt.AlignRight)
            dialog.setLayout(container)
            self._diagnostics_dialog = dialog
            self._diagnostics_tabs = tabs
        else:
            tabs = self._diagnostics_tabs
            if tabs is not None:
                compute_widget = tabs.widget(0)
                if hasattr(compute_widget, "refresh"):
                    try:
                        compute_widget.refresh()
                    except Exception:
                        logger.debug(
                            "Diagnostics compute refresh failed", exc_info=True
                        )
                logs_widget = tabs.widget(1)
                if hasattr(logs_widget, "refresh"):
                    try:
                        logs_widget.refresh()
                    except Exception:
                        logger.debug("Diagnostics log refresh failed", exc_info=True)
        dialog = self._diagnostics_dialog
        if dialog is not None:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

    @staticmethod
    def _encode_bytes(blob: QByteArray | bytes | bytearray | None) -> str | None:
        if isinstance(blob, QByteArray):
            encoded = blob.toBase64()
        elif isinstance(blob, (bytes, bytearray)):
            encoded = QByteArray(blob).toBase64()
        else:
            return None
        return bytes(encoded).decode("ascii")

    @staticmethod
    def _decode_bytes(value: object) -> QByteArray | None:
        if isinstance(value, QByteArray):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return QByteArray.fromBase64(value.encode("ascii"))
            except Exception:
                return None
        return None

    def _on_nav_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._view_order):
            return
        label = self._view_order[index]
        self._activate_view(label, notify_server=True)
        self._remember_layout_state()

    def _activate_view(self, label: str, *, notify_server: bool) -> None:
        widget = self._view_map.get(label)
        if widget is None:
            logger.debug("Unknown view requested: %s", label)
            return
        if self._view_stack.currentWidget() is not widget:
            self._view_stack.setCurrentWidget(widget)
        self._current_view = label
        self._refresh_view(label)
        self._remember_layout_state()
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
        self._remember_layout_state()

    def _reload_registries(self) -> None:
        logger.info("Reloading registries for project %s", self._current_project)
        self._scene_registry = SceneRegistry(project_id=self._current_project)
        self._character_registry = CharacterRegistry(project_id=self._current_project)
        self._timeline_registry = TimelineRegistry(project_id=self._current_project)
        self._asset_registry = AssetRegistry(project_id=self._current_project)

        if hasattr(self._scene_view, "set_registry"):
            self._scene_view.set_registry(self._scene_registry)
        if hasattr(self._characters_view, "set_registry"):
            self._characters_view.set_registry(self._character_registry)
        if hasattr(self._timeline_view, "set_registry"):
            self._timeline_view.set_registry(self._timeline_registry)
        if hasattr(self._asset_view, "set_registry"):
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

        self._metrics_display = StatusBarMetrics(self.bridge.base_url, parent=self)
        status.addPermanentWidget(self._metrics_display.widget, 1)
        self._metrics_display.start()
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
        if hasattr(self, "_metrics_display"):
            self._metrics_display.update_payload(
                payload if isinstance(payload, dict) else None
            )

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
        self._update_base_dependent_views()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.bridge.stop_polling()
        logger.info("Studio window closed; polling stopped")
        if hasattr(self, "_imports_view"):
            try:
                self._imports_view.close()
            except Exception:
                logger.debug("Imports view close handling failed", exc_info=True)
        self._persist_config()
        super().closeEvent(event)
        if self._autostart_timer.isActive():
            self._autostart_timer.stop()
        if hasattr(self, "_metrics_display"):
            self._metrics_display.stop()

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
        self._update_base_dependent_views()

    def _update_status_indicator(self, ok: bool) -> None:
        self._status_indicator.setText(self._format_status_dot(ok))
        self._status_indicator.setToolTip("Backend online" if ok else "Backend offline")

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
