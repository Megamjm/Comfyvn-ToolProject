from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QGroupBox, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from comfyvn.gui.services.job_stream import JobStreamClient
from comfyvn.studio.core.asset_registry import AssetRegistry
from comfyvn.studio.core.timeline_registry import TimelineRegistry

LOGGER = logging.getLogger(__name__)


class TimelineSummaryView(QWidget):
    """Compact timeline browser showing names and ordered scene lists."""

    def __init__(
        self, registry: TimelineRegistry, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self._timelines: list[dict] = []

        self.list_widget = QListWidget(self)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        self.detail = QPlainTextEdit(self)
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(160)
        self.detail.setFrameShape(QFrame.StyledPanel)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)

        header = QHBoxLayout()
        header.addWidget(QLabel("Timelines", self))
        header.addStretch(1)
        header.addWidget(refresh_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(header)

        content = QHBoxLayout()
        content.addWidget(self.list_widget, 1)
        content.addWidget(self.detail, 2)
        layout.addLayout(content, 1)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.refresh()

    def set_registry(self, registry: TimelineRegistry) -> None:
        LOGGER.info("TimelineSummaryView registry updated: %s", registry.project_id)
        self.registry = registry
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        self.detail.clear()
        try:
            self._timelines = self.registry.list_timelines()
        except Exception as exc:
            LOGGER.error("Failed to list timelines: %s", exc)
            self.status_label.setText(f"Error loading timelines: {exc}")
            self._timelines = []
            return

        for timeline in self._timelines:
            name = timeline.get("name") or f"Timeline {timeline.get('id')}"
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, timeline.get("id"))
            self.list_widget.addItem(item)
        count = len(self._timelines)
        self.status_label.setText(f"Timelines loaded: {count}")
        if count:
            self.list_widget.setCurrentRow(0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _on_row_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._timelines):
            self.detail.clear()
            return
        timeline = self._timelines[index]
        sequence = timeline.get("scene_order") or []
        lines = [f"Timeline: {timeline.get('name', 'Untitled')}"]
        if timeline.get("meta"):
            lines.append(f"Meta: {timeline['meta']}")
        if not sequence:
            lines.append("Sequence: (empty)")
        else:
            lines.append("Sequence:")
            for idx, entry in enumerate(sequence, start=1):
                scene_id = entry.get("scene_id", "?")
                title = entry.get("title") or entry.get("name") or ""
                lines.append(f"  {idx}. Scene {scene_id} {title}")
        self.detail.setPlainText("\n".join(lines))


class AssetSummaryView(QWidget):
    """Lightweight asset table for quick inspection of registry rows."""

    def __init__(
        self, registry: AssetRegistry, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self._assets: list[dict] = []

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["UID", "Type", "Size (KB)", "Path"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)

        header = QHBoxLayout()
        header.addWidget(QLabel("Assets", self))
        header.addStretch(1)
        header.addWidget(refresh_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)

        self.refresh()

    def set_registry(self, registry: AssetRegistry) -> None:
        LOGGER.info("AssetSummaryView registry updated: %s", registry.project_id)
        self.registry = registry
        self.refresh()

    def refresh(self) -> None:
        try:
            assets = self.registry.list_assets()
        except Exception as exc:
            LOGGER.error("Failed to list assets: %s", exc)
            self.status_label.setText(f"Error loading assets: {exc}")
            self.table.setRowCount(0)
            self._assets = []
            return

        self._assets = assets[:50]
        self.table.setRowCount(len(self._assets))
        for row, asset in enumerate(self._assets):
            uid = asset.get("uid") or f"asset-{asset.get('id')}"
            typ = asset.get("type") or "-"
            size_bytes = asset.get("bytes") or 0
            size_kb = f"{size_bytes / 1024:.1f}" if size_bytes else "-"
            path = asset.get("path_full") or ""

            self.table.setItem(row, 0, QTableWidgetItem(uid))
            self.table.setItem(row, 1, QTableWidgetItem(str(typ)))
            self.table.setItem(row, 2, QTableWidgetItem(size_kb))
            self.table.setItem(row, 3, QTableWidgetItem(path))

        if self._assets:
            msg = f"Showing {len(self._assets)} of {len(assets)} assets."
        else:
            msg = "No assets indexed yet."
        self.status_label.setText(msg)


class ImportsJobsView(QWidget):
    """Shows importer jobs grouped by status using the jobs websocket feed."""

    def __init__(self, base_url: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.jobs: Dict[str, dict] = {}

        self.status_label = QLabel("Imports — connecting…", self)
        self.status_label.setWordWrap(True)

        self.queued_list = self._make_bucket_list("Queued", "Imports waiting to run.")
        self.active_list = self._make_bucket_list(
            "Active", "Imports currently in progress."
        )
        self.done_list = self._make_bucket_list("Done", "Completed or failed imports.")

        buckets_row = QHBoxLayout()
        buckets_row.addWidget(self.queued_list["frame"], 1)
        buckets_row.addWidget(self.active_list["frame"], 1)
        buckets_row.addWidget(self.done_list["frame"], 1)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self._request_snapshot)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addLayout(buckets_row)
        layout.addWidget(refresh_btn, alignment=Qt.AlignRight)

        self.stream = JobStreamClient(self.base_url, self)
        self.stream.event_received.connect(self._handle_event)
        self.stream.state_changed.connect(self._set_state)
        self.stream.start()

        # Periodic safety net to refresh if the stream stalls.
        self._fallback_timer = QTimer(self)
        self._fallback_timer.setInterval(15000)
        self._fallback_timer.timeout.connect(self._request_snapshot)
        self._fallback_timer.start()

    # ------------------------------------------------------------------
    # Qt lifecycle
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stream.stop()
        self._fallback_timer.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Networking helpers
    # ------------------------------------------------------------------
    def _request_snapshot(self) -> None:
        try:
            response = requests.get(f"{self.base_url}/jobs/all", timeout=3)
        except Exception as exc:
            LOGGER.debug("Imports snapshot request failed: %s", exc)
            return
        if response.status_code >= 400:
            return
        try:
            payload = response.json()
        except Exception:
            return
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if isinstance(jobs, list):
            self._apply_snapshot(jobs)

    # ------------------------------------------------------------------
    # Stream handling
    # ------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state == "connected":
            self.status_label.setText("Imports — live updates")
            LOGGER.info("Imports job stream connected")
        elif state.startswith("error"):
            self.status_label.setText("Imports — reconnecting…")
            LOGGER.warning("Imports job stream error: %s", state)
        elif state == "disconnected":
            self.status_label.setText("Imports — disconnected, retrying…")
            LOGGER.info("Imports job stream disconnected")
        elif state == "connecting":
            self.status_label.setText("Imports — connecting…")

    def _handle_event(self, payload: dict) -> None:
        typ = payload.get("type")
        if typ == "snapshot":
            jobs = payload.get("jobs") or []
            self._apply_snapshot(jobs)
        elif typ == "job.update":
            job = payload.get("job")
            if job and self._is_import_job(job):
                job_id = str(job.get("id"))
                if job_id:
                    self.jobs[job_id] = job
                    self._render()

    def _apply_snapshot(self, jobs: Iterable[dict]) -> None:
        filtered = {}
        for job in jobs:
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("id") or "")
            if not job_id or not self._is_import_job(job):
                continue
            filtered[job_id] = job
        self.jobs = filtered
        self._render()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def _render(self) -> None:
        buckets = {"queued": [], "active": [], "done": []}
        for job in self.jobs.values():
            bucket = self._map_status(job.get("status"))
            buckets[bucket].append(job)

        for bucket_name, holder in (
            ("queued", self.queued_list),
            ("active", self.active_list),
            ("done", self.done_list),
        ):
            items = sorted(
                buckets[bucket_name],
                key=lambda job: job.get("created_at") or job.get("updated_at") or "",
                reverse=True,
            )
            self._hydrate_bucket(holder["list"], holder["label"], items)

    def _hydrate_bucket(
        self, widget: QListWidget, label: QLabel, jobs: List[dict]
    ) -> None:
        widget.clear()
        for job in jobs:
            job_id = job.get("id", "")
            status = job.get("status", "")
            message = job.get("message") or job.get("kind", "")
            widget.addItem(f"{job_id} — {message} ({status})")
        label.setText(f"{label.property('bucket_name')} ({len(jobs)})")

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _make_bucket_list(self, title: str, subtitle: str) -> dict[str, QWidget]:
        frame = QGroupBox(self)
        frame.setTitle(title)

        label = QLabel(f"{title} (0)", frame)
        label.setProperty("bucket_name", title)

        list_widget = QListWidget(frame)
        list_widget.setUniformItemSizes(True)

        lay = QVBoxLayout(frame)
        lay.addWidget(label)
        lay.addWidget(list_widget, 1)
        hint = QLabel(subtitle, frame)
        hint.setWordWrap(True)
        hint.setProperty("class", "hint")
        lay.addWidget(hint)

        return {"frame": frame, "list": list_widget, "label": label}

    @staticmethod
    def _is_import_job(job: dict) -> bool:
        kind = str(job.get("kind", "")).lower()
        if "import" in kind:
            return True
        if kind.startswith("vn."):
            return True
        return False

    @staticmethod
    def _map_status(status: Optional[str]) -> str:
        if not status:
            return "queued"
        status_lower = status.lower()
        if status_lower in {"queued", "pending"}:
            return "queued"
        if status_lower in {"running", "active", "in_progress"}:
            return "active"
        return "done"

    # Public refresh hook for callers that expect a refresh() method
    def refresh(self) -> None:
        self._request_snapshot()
