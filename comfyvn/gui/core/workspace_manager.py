from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow
import json, os
from pathlib import Path

class WorkspaceManager:
    def __init__(self, window: QMainWindow):
        self.window = window
        self.dir = Path("data/workspaces"); self.dir.mkdir(parents=True, exist_ok=True)
        self.current = "default_space"

    def save(self, name=None):
        name = name or self.current
        data = self.window.saveState().data().hex()
        (self.dir / f"{name}.json").write_text(json.dumps({"layout": data}))

    def load(self, name=None):
        name = name or self.current
        path = self.dir / f"{name}.json"
        if not path.exists(): return
        raw = json.loads(path.read_text())
        from PySide6.QtCore import QByteArray
        self.window.restoreState(QByteArray.fromHex(bytes(raw["layout"], "utf8")))