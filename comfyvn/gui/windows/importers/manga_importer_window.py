from __future__ import annotations

from PySide6.QtGui import QAction
# comfyvn/gui/windows/importers/manga_importer_window.py  [Phase 1.20]
from PySide6.QtWidgets import (QDialog, QFileDialog, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout)


class MangaImporterWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manga Importer")
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "Import manga folders or archives.\nPages will be converted into VN scenes/choices."
            )
        )
        btn = QPushButton("Choose Folder…")
        btn.clicked.connect(self._choose)
        lay.addWidget(btn)

    def _choose(self):
        from PySide6.QtWidgets import QFileDialog

        path = QFileDialog.getExistingDirectory(self, "Select Manga Folder")
        if not path:
            return
        # TODO: wire to importer pipeline
        QMessageBox.information(self, "Import", f"Queued manga folder: {path}")
