from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from comfyvn.accessibility import AccessibilityState, accessibility_manager
from comfyvn.accessibility.filters import FilterOverlay
from comfyvn.accessibility.input_map import input_map_manager
from comfyvn.accessibility.subtitles import SubtitleOverlay
from comfyvn.gui.services.server_bridge import ServerBridge

LOGGER = logging.getLogger(__name__)


class VNViewer(QWidget):
    """Central Ren'Py viewer pane with optional window embedding."""

    def __init__(
        self,
        api_client: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api = api_client or ServerBridge()
        self._project_path: Optional[Path] = None
        self._project_id: Optional[str] = None
        self._is_running = False
        self._poll_inflight = False
        self._accessibility_token: Optional[str] = None
        self._embedded_window: Optional[QWindow] = None
        self._window_container: Optional[QWidget] = None
        self._current_window_id: Optional[int] = None
        self._build_ui()

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2500)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start()
        accessibility_manager.ensure_applied()
        self._accessibility_token = accessibility_manager.subscribe(
            self._on_accessibility_changed
        )
        self.destroyed.connect(self._on_destroyed)
        self._register_input_bindings()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Visual Novel Viewer")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        self._status_label = QLabel("waiting for project")
        layout.addWidget(self._status_label)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        layout.addLayout(controls)

        self._start_button = QPushButton("Start Visual Novel")
        self._start_button.clicked.connect(self._start)
        self._start_button.setEnabled(False)
        controls.addWidget(self._start_button)

        self._stop_button = QPushButton("Stop")
        self._stop_button.clicked.connect(self._stop)
        self._stop_button.setEnabled(False)
        controls.addWidget(self._stop_button)
        controls.addStretch(1)

        self._details_label = QLabel(
            "Open a project to launch the Ren'Py viewer. "
            "When running, the window will embed here if supported."
        )
        self._details_label.setWordWrap(True)
        layout.addWidget(self._details_label)

        self._embed_frame = QFrame(self)
        self._embed_frame.setFrameShape(QFrame.StyledPanel)
        self._embed_frame.setMinimumHeight(360)
        self._embed_layout = QVBoxLayout(self._embed_frame)
        self._embed_layout.setContentsMargins(0, 0, 0, 0)
        self._embed_layout.setSpacing(0)
        layout.addWidget(self._embed_frame, 1)

        self._placeholder = QLabel(
            "Waiting to embed Ren'Py output.\n"
            "Start a project to preview the visual novel."
        )
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet("color: #888;")
        self._embed_layout.addWidget(self._placeholder, 1)

        self._filter_overlay = FilterOverlay(self._embed_frame)
        self._subtitle_overlay = SubtitleOverlay(self._embed_frame)
        self._embed_frame.installEventFilter(self)
        self._filter_overlay.hide()
        self._subtitle_overlay.hide()
        self._sync_overlays_geometry()

        layout.addStretch(0)

    # ---------------------------------------------------------- Public API --
    def set_project(
        self, project_path: Optional[Path], project_id: Optional[str] = None
    ) -> None:
        """Update the active project reference reflected in the viewer."""
        if project_path:
            self._project_path = Path(project_path)
            self._project_id = project_id or self._project_path.name
            self._status_label.setText(f"Project ready: {self._project_id}")
            self._start_button.setEnabled(True)
        else:
            self._project_path = None
            self._project_id = None
            if self._is_running:
                self._details_label.setText(
                    "Project closed. Stop the viewer to free resources."
                )
            else:
                self._details_label.setText(
                    "Open a project to launch the Ren'Py viewer."
                )
                self._placeholder.setText(
                    "Waiting to embed Ren'Py output.\n"
                    "Start the viewer to preview scenes."
                )
                self._status_label.setText("waiting for project")
            self._start_button.setEnabled(False)

    def show_message(self, text: str) -> None:
        """Show an informational message under the controls."""
        self._details_label.setText(text)

    def stop_viewer(self) -> None:
        """Expose stop action so the main window can stop the viewer."""
        self._stop()

    # ----------------------------------------------------------- Lifecycle --
    def _on_destroyed(self, *_args: object) -> None:
        if self._accessibility_token:
            accessibility_manager.unsubscribe(self._accessibility_token)
            self._accessibility_token = None
        try:
            input_map_manager.unregister_widget(self)
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Failed to unregister input map for viewer", exc_info=True)

    def _on_accessibility_changed(self, state: AccessibilityState) -> None:
        if hasattr(self, "_filter_overlay"):
            self._filter_overlay.set_filter(state.color_filter)
            self._filter_overlay.raise_()
        if hasattr(self, "_subtitle_overlay"):
            self._subtitle_overlay.update_state(
                enabled=state.subtitles_enabled,
                text=state.subtitle_text,
                font_scale=state.font_scale,
                origin=state.subtitle_origin,
            )
            self._subtitle_overlay.raise_()
        self._sync_overlays_geometry()

    def _register_input_bindings(self) -> None:
        try:
            input_map_manager.register_widget(
                self,
                {
                    "viewer.advance": lambda: self._handle_input_action(
                        "viewer.advance"
                    ),
                    "viewer.back": lambda: self._handle_input_action("viewer.back"),
                    "viewer.skip": lambda: self._handle_input_action("viewer.skip"),
                    "viewer.menu": lambda: self._handle_input_action("viewer.menu"),
                },
            )
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Viewer input binding registration failed", exc_info=True)

    def _handle_input_action(self, action: str) -> None:
        source = input_map_manager.current_source() or "local"
        label_map = {
            "viewer.advance": "Advance / Continue",
            "viewer.back": "Backlog / Previous",
            "viewer.skip": "Toggle Skip",
            "viewer.menu": "Viewer Menu",
        }
        label = label_map.get(action, action)
        self._details_label.setText(f"Input: {label} ({source})")
        if source != "api":
            try:
                self.api.post(
                    "/api/accessibility/input/event",
                    {"action": action, "source": "viewer"},
                )
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Failed to publish viewer input event", exc_info=True)
        if action == "viewer.advance":
            accessibility_manager.push_subtitle("Advance", origin="Input", ttl=1.5)
        elif action == "viewer.back":
            accessibility_manager.push_subtitle("Backlog", origin="Input", ttl=1.5)
        elif action == "viewer.menu":
            accessibility_manager.push_subtitle("Menu toggle", origin="Input", ttl=2.0)

    def _sync_overlays_geometry(self) -> None:
        frame = getattr(self, "_embed_frame", None)
        if frame is None:
            return
        rect = frame.rect()
        if hasattr(self, "_filter_overlay"):
            self._filter_overlay.setGeometry(rect)
        if hasattr(self, "_subtitle_overlay"):
            self._subtitle_overlay.setGeometry(rect)
            self._subtitle_overlay.raise_()

    def _poll_status(self) -> None:
        if self._poll_inflight:
            return
        self._poll_inflight = True
        self.api.get_json(
            "/api/viewer/status", cb=self._on_status_response, timeout=3.0
        )

    def _on_status_response(self, result: dict[str, Any]) -> None:
        QTimer.singleShot(
            0,
            functools.partial(self._process_status_result, result),
        )

    def _process_status_result(self, result: dict[str, Any]) -> None:
        self._poll_inflight = False
        if not isinstance(result, dict):
            return
        if not result.get("ok"):
            error = (
                result.get("error")
                or (result.get("data") if isinstance(result.get("data"), str) else None)
                or "Viewer status unavailable"
            )
            self._status_label.setText("viewer offline")
            self._stop_button.setEnabled(False)
            self._details_label.setText(str(error))
            return
        payload = result.get("data")
        if isinstance(payload, dict):
            self._update_from_status(payload)

    def _start(self) -> None:
        if not self._project_path:
            self._details_label.setText("Select or open a project before starting.")
            return
        payload = {
            "project_path": str(self._project_path),
        }
        if self._project_id:
            payload["project_id"] = self._project_id

        response = self.api.post("/api/viewer/start", payload)
        self._process_action_response(response, action="start")

    def _stop(self) -> None:
        self._stop_button.setEnabled(False)
        response = self.api.post("/api/viewer/stop", {})
        self._process_action_response(response, action="stop")

    def _process_action_response(
        self, response: dict[str, Any], *, action: str
    ) -> None:
        if not isinstance(response, dict):
            self._details_label.setText(f"{action.title()} failed: invalid response.")
            return
        if not response.get("ok"):
            error = (
                response.get("error")
                or (
                    response.get("data")
                    if isinstance(response.get("data"), str)
                    else None
                )
                or f"{action.title()} failed."
            )
            self._details_label.setText(str(error))
            if action == "start":
                self._start_button.setEnabled(bool(self._project_path))
            elif action == "stop":
                self._stop_button.setEnabled(True)
            return
        payload = response.get("data")
        if isinstance(payload, dict):
            self._update_from_status(payload)

    # -------------------------------------------------------------- Status --
    def _update_from_status(self, data: dict[str, Any]) -> None:
        running = bool(data.get("running"))
        mode = str(data.get("mode") or "unknown")
        project_id = data.get("project_id") or self._project_id
        if project_id:
            self._project_id = project_id

        lines: list[str] = []
        if project_id:
            lines.append(f"Project: {project_id}")
        if running:
            lines.append(f"Status: running ({mode})")
        else:
            lines.append("Status: idle")
        stub_reason = data.get("stub_reason")
        if stub_reason:
            lines.append(str(stub_reason))
        embed_fail = data.get("embed_fail_reason")
        log_path = data.get("log_path")
        if log_path:
            lines.append(f"Log file: {log_path}")

        window_id = data.get("window_id")
        if running and isinstance(window_id, int) and window_id > 0:
            self._attach_window(window_id)
            lines.append("Viewer embedded in the workspace.")
        else:
            self._detach_window()
            if running:
                message = (
                    f"Embedding not available ({embed_fail})."
                    if embed_fail
                    else "Viewer running in external window."
                )
            else:
                message = (
                    "Waiting to embed Ren'Py output.\n"
                    "Start the viewer to preview scenes."
                )
            self._placeholder.setText(message)

        self._details_label.setText("\n".join(lines))

        if running:
            self._status_label.setText("visual novel running")
            self._start_button.setEnabled(False)
            self._stop_button.setEnabled(True)
        else:
            self._status_label.setText(
                "waiting for project"
                if not self._project_path
                else "ready — launch the visual novel"
            )
            self._start_button.setEnabled(bool(self._project_path))
            self._stop_button.setEnabled(False)
        self._is_running = running

    # -------------------------------------------------------------- Embed --
    def _attach_window(self, window_id: int) -> None:
        if self._current_window_id == window_id:
            return
        self._detach_window()
        try:
            window = QWindow.fromWinId(window_id)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to embed window %s: %s", window_id, exc)
            self._placeholder.setText("Embedding failed; using external window.")
            return
        container = QWidget.createWindowContainer(window, self._embed_frame)
        container.setFocusPolicy(Qt.StrongFocus)
        self._embed_layout.addWidget(container, 1)
        self._placeholder.hide()
        self._embedded_window = window
        self._window_container = container
        self._current_window_id = window_id
        self._sync_overlays_geometry()
        if hasattr(self, "_filter_overlay"):
            self._filter_overlay.raise_()
        if hasattr(self, "_subtitle_overlay"):
            self._subtitle_overlay.raise_()

    def _detach_window(self) -> None:
        if self._window_container:
            self._embed_layout.removeWidget(self._window_container)
            self._window_container.deleteLater()
            self._window_container = None
        if self._embedded_window:
            self._embedded_window = None
        self._current_window_id = None
        self._placeholder.show()
        self._sync_overlays_geometry()

    # -------------------------------------------------------------- Events --
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is getattr(self, "_embed_frame", None) and event.type() == QEvent.Resize:
            self._sync_overlays_geometry()
        return QWidget.eventFilter(self, obj, event)
