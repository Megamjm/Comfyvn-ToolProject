from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/bridge_local.py
# reserved stub for server→GUI bridges (future multiplayer/sync)
class BridgeLocal:
    def __init__(self):
        self.active = False
    def start(self): self.active = True
    def stop(self): self.active = False
bridge = BridgeLocal()