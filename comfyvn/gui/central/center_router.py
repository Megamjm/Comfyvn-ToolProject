from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config import feature_flags
from comfyvn.core import session_manager
from comfyvn.core.notifier import notifier
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.studio.core import CharacterRegistry

from .character_designer import CharacterDesigner
from .chat_panel import VNChatPanel
from .playground_view import PlaygroundView
from .vn_viewer import VNViewer

logger = logging.getLogger(__name__)


class CenterRouter(QTabWidget):
    """Central hub that tracks view state, feature flags, and quick actions."""

    def __init__(
        self,
        bridge: Optional[ServerBridge] = None,
        character_registry: Optional[CharacterRegistry] = None,
        *,
        open_assets: Optional[Callable[[], None]] = None,
        open_timeline: Optional[Callable[[], None]] = None,
        open_logs: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StudioCenterRouter")
        self.bridge = bridge or ServerBridge()
        self._character_registry = character_registry or CharacterRegistry()
        self._open_assets = open_assets
        self._open_timeline = open_timeline
        self._open_logs = open_logs

        self._viewer = VNViewer(api_client=self.bridge, parent=self)
        self._chat_panel = VNChatPanel(api_client=self.bridge, parent=self)
        self._chat_panel.setVisible(False)

        viewer_container = QWidget(self)
        viewer_layout = QVBoxLayout(viewer_container)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(0)
        viewer_layout.addWidget(self._viewer, 1)
        viewer_layout.addWidget(self._chat_panel, 0)

        self._designer = CharacterDesigner(api_client=self.bridge, parent=self)
        self._playground: Optional[PlaygroundView] = None
        self._playground_label = "Playground"

        self._views = {
            "VN Viewer": viewer_container,
            "Character Designer": self._designer,
        }

        for label, widget in self._views.items():
            self.addTab(widget, label)

        self.currentChanged.connect(self._on_current_changed)
        self._feature_flags = feature_flags.load_feature_flags()
        self._feature_label: Optional[QLabel] = None
        self._project_path: Optional[Path] = None
        self._project_id: Optional[str] = None
        self._forced_project_default = False

        self._build_corner_widget()
        notifier.attach(self._handle_notifier_event)
        self._ensure_playground_view(initial=True)
        self._restore_last_space()
        self._apply_features()

    # ------------------------------------------------------------------ API
    def activate(self, label: str) -> None:
        widget = self._views.get(label)
        if widget is not None:
            self.setCurrentWidget(widget)

    def viewer_widget(self) -> VNViewer:
        return self._viewer

    def designer_widget(self) -> CharacterDesigner:
        return self._designer

    def set_project_context(
        self, project_path: Optional[Path], project_id: Optional[str] = None
    ) -> None:
        self._project_path = Path(project_path) if project_path else None
        self._project_id = project_id
        self._viewer.set_project(self._project_path, project_id=project_id)
        if self._project_path is None:
            # Reset default selection heuristic when the project closes.
            self._forced_project_default = False
            self._designer.status_label.setText(
                "No project selected. Character saves will land in the default data directory."
            )
        else:
            if not self._forced_project_default:
                self.activate("VN Viewer")
                self._forced_project_default = True
            self._designer.refresh()

    # ------------------------------------------------------------------ internals
    def _restore_last_space(self) -> None:
        target = None
        try:
            state = session_manager.load()
            if isinstance(state, dict):
                target = state.get("last_space")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Unable to load session state for center router: %s", exc)

        if target not in self._views:
            target = "VN Viewer"
        self.activate(target)

    def _build_corner_widget(self) -> None:
        corner = QWidget(self)
        layout = QHBoxLayout(corner)
        layout.setContentsMargins(0, 4, 6, 0)
        layout.setSpacing(6)

        for label, handler in (
            ("Assets", self._open_assets),
            ("Timeline", self._open_timeline),
            ("Logs", self._open_logs),
        ):
            if handler is None:
                continue
            btn = QToolButton(corner)
            btn.setObjectName(f"CenterRouter{label}Button")
            btn.setText(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.clicked.connect(handler)
            layout.addWidget(btn)

        self._feature_label = QLabel(corner)
        self._feature_label.setObjectName("CenterRouterFeatureLabel")
        self._feature_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(self._feature_label)
        self.setCornerWidget(corner, Qt.TopRightCorner)

    def _apply_features(self) -> None:
        narrator_enabled = bool(self._feature_flags.get("enable_narrator_mode"))
        if narrator_enabled:
            self._chat_panel.setVisible(True)
        else:
            if hasattr(self._chat_panel, "_reset_narrator"):
                self._chat_panel._reset_narrator()  # type: ignore[attr-defined]
            self._chat_panel.setVisible(False)

        badges = []
        if self._feature_flags.get("enable_comfy_preview_stream"):
            badges.append("Preview")
        if self._feature_flags.get("enable_sillytavern_bridge"):
            badges.append("ST Bridge")
        if narrator_enabled:
            badges.append("Narrator")

        if self._feature_label is not None:
            text = " • ".join(badges)
            self._feature_label.setText(text)
            self._feature_label.setVisible(bool(text))
        self._ensure_playground_view()

    def _handle_notifier_event(self, event: dict) -> None:
        meta = event.get("meta")
        if not isinstance(meta, dict):
            return
        flags = meta.get("feature_flags")
        if not isinstance(flags, dict):
            return

        changed = False
        for key, value in flags.items():
            if isinstance(value, bool) and self._feature_flags.get(key) != value:
                self._feature_flags[key] = value
                changed = True
        if changed:
            self._apply_features()

    def _on_current_changed(self, index: int) -> None:
        widget = self.widget(index)
        label = self.tabText(index)
        try:
            session_manager.remember_space(label)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to persist center router state: %s", exc)

    # ------------------------------------------------------------------ playground plumbing
    def _ensure_playground_view(self, *, initial: bool = False) -> None:
        enabled = bool(self._feature_flags.get("enable_playground"))
        if enabled and self._playground is None:
            self._playground = PlaygroundView(parent=self)
            self._playground.register_hook(
                "on_stage_snapshot", self._handle_playground_snapshot
            )
            self._playground.register_hook("on_stage_log", self._handle_playground_log)
            self._views[self._playground_label] = self._playground
            self.addTab(self._playground, self._playground_label)
            logger.info("Playground view enabled via feature flag.")
            if not initial:
                self.activate(self._playground_label)
        elif not enabled and self._playground is not None:
            idx = self.indexOf(self._playground)
            if idx != -1:
                self.removeTab(idx)
            self._views.pop(self._playground_label, None)
            self._playground.deleteLater()
            self._playground = None
            logger.info("Playground view disabled via feature flag.")

    def _handle_playground_snapshot(self, payload: Dict[str, Any]) -> None:
        path = payload.get("path")
        logger.info("Playground snapshot captured: %s", path or payload.get("workflow"))

    def _handle_playground_log(self, payload: Dict[str, Any]) -> None:
        level = (payload or {}).get("level", "info")
        message = (payload or {}).get("message", "")
        detail = (payload or {}).get("detail")
        log_line = f"[Playground] {message}"
        if detail:
            log_line = f"{log_line} ({detail})"
        if level == "warning":
            logger.warning(log_line)
        elif level == "error":
            logger.error(log_line)
        else:
            logger.info(log_line)

        if self.currentWidget() is self._designer:
            current_id = self._designer.id_edit.text().strip() or None
            self._designer.refresh(select_id=current_id)
