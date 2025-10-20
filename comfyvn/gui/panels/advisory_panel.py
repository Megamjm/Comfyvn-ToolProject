from __future__ import annotations

import logging
from typing import Optional

import requests
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QComboBox,
)


LOGGER = logging.getLogger(__name__)


class AdvisoryPanel(QWidget):
    """Displays advisory scan results using `/api/advisory/logs`."""

    def __init__(self, base: str = "http://127.0.0.1:8001") -> None:
        super().__init__()
        self.base = base.rstrip("/")

        self.filter_box = QComboBox(self)
        self.filter_box.addItems(["All", "Unresolved", "Resolved"])
        self.filter_box.currentIndexChanged.connect(self.refresh)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(self.filter_box)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Target", "Severity", "Message", "Resolved"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.status_label = QLabel("Advisory scans", self)
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)

        self.refresh()

    def _get(self, resolved: Optional[bool]) -> dict:
        params = {}
        if resolved is not None:
            params["resolved"] = "true" if resolved else "false"
        try:
            resp = requests.get(self.base + "/api/advisory/logs", params=params, timeout=3)
            if resp.status_code < 400:
                return resp.json()
            LOGGER.warning("Advisory logs request failed: %s %s", resp.status_code, resp.text)
        except Exception as exc:
            LOGGER.error("Advisory logs request error: %s", exc)
        return {}

    def refresh(self) -> None:
        index = self.filter_box.currentIndex()
        resolved_filter = None
        if index == 1:
            resolved_filter = False
        elif index == 2:
            resolved_filter = True

        payload = self._get(resolved_filter)
        items = payload.get("items") or []
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(item.get("issue_id", "")))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("target_id", "")))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("severity", "")))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("message", "")))
            self.table.setItem(row, 4, QTableWidgetItem(str(item.get("resolved", False))))

        self.status_label.setText(f"Advisory entries: {len(items)}")

