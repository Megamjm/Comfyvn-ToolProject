from PySide6.QtGui import QAction
# comfyvn/extensions/demo_tool/entry.py
from PySide6.QtWidgets import QMessageBox


def run_tool():
    try:
        QMessageBox.information(None, "Demo Tool", "Demo Tool executed.")
    except Exception:
        pass
