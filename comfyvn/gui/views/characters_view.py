from __future__ import annotations

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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


class CharactersView(QWidget):
    """
    Read-only view of character records sourced from the Studio REST API.

    Shows a selectable list with a JSON inspector so narrative designers can
    quickly confirm payloads without leaving the GUI. Falls back to a small
    set of mock characters when `/api/characters` is not yet live.
    """

    def __init__(
        self,
        api_client: Optional[ServerBridge] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.api = api_client or ServerBridge()
        self._items: list[dict[str, Any]] = []
        self._last_raw_payload: Any | None = None
        self._raw_mode = False

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)

        self.detail = QTextEdit(self)
        self.detail.setObjectName("charactersDetailInspector")
        self.detail.setReadOnly(True)
        self.detail.setLineWrapMode(QTextEdit.NoWrap)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        self._refresh_button = QPushButton("Refresh", self)
        self._refresh_button.clicked.connect(self.refresh)

        self.raw_toggle = QCheckBox("Show raw response", self)
        self.raw_toggle.stateChanged.connect(
            lambda state: self._set_raw_mode(state == Qt.Checked)
        )

        actions_row = QHBoxLayout()
        actions_row.addWidget(self.raw_toggle)
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
        """Reload characters from the backend or mock fallback."""
        self._refresh_button.setEnabled(False)
        try:
            items, source = self._load_items()
        finally:
            self._refresh_button.setEnabled(True)

        self._items = items
        if source != "server":
            self._last_raw_payload = {"source": source, "items": items}
        self.list_widget.clear()
        for index, item in enumerate(items):
            label = self._format_label(item, index)
            widget_item = QListWidgetItem(label)
            widget_item.setData(Qt.UserRole, item)
            self.list_widget.addItem(widget_item)

        if items:
            self.list_widget.setCurrentRow(0)
            self.status_label.setText(
                f"Loaded {len(items)} character(s) from {source}."
            )
        else:
            self.detail.setPlainText("No characters available.")
            self.status_label.setText("No characters available.")

        if self._raw_mode:
            self.detail.setPlainText(self._raw_payload_text())

    def _set_raw_mode(self, enabled: bool) -> None:
        if self._raw_mode == enabled:
            return
        self._raw_mode = enabled
        if enabled:
            self.detail.setPlainText(self._raw_payload_text())
        else:
            self._on_selection_changed(self.list_widget.currentRow())

    def _raw_payload_text(self) -> str:
        payload = self._last_raw_payload
        if payload is None:
            return "No response captured yet."
        try:
            return json.dumps(payload, indent=2, sort_keys=True)
        except TypeError:
            return repr(payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_items(self) -> tuple[list[dict[str, Any]], str]:
        try:
            response = self.api.get_json("/api/characters", timeout=4.0, default=None)
            self._last_raw_payload = response
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("CharactersView API error: %s", exc)
            self._last_raw_payload = {"ok": False, "error": str(exc)}
            return self._mock_items(), "mock data"

        if not isinstance(response, dict):
            self._last_raw_payload = response
            return self._mock_items(), "mock data"

        status = response.get("status")
        if status == 404:
            self._last_raw_payload = response
            return self._mock_items(), "mock data"

        payload = response.get("data")
        items = self._extract_items(payload or response)
        if response.get("ok") and items is not None:
            return items, "server"

        if items is None:
            if response.get("ok"):
                return [], "server"
            self._last_raw_payload = response
            return self._mock_items(), "mock data"
        return items, "server"

    def _extract_items(self, payload: Any) -> Optional[list[dict[str, Any]]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "data", "results", "rows", "characters"):
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
                "id": "char-hero",
                "name": "Aiko",
                "role": "Protagonist",
                "mood": "Curious",
                "voice": "light_friendly",
            },
            {
                "id": "char-mentor",
                "name": "Haru",
                "role": "Mentor",
                "mood": "Calm",
                "voice": "deep_resonant",
            },
            {
                "id": "char-rival",
                "name": "Rin",
                "role": "Rival",
                "mood": "Impatient",
                "voice": "sharp_confident",
            },
        ]

    def _format_label(self, item: dict[str, Any], index: int) -> str:
        name = (
            str(item.get("name"))
            or str(item.get("display_name"))
            or str(item.get("id"))
            or f"Character {index + 1}"
        )
        role = item.get("role")
        if role:
            return f"{name} — {role}"
        return name

    def _on_selection_changed(self, index: int) -> None:
        if self._raw_mode:
            self.detail.setPlainText(self._raw_payload_text())
            return
        if index < 0 or index >= len(self._items):
            self.detail.setPlainText("Select a character to inspect its JSON payload.")
            return
        item = self._items[index]
        serialized = json.dumps(item, indent=2, sort_keys=True)
        self.detail.setPlainText(serialized)
