from __future__ import annotations

import logging
import time

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

logger = logging.getLogger(__name__)


class SnapshotDefaultsDrawer(QWidget):
    def __init__(self, parent=None, api_base="http://127.0.0.1:8001"):
        super().__init__(parent)
        self.api_base = api_base.rstrip("/")

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(8)
        v.addWidget(QLabel("Snapshots Management", alignment=Qt.AlignLeft))

        self.combo_snaps = QComboBox()
        v.addWidget(self.combo_snaps)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Snapshots")
        self.btn_create = QPushButton("Create Snapshot")
        self.btn_restore = QPushButton("Restore Selected Snapshot")
        for b in (self.btn_refresh, self.btn_create, self.btn_restore):
            row.addWidget(b)
        v.addLayout(row)

        self.btn_refresh.clicked.connect(self.refresh_snapshots)
        self.btn_create.clicked.connect(self._create_snapshot)
        self.btn_restore.clicked.connect(self._restore_snapshot)

        self.refresh_snapshots()

    # ---- HTTP helpers ----
    def _get(self, path: str) -> dict:
        try:
            r = requests.get(self.api_base + path, timeout=3)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def _post(self, path: str, payload: dict) -> dict:
        try:
            r = requests.post(self.api_base + path, json=payload, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    # ---- actions ----
    def refresh_snapshots(self):
        data = self._get("/snapshot/list")
        self.combo_snaps.clear()
        for it in data.get("snapshots", []):
            self.combo_snaps.addItem(it.get("name", ""))
        if data.get("error"):
            QMessageBox.critical(self, "Snapshots", f"Error: {data['error']}")

    def _create_snapshot(self):
        ts = time.strftime("manual_%Y%m%d_%H%M%S")
        res = self._post("/snapshot/create", {"name": ts})
        if res.get("error"):
            QMessageBox.critical(self, "Snapshot", f"Error: {res['error']}")
        else:
            QMessageBox.information(self, "Snapshot", f"Created: {res.get('name', ts)}")
        self.refresh_snapshots()

    def _restore_snapshot(self):
        name = self.combo_snaps.currentText()
        if not name:
            QMessageBox.warning(self, "Snapshot", "Select a snapshot.")
            return
        if (
            QMessageBox.question(
                self,
                "Confirm",
                f"Restore '{name}'? This overwrites data/exports.",
                QMessageBox.Yes | QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        res = self._post("/snapshot/restore", {"snap_id": name, "overwrite": True})
        if res.get("error"):
            QMessageBox.critical(self, "Snapshot", f"Error: {res['error']}")
        else:
            QMessageBox.information(self, "Snapshot", f"Restored: {name}")
