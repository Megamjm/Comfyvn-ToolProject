# comfyvn/gui/components/task_resource_bar.py
# 📊 Task Resource Bar — v0.4-dev (Phase 3.4-A)
# Shows CPU / GPU / RAM usage using SystemMonitor
# [🎨 GUI Code Production Chat]

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QProgressBar, QLabel
from comfyvn.core.system_monitor import SystemMonitor


class TaskResourceBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.lbl_cpu = QLabel("CPU")
        self.bar_cpu = QProgressBar(); self.bar_cpu.setRange(0, 100)
        self.lbl_gpu = QLabel("GPU")
        self.bar_gpu = QProgressBar(); self.bar_gpu.setRange(0, 100)
        self.lbl_ram = QLabel("RAM")
        self.bar_ram = QProgressBar(); self.bar_ram.setRange(0, 100)

        for w in (self.lbl_cpu, self.bar_cpu, self.lbl_gpu, self.bar_gpu, self.lbl_ram, self.bar_ram):
            lay.addWidget(w)

        self.monitor = SystemMonitor()
        self.monitor.on_update(self._on_update)
        # no separate start; rely on existing running instance or start a light one
        self.monitor.start(interval=7)

    def _on_update(self, data: dict):
        cpu = int(data.get("cpu_percent", 0))
        gpu = int(data.get("gpu_percent", 0))
        ram = int(data.get("ram_percent", 0))
        self.bar_cpu.setValue(cpu)
        self.bar_gpu.setValue(gpu)
        self.bar_ram.setValue(ram)