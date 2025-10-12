# comfyvn/gui/components/task_manager_controls.py
# ⚙️ Task Manager Controls — v1.0 (Phase 3.4-D)
# Adds Auto-Optimize, Rebalance, Device-Swap, and Quick Filters
# [🎨 GUI Code Production Chat]

import threading, requests, json
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QComboBox, QCheckBox, QMessageBox
)
from comfyvn.core.system_monitor import SystemMonitor


class TaskManagerControls(QWidget):
    """
    Utility control bar for TaskManagerDock — provides system-aware task actions:
      • Auto-Optimize (balances jobs based on current load)
      • Rebalance Jobs (moves queued tasks between CPU/GPU)
      • Device Filter / Quick job filter switches
    """

    message = Signal(str)
    refresh_jobs = Signal()

    def __init__(self, server_url="http://127.0.0.1:8001", parent=None):
        super().__init__(parent)
        self.server_url = server_url.rstrip("/")
        self.monitor = SystemMonitor(debug=False)
        self.monitor.on_update(self._on_metrics)
        self.latest_metrics = {}

        self._build_ui()
        self.monitor.start(interval=5)

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(6)

        top_row = QHBoxLayout()
        self.btn_auto_opt = QPushButton("⚡ Auto-Optimize")
        self.btn_rebalance = QPushButton("🔁 Rebalance Jobs")
        self.btn_swap = QPushButton("🔀 Move to GPU")
        self.btn_refresh = QPushButton("🔄 Refresh")
        for b in [self.btn_auto_opt, self.btn_rebalance, self.btn_swap, self.btn_refresh]:
            b.setMinimumWidth(120)
            top_row.addWidget(b)
        root.addLayout(top_row)

        # Quick filters
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Quick Filters:"))
        self.chk_cpu = QCheckBox("CPU Only")
        self.chk_gpu = QCheckBox("GPU Only")
        self.chk_active = QCheckBox("Active Jobs")
        self.chk_failed = QCheckBox("Failed Jobs")
        for c in [self.chk_cpu, self.chk_gpu, self.chk_active, self.chk_failed]:
            filter_row.addWidget(c)
        filter_row.addStretch(1)
        root.addLayout(filter_row)

        # Device preference selector
        dev_row = QHBoxLayout()
        dev_row.addWidget(QLabel("Preferred Device:"))
        self.device_box = QComboBox()
        self.device_box.addItems(["Auto", "CPU", "GPU", "RAM-Only"])
        dev_row.addWidget(self.device_box)
        dev_row.addStretch(1)
        root.addLayout(dev_row)

        # Signals
        self.btn_auto_opt.clicked.connect(self._auto_optimize)
        self.btn_rebalance.clicked.connect(self._rebalance)
        self.btn_swap.clicked.connect(self._swap_selected_to_gpu)
        self.btn_refresh.clicked.connect(lambda: self.refresh_jobs.emit())

    # ------------------------------------------------------------------
    # Metrics / system info feedback
    # ------------------------------------------------------------------
    def _on_metrics(self, data):
        self.latest_metrics = data

    # ------------------------------------------------------------------
    @Slot()
    def _auto_optimize(self):
        """Automatically rebalance queued/running jobs based on load."""
        res = self.latest_metrics.get("resources", {})
        cpu, ram, gpu = res.get("cpu_percent", 0), res.get("ram_percent", 0), res.get("gpu_percent", 0)

        msg = f"CPU {cpu:.1f}% | RAM {ram:.1f}% | GPU {gpu:.1f}%"
        self.message.emit(f"[Auto-Optimize] Metrics → {msg}")

        # Example heuristic: prefer GPU if CPU > 80% and GPU < 70%
        target = "gpu" if cpu > 80 and gpu < 70 else "cpu" if gpu > 90 else "auto"

        def _work():
            try:
                r = requests.post(f"{self.server_url}/jobs/optimize", json={"target": target}, timeout=10)
                if r.status_code == 200:
                    self.message.emit(f"[Auto-Optimize] Rebalanced toward {target.upper()}")
                else:
                    self.message.emit(f"[Auto-Optimize] Server Error {r.status_code}")
            except Exception as e:
                self.message.emit(f"[Auto-Optimize] Failed → {e}")

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    @Slot()
    def _rebalance(self):
        """Rebalances queued jobs across available compute devices."""
        def _work():
            try:
                r = requests.post(f"{self.server_url}/jobs/rebalance", timeout=10)
                if r.status_code == 200:
                    self.message.emit("[Rebalance] Jobs successfully redistributed.")
                    self.refresh_jobs.emit()
                else:
                    self.message.emit(f"[Rebalance] Server Error {r.status_code}")
            except Exception as e:
                self.message.emit(f"[Rebalance] Failed → {e}")

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    @Slot()
    def _swap_selected_to_gpu(self):
        """Moves selected CPU jobs to GPU (if supported by backend)."""
        dev = self.device_box.currentText().lower()
        def _work():
            try:
                r = requests.post(f"{self.server_url}/jobs/move", json={"target": dev}, timeout=10)
                if r.status_code == 200:
                    self.message.emit(f"[Device-Swap] Moved selected tasks → {dev.upper()}")
                    self.refresh_jobs.emit()
                else:
                    self.message.emit(f"[Device-Swap] Server Error {r.status_code}")
            except Exception as e:
                self.message.emit(f"[Device-Swap] Failed → {e}")

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    def collect_filters(self):
        """Returns dict for filtering jobs table externally."""
        return {
            "cpu_only": self.chk_cpu.isChecked(),
            "gpu_only": self.chk_gpu.isChecked(),
            "active": self.chk_active.isChecked(),
            "failed": self.chk_failed.isChecked(),
        }