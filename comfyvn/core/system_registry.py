from PySide6.QtGui import QAction

import platform, os, json, time

class SystemRegistry:
    def __init__(self):
        self._meta = {
            "name": "ComfyVN",
            "version": "0.7.0",
            "py": platform.python_version(),
            "os": platform.platform(),
            "ts": time.time(),
        }
        self._devices = {}
    def update_devices(self, devices: dict): self._devices = devices or {}
    def info(self): return {"meta": self._meta, "devices": self._devices}