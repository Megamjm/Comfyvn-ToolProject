# comfyvn/gui/components/charts/resource_chart_widget.py
# 📈 Resource Chart Widget — v1.0 (Phase 3.4-C)
# Real-time CPU / RAM / GPU utilization history graphs (60s window)
# [🎨 GUI Code Production Chat]

import collections
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtGui import QPen, QColor, QPainter, QPainterPath
from comfyvn.modules.system_monitor import SystemMonitor


class ResourceChartWidget(QWidget):
    """Lightweight real-time utilization chart for CPU, RAM, and GPU."""

    def __init__(self, parent=None, max_points=60):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setObjectName("ResourceChartWidget")

        self.max_points = max_points  # ~60s window at 1 Hz
        self.monitor = SystemMonitor(debug=False)
        self.monitor.on_update(self._on_update)
        self.data = {
            "cpu": collections.deque(maxlen=max_points),
            "ram": collections.deque(maxlen=max_points),
            "gpu": collections.deque(maxlen=max_points),
        }

        # Title
        layout = QVBoxLayout(self)
        self.title = QLabel("System Utilization (last 60 s)")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-weight:bold; padding:4px;")
        layout.addWidget(self.title)
        layout.setContentsMargins(2, 2, 2, 2)

        # Update timers
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update)
        self.refresh_timer.start(1000)

        self.monitor.start(interval=1)

    # ------------------------------------------------------------------
    def _on_update(self, snapshot):
        res = snapshot.get("resources", {})
        self.data["cpu"].append(float(res.get("cpu_percent", 0)))
        self.data["ram"].append(float(res.get("ram_percent", 0)))
        self.data["gpu"].append(float(res.get("gpu_percent", 0)))

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)

        # Draw grid
        self._draw_grid(painter)

        # Plot lines
        self._draw_line(painter, self.data["cpu"], QColor(0, 200, 255), "CPU")
        self._draw_line(painter, self.data["ram"], QColor(255, 200, 0), "RAM")
        self._draw_line(painter, self.data["gpu"], QColor(0, 255, 100), "GPU")

        painter.end()

    # ------------------------------------------------------------------
    def _draw_grid(self, p: QPainter):
        rect = self.rect()
        pen = QPen(QColor(50, 50, 50))
        p.setPen(pen)

        # Horizontal lines every 20%
        for y in range(0, 101, 20):
            yp = rect.height() - (y / 100) * rect.height()
            p.drawLine(0, int(yp), rect.width(), int(yp))
        # Vertical 10s ticks
        for i in range(0, self.max_points, 10):
            xp = rect.width() - (i / self.max_points) * rect.width()
            p.drawLine(int(xp), 0, int(xp), rect.height())

        p.setPen(QPen(QColor(80, 80, 80)))
        p.drawRect(rect.adjusted(0, 0, -1, -1))

    def _draw_line(self, p: QPainter, series, color: QColor, label: str):
        if not series:
            return
        rect = self.rect()
        path = QPainterPath()
        step_x = rect.width() / max(1, self.max_points - 1)
        path.moveTo(rect.width(), rect.height())
        for i, val in enumerate(reversed(series)):
            x = rect.width() - i * step_x
            y = rect.height() - (val / 100) * rect.height()
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        pen = QPen(color, 2)
        p.setPen(pen)
        p.drawPath(path)

        # Label text (latest value)
        latest = series[-1]
        text = f"{label}: {latest:.0f}%"
        p.setPen(QPen(color))
        p.drawText(8, 16 + (18 * ["CPU", "RAM", "GPU"].index(label)), text)
