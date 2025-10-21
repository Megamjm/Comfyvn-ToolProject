from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

import httpx
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QLabel

logger = logging.getLogger(__name__)


class StatusBarMetrics(QObject):
    """Lightweight status bar poller that displays backend CPU/RAM/GPU usage."""

    metrics_ready = Signal(dict)
    offline_ready = Signal()

    def __init__(
        self,
        base_url: str,
        *,
        parent: QObject | None = None,
        interval_ms: int = 2500,
        timeout: float = 1.5,
    ):
        super().__init__(parent)
        self._base_url = base_url.rstrip("/")
        self._timeout = max(0.5, float(timeout))
        self._interval_ms = max(750, int(interval_ms))
        self._label = QLabel("CPU --% • RAM --% • GPU --")
        self._label.setObjectName("statusBarMetricsLabel")
        self._lock = threading.Lock()
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._trigger_poll)
        self.metrics_ready.connect(self._apply_metrics)
        self.offline_ready.connect(self._apply_offline)
        self._last_payload: Optional[Dict[str, Any]] = None

    @property
    def widget(self) -> QLabel:
        return self._label

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self._trigger_poll()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def set_base_url(self, base_url: str) -> None:
        clean = base_url.rstrip("/")
        if clean != self._base_url:
            self._base_url = clean
            self._trigger_poll()

    def update_payload(self, payload: Optional[Dict[str, Any]]) -> None:
        if payload and bool(payload.get("ok")):
            self._apply_metrics(dict(payload))
        else:
            self._apply_offline()

    def _trigger_poll(self) -> None:
        if not self._base_url:
            self._apply_offline()
            return
        if not self._lock.acquire(blocking=False):
            return

        def worker():
            try:
                self._poll()
            finally:
                self._lock.release()

        threading.Thread(target=worker, daemon=True, name="StatusBarMetricsPoll").start()

    def _poll(self) -> None:
        url = f"{self._base_url}/system/metrics"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url)
        except Exception as exc:
            logger.debug("Status bar metrics request failed: %s", exc)
            self.offline_ready.emit()
            return

        if response.status_code != 200:
            logger.debug("Status bar metrics request returned %s", response.status_code)
            self.offline_ready.emit()
            return

        try:
            payload = response.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"data": payload}
        payload.setdefault("ok", True)
        self.metrics_ready.emit(payload)

    def _apply_metrics(self, payload: Dict[str, Any]) -> None:
        self._last_payload = dict(payload)
        cpu = self._format_percent(payload.get("cpu"))
        mem = self._format_percent(payload.get("mem"))
        gpu = self._format_gpu(payload.get("gpus"))
        parts = [f"CPU {cpu}", f"RAM {mem}"]
        if gpu:
            parts.append(gpu)
        else:
            parts.append("GPU --")
        self._label.setText(" • ".join(parts))

    def _apply_offline(self) -> None:
        self._last_payload = None
        self._label.setText("CPU --% • RAM --% • GPU --")

    @staticmethod
    def _format_percent(value: Any) -> str:
        if isinstance(value, (int, float)):
            clamped = max(0, min(100, int(round(value))))
            return f"{clamped}%"
        return "--%"

    def _format_gpu(self, gpus: Any) -> str:
        if isinstance(gpus, list) and gpus:
            first = gpus[0]
            if isinstance(first, dict):
                util = self._format_percent(first.get("util"))
                name = first.get("name") or first.get("id")
                if isinstance(name, (int, float)):
                    name = f"#{int(name)}"
                elif not isinstance(name, str) or not name:
                    name = "#0"
                mem_used = first.get("mem_used")
                mem_total = first.get("mem_total")
                mem_text = ""
                if isinstance(mem_used, (int, float)) and isinstance(
                    mem_total, (int, float)
                ):
                    mem_text = f" {int(mem_used)}/{int(mem_total)}MB"
                return f"GPU {name} {util}{mem_text}"
        return ""
