from __future__ import annotations

from typing import Iterable, Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class MetricsDashboard(QWidget):
    """Simple metrics dashboard showing CPU/RAM/GPU state plus server controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Status indicator row
        self._status_label = QLabel(self)
        self._status_label.setObjectName("metricsStatusLabel")
        self._status_label.setText(self._format_status(False, "Disconnected"))
        self._status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.start_button = QPushButton("Start Embedded Server", self)
        self.start_button.setObjectName("metricsStartButton")

        status_row = QHBoxLayout()
        status_row.addWidget(self._status_label, 1)
        status_row.addWidget(self.start_button, 0, Qt.AlignRight)
        root.addLayout(status_row)

        # Metrics frame
        metrics_frame = QFrame(self)
        metrics_frame.setFrameShape(QFrame.StyledPanel)
        metrics_frame.setObjectName("metricsFrame")
        metrics_layout = QGridLayout(metrics_frame)
        metrics_layout.setContentsMargins(12, 12, 12, 12)
        metrics_layout.setSpacing(12)

        self._cpu_bar = QProgressBar(self)
        self._cpu_bar.setRange(0, 100)
        self._cpu_bar.setFormat("CPU — %p%")

        self._mem_bar = QProgressBar(self)
        self._mem_bar.setRange(0, 100)
        self._mem_bar.setFormat("Memory — %p%")

        self._gpu_list = QListWidget(self)
        self._gpu_list.setObjectName("metricsGpuList")
        self._gpu_list.setAlternatingRowColors(True)
        self._gpu_list.setSelectionMode(QListWidget.NoSelection)

        metrics_layout.addWidget(self._cpu_bar, 0, 0, 1, 1)
        metrics_layout.addWidget(self._mem_bar, 1, 0, 1, 1)
        metrics_layout.addWidget(self._gpu_list, 0, 1, 2, 1)
        root.addWidget(metrics_frame, 1)

        self._message_label = QLabel(self)
        self._message_label.setWordWrap(True)
        self._message_label.setObjectName("metricsMessageLabel")
        self._message_label.hide()
        root.addWidget(self._message_label)

        root.addStretch(1)

    # -----------------
    # Public interface
    # -----------------
    def update_metrics(self, payload: Mapping[str, object] | None) -> None:
        """Update progress bars from backend metrics payload."""
        if not payload or not bool(payload.get("ok")):
            self._cpu_bar.setValue(0)
            self._mem_bar.setValue(0)
            self._cpu_bar.setFormat("CPU — n/a")
            self._mem_bar.setFormat("Memory — n/a")
            self._gpu_list.clear()
            return

        cpu = self._bound_percent(payload.get("cpu"))
        mem = self._bound_percent(payload.get("mem"))

        self._cpu_bar.setValue(cpu)
        self._cpu_bar.setFormat(f"CPU — {cpu}%")

        self._mem_bar.setValue(mem)
        self._mem_bar.setFormat(f"Memory — {mem}%")

        gpu_entries = payload.get("gpus") if isinstance(payload, Mapping) else []
        self._hydrate_gpu_list(gpu_entries)  # type: ignore[arg-type]

    def update_health(self, info: Mapping[str, object] | None, *, fallback_ok: bool = False) -> None:
        """Update the status badge based on /health response."""
        ok = fallback_ok
        status_text = "Disconnected"
        detail = ""

        if info and isinstance(info, Mapping):
            ok = bool(info.get("ok", False))
            data = info.get("data")
            if isinstance(data, Mapping):
                status_text = str(data.get("status") or data.get("state") or ("OK" if ok else "Issue"))
            elif isinstance(data, str):
                status_text = data
            elif ok:
                status_text = "Online"
            status_code = info.get("status")
            if status_code:
                detail = f"HTTP {status_code}"
        elif fallback_ok:
            status_text = "Online"

        message = status_text if not detail else f"{status_text} ({detail})"
        self._status_label.setText(self._format_status(ok, message))

    def set_retry_message(self, delay_seconds: float) -> None:
        if delay_seconds <= 0:
            self._message_label.hide()
            self._message_label.clear()
            return
        self._message_label.setText(f"Retrying server start in {delay_seconds:.0f} seconds…")
        self._message_label.show()

    def show_message(self, text: str | None) -> None:
        if text:
            self._message_label.setText(text)
            self._message_label.show()
        else:
            self._message_label.hide()
            self._message_label.clear()

    def set_manual_enabled(self, enabled: bool) -> None:
        self.start_button.setEnabled(enabled)

    # -----------------
    # Helpers
    # -----------------
    def _hydrate_gpu_list(self, entries: Iterable[Mapping[str, object]] | None) -> None:
        self._gpu_list.clear()
        if not entries:
            placeholder = QListWidgetItem("No GPU metrics reported.")
            placeholder.setFlags(Qt.NoItemFlags)
            self._gpu_list.addItem(placeholder)
            return

        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            idx = entry.get("id", "?")
            name = entry.get("name", "GPU")
            util = self._bound_percent(entry.get("util"))
            mem_used = entry.get("mem_used")
            mem_total = entry.get("mem_total")
            temp = entry.get("temp_c")
            pieces = [f"GPU {idx}: {name}", f"Util {util}%", self._format_mem(mem_used, mem_total)]
            if isinstance(temp, (int, float)):
                pieces.append(f"{temp}°C")
            item = QListWidgetItem(" • ".join(pieces))
            item.setFlags(Qt.NoItemFlags)
            self._gpu_list.addItem(item)

    @staticmethod
    def _format_mem(used: object, total: object) -> str:
        if not isinstance(used, (int, float)) or not isinstance(total, (int, float)) or total <= 0:
            return "Memory n/a"
        return f"Memory {used}/{total} MB"

    @staticmethod
    def _bound_percent(value: object) -> int:
        if isinstance(value, (int, float)):
            return max(0, min(100, int(round(value))))
        return 0

    @staticmethod
    def _format_status(ok: bool, text: str) -> str:
        color = "#2ecc71" if ok else "#e74c3c"
        return f'<span style="color:{color};font-weight:600;">●</span> {text}'
