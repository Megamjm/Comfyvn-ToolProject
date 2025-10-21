from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
# comfyvn/gui/panels/server_control_panel.py
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

# psutil is optional
try:
    import psutil
except Exception:
    psutil = None

import threading
import urllib.request


def _fetch_json(url: str, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


class ServerControlPanel(QWidget):
    def __init__(self, api_base="http://127.0.0.1:8001", parent=None):
        super().__init__(parent)
        self.api_base = api_base.rstrip("/")
        self.setObjectName("ServerControlPanel")

        self.lbl_server = QLabel("Server: unknown")
        self.lbl_cpu = QLabel("CPU: -")
        self.lbl_ram = QLabel("RAM: -")
        self.lbl_gpu = QLabel("GPU: -")
        self.lbl_tasks = QLabel("Tasks: -")

        for L in (
            self.lbl_server,
            self.lbl_cpu,
            self.lbl_ram,
            self.lbl_gpu,
            self.lbl_tasks,
        ):
            L.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        row = QHBoxLayout()
        row.addWidget(self.lbl_server)
        row.addSpacing(12)
        row.addWidget(self.lbl_cpu)
        row.addSpacing(12)
        row.addWidget(self.lbl_ram)
        row.addSpacing(12)
        row.addWidget(self.lbl_gpu)
        row.addSpacing(12)
        row.addWidget(self.lbl_tasks)
        row.addStretch(1)
        self.setLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(3000)
        self._tick()

    def _tick(self):
        # server status
        health = _fetch_json(self.api_base + "/health") or _fetch_json(
            self.api_base + "/healthz"
        )
        if health and isinstance(health, dict):
            self.lbl_server.setText("Server: ONLINE")
        else:
            self.lbl_server.setText("Server: OFFLINE")

        # metrics
        m = _fetch_json(self.api_base + "/system/metrics") or {}
        cpu_txt = "CPU: -"
        ram_txt = "RAM: -"
        gpu_txt = "GPU: -"
        if m:
            if "cpu" in m:
                cpu_txt = f"CPU: {m['cpu']}%"
            if "mem" in m:
                ram_txt = f"RAM: {m['mem']}%"
            if m.get("gpus"):
                g = m["gpus"]
                if isinstance(g, list) and g:
                    parts = []
                    for gg in g[:2]:
                        parts.append(
                            f"#{gg.get('id','?')} {gg.get('util','?')}% {gg.get('temp_c','?')}°C"
                        )
                    if len(g) > 2:
                        parts.append(f"+{len(g)-2} more")
                    gpu_txt = "GPU: " + " | ".join(parts)
                else:
                    gpu_txt = "GPU: 0"
        else:
            # fallback to local psutil
            if psutil:
                try:
                    cpu_txt = f"CPU: {psutil.cpu_percent(interval=0.05)}%"
                    ram_txt = f"RAM: {psutil.virtual_memory().percent}%"
                except Exception:
                    pass

        self.lbl_cpu.setText(cpu_txt)
        self.lbl_ram.setText(ram_txt)
        self.lbl_gpu.setText(gpu_txt)

        # tasks
        t = _fetch_json(self.api_base + "/system/status") or {}
        tasks_num = 0
        if isinstance(t, dict):
            # allow server to surface tasks later; for now just show standby
            pass
        self.lbl_tasks.setText(
            "Tasks: server on standby"
            if tasks_num == 0
            else f"Tasks: {tasks_num} running"
        )
