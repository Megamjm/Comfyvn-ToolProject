from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/services/server_bridge.py
# [ComfyVN Architect | Phase 2.05 | Async Bridge + Non-blocking refresh]
import httpx, threading, asyncio, time
from PySide6.QtCore import QObject, Signal

class ServerBridge(QObject):
    status_updated = Signal(dict)

    def __init__(self, base="http://127.0.0.1:8001"):
        super().__init__()
        self.base = base
        self._stop = False
        self._thread = None
        self._interval = 5
        self._latest = {}

    # ─────────────────────────────
    # Async polling loop (non-blocking)
    # ─────────────────────────────
    async def _poll_once(self):
        async with httpx.AsyncClient(timeout=3.0) as cli:
            try:
                r = await cli.get(f"{self.base}/system/metrics")
                if r.status_code == 200:
                    self._latest = r.json()
                    self.status_updated.emit(self._latest)
            except Exception:
                self._latest = {"ok": False}
                self.status_updated.emit(self._latest)

    def start_polling(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        def _loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            while not self._stop:
                loop.run_until_complete(self._poll_once())
                time.sleep(self._interval)
        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_polling(self):
        self._stop = True

    def get(self, path: str, default=None):
        try:
            return self._latest.get(path, default)
        except Exception:
            return default