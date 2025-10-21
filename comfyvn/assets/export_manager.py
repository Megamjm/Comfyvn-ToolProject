from PySide6.QtGui import QAction

from comfyvn.integrations.renpy_bridge import RenPyBridge


class ExportManager:
    def __init__(self, export_dir: str = "./exports/renpy"):
        self.bridge = RenPyBridge(export_dir)

    def export_scene_to_renpy(self, scene):
        return self.bridge.save_script(scene)
