from __future__ import annotations

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.services.server_bridge import ServerBridge

LOGGER = logging.getLogger(__name__)


class TimelineView(QWidget):
    """
    Read-only timeline browser that inspects payloads from `/api/timelines`.

    Lists timelines by name and renders the raw JSON of the selected entry in
    the inspector. Provides a mock fallback when the endpoint is missing so the
    GUI maintains parity with the other Studio views during development.
    """

    def __init__(
        self,
        api_client: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api = api_client or ServerBridge()
        self._items: list[dict[str, Any]] = []

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)

        self.detail = QTextEdit(self)
        self.detail.setObjectName("timelineDetailInspector")
        self.detail.setReadOnly(True)
        self.detail.setLineWrapMode(QTextEdit.NoWrap)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        self._refresh_button = QPushButton("Refresh", self)
        self._refresh_button.clicked.connect(self.refresh)

        actions_row = QHBoxLayout()
        actions_row.addStretch(1)
        actions_row.addWidget(self._refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(actions_row)

        split_row = QHBoxLayout()
        split_row.addWidget(self.list_widget, 1)
        split_row.addWidget(self.detail, 2)
        layout.addLayout(split_row, 1)
        layout.addWidget(self.status_label)

        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Reload timelines from the backend or use mock data."""
        self._refresh_button.setEnabled(False)
        try:
            items, source = self._load_items()
        finally:
            self._refresh_button.setEnabled(True)

        self._items = items
        self.list_widget.clear()
        for index, item in enumerate(items):
            label = self._format_label(item, index)
            widget_item = QListWidgetItem(label)
            widget_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(widget_item)

        if items:
            self.list_widget.setCurrentRow(0)
            self.status_label.setText(f"Loaded {len(items)} timeline(s) from {source}.")
        else:
            self.detail.setPlainText("No timelines available.")
            self.status_label.setText("No timelines available.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_items(self) -> tuple[list[dict[str, Any]], str]:
        try:
            response = self.api.get_json("/api/timelines", timeout=4.0, default=None)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("TimelineView API error: %s", exc)
            return self._mock_items(), "mock data"

        if not isinstance(response, dict):
            return self._mock_items(), "mock data"

        status = response.get("status")
        if status == 404:
            return self._mock_items(), "mock data"

        payload = response.get("data")
        items = self._extract_items(payload or response)
        if response.get("ok") and items is not None:
            return items, "server"

        if items is None:
            if response.get("ok"):
                return [], "server"
            return self._mock_items(), "mock data"
        return items, "server"

    def _extract_items(self, payload: Any) -> Optional[list[dict[str, Any]]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "data", "results", "rows", "timelines"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            values = list(payload.values())
            if values and all(isinstance(it, dict) for it in values):
                return [it for it in values if isinstance(it, dict)]
        return None

    def _mock_items(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "timeline-main",
                "name": "Main Narrative",
                "scene_order": [
                    {"scene_id": "scene-prologue", "title": "Prologue"},
                    {"scene_id": "scene-market", "title": "Morning at the Bazaar"},
                    {"scene_id": "scene-confrontation", "title": "Courtyard Clash"},
                ],
                "meta": {"branching": "A/B/C"},
            },
            {
                "id": "timeline-side",
                "name": "Character Spotlight — Rin",
                "scene_order": [
                    {"scene_id": "scene-rin-01", "title": "Rin's Resolve"},
                    {"scene_id": "scene-rin-02", "title": "Echoes in the Alley"},
                ],
            },
        ]

    def _format_label(self, item: dict[str, Any], index: int) -> str:
        name = (
            str(item.get("name"))
            or str(item.get("title"))
            or str(item.get("id"))
            or f"Timeline {index + 1}"
        )
        scene_count = len(item.get("scene_order") or [])
        if scene_count:
            return f"{name} — {scene_count} scene(s)"
        return name

    def _on_selection_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._items):
            self.detail.setPlainText("Select a timeline to inspect its JSON payload.")
            return
        item = self._items[index]
        serialized = json.dumps(item, indent=2, sort_keys=True)
        self.detail.setPlainText(serialized)
