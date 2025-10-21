from __future__ import annotations

import logging
from datetime import datetime

import requests
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.services.job_stream import JobStreamClient

LOGGER = logging.getLogger(__name__)


def _friendly_ts(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return value or ""


class JobsPanel(QWidget):
    def __init__(self, base: str = "http://127.0.0.1:8001"):
        super().__init__()
        self.base = base.rstrip("/")
        self.lbl = QLabel("Active Jobs")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Kind", "Status", "Updated"])
        self.table.horizontalHeader().setStretchLastSection(True)

        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl)
        lay.addWidget(self.table)

        self.jobs: dict[str, dict] = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

        self.stream = JobStreamClient(self.base, self)
        self.stream.event_received.connect(self._handle_event)
        self.stream.state_changed.connect(self._set_state)
        self.stream.start()

        self.refresh()

    # ------------------------------------------------------------------
    # Networking helpers
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self.stream.stop()
        super().closeEvent(event)

    def _get(self, path: str):
        try:
            r = requests.get(self.base + path, timeout=2)
            if r.status_code < 400:
                return r.json()
        except Exception:
            return None

    def refresh(self):
        data = self._get("/jobs/all") or {}
        jobs = data.get("jobs") or []
        if jobs:
            self._apply_snapshot(jobs)

    # ------------------------------------------------------------------
    # Stream handling
    # ------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state == "connected":
            self.lbl.setText("Active Jobs — live")
            self.lbl.setProperty("class", "status-ok")
            LOGGER.info("Jobs stream connected")
        elif state.startswith("error"):
            self.lbl.setText("Active Jobs — reconnecting…")
            self.lbl.setProperty("class", "status-warn")
            LOGGER.warning("Jobs stream error state: %s", state)
        elif state == "disconnected":
            self.lbl.setText("Active Jobs — disconnected")
            self.lbl.setProperty("class", "status-warn")
            LOGGER.info("Jobs stream disconnected")
        elif state == "connecting":
            self.lbl.setText("Active Jobs — connecting…")
            self.lbl.setProperty("class", "status-info")
            LOGGER.debug("Jobs stream connecting")
        self.lbl.style().unpolish(self.lbl)
        self.lbl.style().polish(self.lbl)

    def _handle_event(self, payload: dict) -> None:
        typ = payload.get("type")
        if typ == "snapshot":
            jobs = payload.get("jobs") or []
            self._apply_snapshot(jobs)
        elif typ == "job.update":
            job = payload.get("job")
            if job and job.get("id"):
                self.jobs[job["id"]] = job
                self._render_jobs()
                LOGGER.debug(
                    "Job update received: %s -> %s", job.get("id"), job.get("status")
                )

    def _apply_snapshot(self, jobs: list[dict]) -> None:
        self.jobs = {job["id"]: job for job in jobs if job.get("id")}
        self._render_jobs()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render_jobs(self) -> None:
        ordered = sorted(
            self.jobs.values(),
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )
        self.table.setRowCount(len(ordered))
        for row, job in enumerate(ordered):
            self.table.setItem(row, 0, QTableWidgetItem(job.get("id", "")))
            self.table.setItem(row, 1, QTableWidgetItem(job.get("kind", "")))
            self.table.setItem(row, 2, QTableWidgetItem(job.get("status", "")))
            ts = job.get("updated_at") or job.get("created_at")
            self.table.setItem(row, 3, QTableWidgetItem(_friendly_ts(ts)))
        if not ordered:
            self.lbl.setText("Active Jobs — idle")
