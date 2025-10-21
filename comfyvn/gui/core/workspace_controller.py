import json
# comfyvn/gui/core/workspace_controller.py  [Studio-090]
from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QAction


class WorkspaceController:
    def __init__(self, window, store_dir: Path):
        self.window = window
        self.dir = store_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.current = "default"

    def save(self, name=None):
        name = name or self.current
        path = self.dir / f"{name}.json"
        data = self.window.saveState().data().hex()
        path.write_text(json.dumps({"layout": data}), encoding="utf-8")
        return str(path)

    def load(self, name=None):
        name = name or self.current
        path = self.dir / f"{name}.json"
        if not path.exists():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.window.restoreState(QByteArray.fromHex(bytes(payload["layout"], "utf-8")))
        return True
