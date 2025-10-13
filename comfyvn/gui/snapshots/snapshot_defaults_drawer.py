# comfyvn/gui/snapshots/snapshot_defaults_drawer.py
# Snapshot drawer (list/create/restore) used by SettingsUI
# COMFYVN Architect

import threading, time
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QMessageBox,
)
from PySide6.QtCore import Qt
import requests


class SnapshotDefaultsDrawer(QWidget):
    def __init__(self, parent=None, api_base="http://127.0.0.1:8000"):
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
        row.addWidget(self.btn_refresh)
        row.addWidget(self.btn_create)
        row.addWidget(self.btn_restore)
        v.addLayout(row)

        self.btn_refresh.clicked.connect(self.refresh_snapshots)
        self.btn_create.clicked.connect(self._create_snapshot)
        self.btn_restore.clicked.connect(self._restore_snapshot)

        self.refresh_snapshots()

    # ---- HTTP helpers ----
    def _get(self, path: str) -> dict:
        try:
            r = requests.get(self.api_base + path, timeout=15)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def _post(self, path: str, payload: dict) -> dict:
        try:
            r = requests.post(self.api_base + path, json=payload, timeout=60)
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
