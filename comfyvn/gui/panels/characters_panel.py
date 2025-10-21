from __future__ import annotations

import json
import logging
from typing import Optional

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QVBoxLayout, QWidget)

from comfyvn.studio.core.character_registry import CharacterRegistry

LOGGER = logging.getLogger(__name__)


class CharactersPanel(QWidget):
    """Displays characters from the studio registry."""

    def __init__(
        self, registry: CharacterRegistry, parent: Optional[QWidget] = None
    ) -> None:
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

    def set_registry(self, registry: CharacterRegistry) -> None:
        LOGGER.info("CharactersPanel registry updated: %s", registry.project_id)
        self.registry = registry
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        try:
            characters = self.registry.list_characters()
        except Exception as exc:
            LOGGER.error("Failed to list characters: %s", exc)
            self.status_label.setText(f"Error loading characters: {exc}")
            return

        for char in characters:
            name = char.get("name") or f"Character {char.get('id')}"
            meta = char.get("meta")
            detail = ""
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if isinstance(meta, dict) and meta.get("origin"):
                detail = f" (origin: {meta['origin']})"
            self.list_widget.addItem(name + detail)
        count = len(characters)
        self.status_label.setText(f"Characters loaded: {count}")
