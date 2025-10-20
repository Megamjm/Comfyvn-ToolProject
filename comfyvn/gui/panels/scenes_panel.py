from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QLabel,
)

from comfyvn.studio.core.scene_registry import SceneRegistry


LOGGER = logging.getLogger(__name__)


class ScenesPanel(QWidget):
    """Minimal scene browser backed by the studio SceneRegistry."""

    def __init__(self, registry: SceneRegistry, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.registry = registry

        self.list_widget = QListWidget(self)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)

        header = QHBoxLayout()
        header.addWidget(refresh_btn)
        header.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.status_label)

        self.refresh()

    def set_registry(self, registry: SceneRegistry) -> None:
        LOGGER.info("ScenesPanel registry updated: %s", registry.project_id)
        self.registry = registry
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        try:
            scenes = self.registry.list_scenes()
        except Exception as exc:
            LOGGER.error("Failed to list scenes: %s", exc)
            self.status_label.setText(f"Error loading scenes: {exc}")
            return

        for scene in scenes:
            title = scene.get("title") or f"Scene {scene.get('id')}"
            self.list_widget.addItem(title)
        count = len(scenes)
        self.status_label.setText(f"Scenes loaded: {count}")

