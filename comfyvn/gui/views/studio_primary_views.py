from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from comfyvn.gui.panels.debug_integrations import DebugIntegrationsPanel
from comfyvn.gui.services.job_stream import JobStreamClient
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.studio.core.asset_registry import AssetRegistry
from comfyvn.studio.core.timeline_registry import TimelineRegistry

LOGGER = logging.getLogger(__name__)


def _sample_bundle_payload() -> Dict[str, Any]:
    return {
        "raw": {
            "id": "studio-preview",
            "dialogue": [
                {
                    "type": "line",
                    "speaker": "Guide",
                    "text": "Welcome to the Studio shell!",
                }
            ],
        }
    }


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

        self.status_label = QLabel("Import Processing — connecting…", self)
        self.status_label.setWordWrap(True)

        self.queued_list = self._make_bucket_list(
            "Queued", "Import jobs queued for processing."
        )
        self.active_list = self._make_bucket_list(
            "Active", "Import jobs currently in progress."
        )
        self.done_list = self._make_bucket_list(
            "Done", "Completed or failed import jobs."
        )

        buckets_widget = QWidget(self)
        buckets_layout = QHBoxLayout(buckets_widget)
        buckets_layout.setContentsMargins(0, 0, 0, 0)
        buckets_layout.setSpacing(12)
        buckets_layout.addWidget(self.queued_list["frame"], 1)
        buckets_layout.addWidget(self.active_list["frame"], 1)
        buckets_layout.addWidget(self.done_list["frame"], 1)

        self.raw_toggle = QCheckBox("Show raw response", self)
        self.raw_toggle.stateChanged.connect(self._toggle_raw)

        self._refresh_button = QPushButton("Refresh", self)
        self._refresh_button.clicked.connect(self._request_snapshot)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.raw_toggle, alignment=Qt.AlignRight)
        self._buckets_widget = buckets_widget
        layout.addWidget(buckets_widget, 1)
        layout.addWidget(self._refresh_button, alignment=Qt.AlignRight)

        self.raw_view = QPlainTextEdit(self)
        self.raw_view.setReadOnly(True)
        self.raw_view.hide()
        layout.addWidget(self.raw_view, 1)

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
            LOGGER.debug("Import Processing snapshot request failed: %s", exc)
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
            self.status_label.setText("Import Processing — live updates")
            LOGGER.info("Import Processing job stream connected")
        elif state.startswith("error"):
            self.status_label.setText("Import Processing — reconnecting…")
            LOGGER.warning("Import Processing job stream error: %s", state)
        elif state == "disconnected":
            self.status_label.setText("Import Processing — disconnected, retrying…")
            LOGGER.info("Import Processing job stream disconnected")
        elif state == "connecting":
            self.status_label.setText("Import Processing — connecting…")

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
        self._update_raw_view()

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

    def _toggle_raw(self, state: int) -> None:
        enabled = state == Qt.Checked
        self._buckets_widget.setVisible(not enabled)
        self._refresh_button.setVisible(not enabled)
        self.raw_view.setVisible(enabled)
        if enabled:
            self._update_raw_view()

    def _update_raw_view(self) -> None:
        if not self.raw_view.isVisible():
            return
        snapshot = {
            "jobs": list(self.jobs.values()),
            "updated_at": time.time(),
        }
        try:
            text = json.dumps(snapshot, indent=2, sort_keys=True)
        except TypeError:
            text = repr(snapshot)
        self.raw_view.setPlainText(text)

    def set_base_url(self, base_url: str) -> None:
        new_base = base_url.rstrip("/")
        if not new_base or new_base == self.base_url:
            return
        self.base_url = new_base
        try:
            self.stream.stop()
        except Exception:
            LOGGER.debug("Failed to stop job stream before base switch", exc_info=True)
        self.stream.base = self.base_url
        self.stream.start()
        self._request_snapshot()

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


class ComputeSummaryView(QWidget):
    """Wraps the provider diagnostics panel for the Studio Compute view."""

    def __init__(self, base_url: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel = DebugIntegrationsPanel(base=self.base_url, parent=self)
        layout.addWidget(self.panel)

    def set_base_url(self, base_url: str) -> None:
        new_base = base_url.rstrip("/")
        if not new_base or new_base == self.base_url:
            return
        self.base_url = new_base
        self.panel.base = self.base_url
        try:
            self.panel.refresh()
        except Exception:
            LOGGER.debug("Compute diagnostics refresh failed", exc_info=True)


class ExportStatusView(QWidget):
    """Simple controller for requesting bundle exports and inspecting responses."""

    def __init__(self, bridge: ServerBridge, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self._last_result: Optional[Dict[str, Any]] = None
        self._raw_mode = False
        self._inflight = False
        self._status_base = bridge.base_url

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.status_label = QLabel("Trigger a bundle export to view status.", self)
        self.status_label.setWordWrap(True)

        self.path_input = QLineEdit(self)
        self.path_input.setPlaceholderText("Optional raw scene JSON path…")

        control_row = QHBoxLayout()
        self.sample_button = QPushButton("Export Sample Bundle", self)
        self.sample_button.clicked.connect(lambda: self._trigger_export(sample=True))
        self.export_button = QPushButton("Export Bundle", self)
        self.export_button.clicked.connect(lambda: self._trigger_export(sample=False))
        control_row.addWidget(self.sample_button)
        control_row.addWidget(self.export_button)
        control_row.addStretch(1)

        self.raw_toggle = QCheckBox("Show raw response", self)
        self.raw_toggle.stateChanged.connect(
            lambda state: self._set_raw_mode(state == Qt.Checked)
        )

        self.result_view = QPlainTextEdit(self)
        self.result_view.setReadOnly(True)

        layout.addWidget(self.status_label)
        layout.addWidget(self.path_input)
        layout.addLayout(control_row)
        layout.addWidget(self.raw_toggle, alignment=Qt.AlignRight)
        layout.addWidget(self.result_view, 1)

    def set_base_url(self, base_url: str) -> None:
        new_base = base_url.rstrip("/")
        if new_base:
            self._status_base = new_base
            if self._last_result is None:
                self.status_label.setText(f"Exports will target {self._status_base}.")

    def _trigger_export(self, *, sample: bool) -> None:
        if self._inflight:
            return
        payload = self._build_payload(sample=sample)
        self._set_busy(True)

        def _complete(result: Dict[str, Any]) -> None:
            QTimer.singleShot(0, lambda: self._apply_result(result))

        self.bridge.post(
            "/api/studio/export_bundle",
            payload,
            cb=_complete,
            timeout=15.0,
        )

    def _build_payload(self, *, sample: bool) -> Dict[str, Any]:
        if not sample:
            raw_path = self.path_input.text().strip()
            if raw_path:
                return {"raw_path": raw_path}
        return _sample_bundle_payload()

    def _apply_result(self, result: Dict[str, Any]) -> None:
        self._set_busy(False)
        if not isinstance(result, dict):
            self.status_label.setText("Export failed: invalid response.")
            self._last_result = None
            self._update_result_view()
            return
        self._last_result = result
        if result.get("ok"):
            bundle = result.get("bundle") or result.get("data")
            summary = self._summarise_bundle(bundle)
            if self._status_base:
                summary = f"{summary} (base {self._status_base})"
            self.status_label.setText(summary)
        else:
            error = result.get("error") or result.get("data")
            if isinstance(error, dict):
                error = error.get("detail") or error.get("message")
            self.status_label.setText(f"Export failed: {error or 'Unknown error'}")
        self._update_result_view()

    def _summarise_bundle(self, bundle: Any) -> str:
        if isinstance(bundle, dict):
            parts = []
            name = bundle.get("name") or bundle.get("id")
            if name:
                parts.append(f"Bundle {name}")
            size = bundle.get("size") or bundle.get("bytes")
            if isinstance(size, (int, float)):
                parts.append(f"size {int(size)} bytes")
            target = bundle.get("path") or bundle.get("destination")
            if target:
                parts.append(str(target))
            return "Export completed: " + (", ".join(parts) or "bundle ready")
        return "Export completed."

    def _update_result_view(self) -> None:
        if self._raw_mode:
            self.result_view.setPlainText(self._raw_text())
            return
        if not isinstance(self._last_result, dict):
            self.result_view.setPlainText("No response captured yet.")
            return
        bundle = self._last_result.get("bundle") or self._last_result.get("data")
        if isinstance(bundle, dict):
            lines = []
            for key in ("id", "name", "path", "destination", "size", "bytes"):
                if key in bundle:
                    lines.append(f"{key}: {bundle[key]}")
            if not lines:
                lines = [json.dumps(bundle, indent=2, sort_keys=True)]
            self.result_view.setPlainText("\n".join(lines))
        else:
            self.result_view.setPlainText(
                json.dumps(self._last_result, indent=2, sort_keys=True)
            )

    def _set_busy(self, busy: bool) -> None:
        self._inflight = busy
        self.sample_button.setEnabled(not busy)
        self.export_button.setEnabled(not busy)
        self.path_input.setEnabled(not busy)
        if busy:
            self.status_label.setText("Export in progress…")

    def _set_raw_mode(self, enabled: bool) -> None:
        if self._raw_mode == enabled:
            return
        self._raw_mode = enabled
        self._update_result_view()

    def _raw_text(self) -> str:
        payload = self._last_result
        if payload is None:
            return "No response captured yet."
        try:
            return json.dumps(payload, indent=2, sort_keys=True)
        except TypeError:
            return repr(payload)
