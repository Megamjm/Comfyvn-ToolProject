from PySide6.QtGui import QAction
# comfyvn/extensions/demo_importer/entry.py
from PySide6.QtWidgets import QMessageBox
def open_dialog():
    try:
        QMessageBox.information(None, "Demo Importer", "Hello from Demo Importer!")
    except Exception:
        pass