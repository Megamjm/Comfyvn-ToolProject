from PySide6.QtGui import QAction

from pathlib import Path
import importlib, sys

class PluginLoader:
    def __init__(self, base="data/plugins"):
        self.base = Path(base); self.base.mkdir(parents=True, exist_ok=True)
    def list(self):
        return [p.stem for p in self.base.glob("*.py")]
    def import_all(self):
        out = []
        sys.path.insert(0, str(self.base.resolve()))
        for p in self.base.glob("*.py"):
            try:
                mod = importlib.import_module(p.stem)
                out.append({"name": p.stem, "ok": True})
            except Exception as e:
                out.append({"name": p.stem, "ok": False, "error": str(e)})
        return out