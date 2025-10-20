from PySide6.QtGui import QAction
# extensions/panel_demo.py
# [COMFYVN Architect | v1.0 | this chat]
from comfyvn.core.core import hooks
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

def register():
    hooks.emit("studio.register_panel", "Demo Panel", lambda: QLabel("Hi from extension"), Qt.LeftDockWidgetArea)

register()