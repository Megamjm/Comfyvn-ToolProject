import json
import re

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QDockWidget, QMainWindow

from comfyvn.config.runtime_paths import workspace_dir


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")


def _ensure_dock_names(window: QMainWindow):
    """Assign stable objectName to every QDockWidget before save/restore."""
    for i, dock in enumerate(window.findChildren(QDockWidget)):
        if not dock.objectName():
            dock.setObjectName(f"dock_{_slug(dock.windowTitle())}_{i}")
        dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )


class WorkspaceManager:
    def __init__(self, window: QMainWindow):
        self.window = window
        self.dir = workspace_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.current = "default_space"

    def save(self, name=None):
        name = name or self.current
        _ensure_dock_names(self.window)
        data = self.window.saveState().data().hex()
        (self.dir / f"{name}.json").write_text(json.dumps({"layout": data}))

    def load(self, name=None):
        name = name or self.current
        path = self.dir / f"{name}.json"
        if not path.exists():
            return
        raw = json.loads(path.read_text())

        _ensure_dock_names(self.window)
        self.window.restoreState(QByteArray.fromHex(bytes(raw["layout"], "utf8")))
