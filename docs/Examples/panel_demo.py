from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel

# extensions/panel_demo.py
# [COMFYVN Architect | v1.0 | this chat]
from comfyvn.core.core import hooks


def register():
    hooks.emit(
        "studio.register_panel",
        "Demo Panel",
        lambda: QLabel("Hi from extension"),
        Qt.LeftDockWidgetArea,
    )


register()
