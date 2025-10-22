from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config.baseurl_authority import default_base_url

_ROW_HEIGHT = 64
_LEFT_GUTTER = 140
_TOP_GUTTER = 28
_MIN_WIDTH = 720
_PALETTE = {
    "queued": QColor("#1e88e5"),
    "running": QColor("#43a047"),
    "succeeded": QColor("#3949ab"),
    "failed": QColor("#e53935"),
    "cancelled": QColor("#8d6e63"),
}


class _GanttCanvas(QWidget):
    """Simple canvas that renders scheduler segments as a Gantt chart."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._segments: List[Dict[str, float]] = []
        self._queues: List[str] = []
        self._time_window: tuple[float, float] = (0.0, 1.0)
        self.setMinimumHeight(_ROW_HEIGHT * 3)

    def update_segments(self, segments: List[Dict[str, float]]) -> None:
        now = time.time()
        cleaned: List[Dict[str, float]] = []
        for seg in segments:
            start = float(seg.get("start") or now)
            end_raw = seg.get("end")
            end = float(end_raw if end_raw is not None else now)
            if end < start:
                end = start
            cleaned.append(
                {
                    "id": seg.get("id"),
                    "name": seg.get("name"),
                    "queue": seg.get("queue") or "local",
                    "device": seg.get("device"),
                    "status": seg.get("status") or "queued",
                    "priority": seg.get("priority") or 0,
                    "start": start,
                    "end": end,
                    "duration_sec": seg.get("duration_sec") or max(0.0, end - start),
                    "cost_estimate": seg.get("cost_estimate"),
                }
            )
        queues = sorted({seg["queue"] for seg in cleaned}) if cleaned else []
        if not queues:
            queues = ["local", "remote"]
        self._segments = cleaned
        self._queues = queues
        if cleaned:
            start_min = min(seg["start"] for seg in cleaned)
            end_max = max(seg["end"] for seg in cleaned)
            if end_max <= start_min:
                end_max = start_min + 1.0
            self._time_window = (start_min, end_max)
        else:
            now = time.time()
            self._time_window = (now, now + 1.0)
        self.updateGeometry()
        self.update()

    # Qt sizing --------------------------------------------------------
    def sizeHint(self) -> QSize:
        height = _TOP_GUTTER + len(self._queues or ["local", "remote"]) * _ROW_HEIGHT
        return QSize(_MIN_WIDTH, max(height, _ROW_HEIGHT * 3))

    # Painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())

        if not self._segments:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignCenter, "No scheduled jobs")
            return

        start_min, end_max = self._time_window
        span = max(1.0, end_max - start_min)

        width = max(_MIN_WIDTH, self.width())
        chart_width = width - _LEFT_GUTTER - 32
        scale_x = chart_width / span

        font_bold = QFont(self.font())
        font_bold.setBold(True)

        # Draw queue labels and horizontal bands
        for row, queue in enumerate(self._queues):
            top = _TOP_GUTTER + row * _ROW_HEIGHT
            rect = QRectF(_LEFT_GUTTER, top, chart_width, _ROW_HEIGHT)
            painter.fillRect(rect, self.palette().alternateBase())
            painter.setPen(QPen(self.palette().mid().color(), 1, Qt.DashLine))
            painter.drawLine(
                _LEFT_GUTTER, top + _ROW_HEIGHT, width - 16, top + _ROW_HEIGHT
            )
            painter.setPen(self.palette().text().color())
            painter.setFont(font_bold)
            painter.drawText(
                QRectF(0, top, _LEFT_GUTTER - 12, _ROW_HEIGHT),
                Qt.AlignVCenter | Qt.AlignRight,
                queue.title(),
            )

        painter.setFont(self.font())

        for seg in self._segments:
            row = (
                self._queues.index(seg["queue"]) if seg["queue"] in self._queues else 0
            )
            top = _TOP_GUTTER + row * _ROW_HEIGHT + 8
            bar_start = _LEFT_GUTTER + (seg["start"] - start_min) * scale_x
            bar_width = max(6.0, (seg["end"] - seg["start"]) * scale_x)
            bar_rect = QRectF(bar_start, top, bar_width, _ROW_HEIGHT - 16)

            status = str(seg.get("status") or "queued").lower()
            color = _PALETTE.get(status, QColor("#546e7a"))
            painter.fillRect(bar_rect, color)
            painter.setPen(QPen(color.darker(130), 1))
            painter.drawRect(bar_rect)

            painter.setPen(Qt.white if color.lightness() < 160 else Qt.black)
            label = f"{seg.get('id')} • {seg['duration_sec']:.1f}s"
            cost = seg.get("cost_estimate")
            if cost is not None:
                label += f" • ${cost:.2f}"
            painter.drawText(
                bar_rect.adjusted(4, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, label
            )

        # Timeline axis
        painter.setPen(self.palette().text().color())
        baseline_y = _TOP_GUTTER + len(self._queues) * _ROW_HEIGHT + 12
        painter.drawLine(_LEFT_GUTTER, baseline_y, width - 16, baseline_y)
        painter.setFont(self.font())

        tick_count = 6
        for i in range(tick_count + 1):
            frac = i / tick_count
            x = _LEFT_GUTTER + frac * chart_width
            ts = start_min + frac * span
            label = time.strftime("%H:%M:%S", time.localtime(ts))
            painter.drawLine(x, baseline_y - 4, x, baseline_y + 4)
            painter.drawText(QPointF(x - 30, baseline_y + 16), label)


class ScheduleBoardPanel(QDockWidget):
    """Fetches scheduler telemetry and renders a simple Gantt board."""

    def __init__(self, base: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__("Scheduler Board", parent)
        self.setObjectName("ScheduleBoardPanel")
        self.base_url = (base or default_base_url()).rstrip("/")

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.status = QLabel("Scheduler Board — loading…", self)
        layout.addWidget(self.status)

        self.canvas = _GanttCanvas(container)
        scroll = QScrollArea(container)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.canvas)
        layout.addWidget(scroll, 1)

        self.timer = QTimer(container)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self.setWidget(container)
        self.refresh()

    def refresh(self) -> None:
        try:
            res = requests.get(self.base_url + "/api/schedule/board", timeout=2.5)
            res.raise_for_status()
            data = res.json()
        except Exception:
            self.status.setText("Scheduler Board — offline")
            self.canvas.update_segments([])
            return

        segments = data.get("jobs") or []
        self.status.setText(
            f"Scheduler Board — jobs: {len(segments)} | updated {data.get('generated_at','?')}"
        )
        self.canvas.update_segments(segments)
