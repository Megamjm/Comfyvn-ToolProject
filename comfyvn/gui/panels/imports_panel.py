from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import requests
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url

LOGGER = logging.getLogger(__name__)


class ImportsPanel(QWidget):
    """Displays recent importer jobs (VN/roleplay) using the task registry endpoints."""

    def __init__(self, base: str | None = None) -> None:
        super().__init__()
        self.base = (base or default_base_url()).rstrip("/")

        self.status_label = QLabel("Import Processing — loading", self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Kind", "Status", "Progress", "Message"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)

        open_btn = QPushButton("Open Summary", self)
        open_btn.clicked.connect(self.open_summary)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh_btn)
        buttons.addWidget(open_btn)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)

        self.jobs: List[dict] = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(6000)

        self.refresh()

    def _get(self, path: str) -> dict:
        try:
            response = requests.get(self.base + path, timeout=3)
            if response.status_code < 400:
                return response.json()
        except Exception as exc:
            LOGGER.warning("ImportProcessingPanel request failed: %s", exc)
        return {}

    def refresh(self) -> None:
        payload = self._get("/jobs/all")
        jobs = payload.get("jobs") or []
        filtered = [
            job
            for job in jobs
            if str(job.get("kind", "")).startswith("vn")
            or job.get("kind") in {"roleplay_import"}
        ]
        self.jobs = filtered
        self._render()

    def _render(self) -> None:
        self.table.setRowCount(len(self.jobs))
        for row, job in enumerate(self.jobs):
            self.table.setItem(row, 0, QTableWidgetItem(job.get("id", "")))
            self.table.setItem(row, 1, QTableWidgetItem(job.get("kind", "")))
            self.table.setItem(row, 2, QTableWidgetItem(job.get("status", "")))
            progress = job.get("progress")
            self.table.setItem(
                row,
                3,
                QTableWidgetItem(
                    f"{progress:.0%}" if isinstance(progress, float) else ""
                ),
            )
            self.table.setItem(row, 4, QTableWidgetItem(job.get("message", "")))

        if self.jobs:
            self.status_label.setText(
                f"Import Processing — tracking {len(self.jobs)} job(s)"
            )
        else:
            self.status_label.setText("Import Processing — idle")

    def open_summary(self) -> None:
        current_row = self.table.currentRow()
        if current_row < 0 or current_row >= len(self.jobs):
            QMessageBox.information(self, "Open Summary", "Select a job first.")
            return
        job = self.jobs[current_row]
        job_id = job.get("id")
        if not job_id:
            return
        detail = self._get(f"/vn/import/{job_id}")
        summary = detail.get("summary") or {}
        summary_path = summary.get("summary_path")
        if summary_path and Path(summary_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(summary_path))
        else:
            QMessageBox.information(
                self, "Open Summary", "Summary path unavailable; check server logs."
            )
