from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/windows/importers/vn_importer_window.py  [Phase 1.20]
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox

class VNImporterWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VN Importer")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Import .pak / zip visual novels.\nThis will extract assets, scenarios, characters."))
        btn = QPushButton("Choose File…")
        btn.clicked.connect(self._choose)
        lay.addWidget(btn)

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select VN Package", "", "Packages (*.pak *.zip);;All (*.*)")
        if not path: return
        # TODO: wire to importer pipeline
        QMessageBox.information(self, "Import", f"Queued import: {path}")