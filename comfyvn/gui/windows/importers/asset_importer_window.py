from __future__ import annotations

from PySide6.QtGui import QAction
# comfyvn/gui/windows/importers/asset_importer_window.py  [Phase 1.20]
from PySide6.QtWidgets import (QDialog, QFileDialog, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout)


class AssetImporterWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Asset Importer")
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "Import images / audio / sprites.\nImports to project asset registry."
            )
        )
        btn = QPushButton("Choose Files…")
        btn.clicked.connect(self._choose)
        lay.addWidget(btn)

    def _choose(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Assets",
            "",
            "Images/Audio (*.png *.jpg *.jpeg *.wav *.mp3 *.ogg);;All (*.*)",
        )
        if not files:
            return
        # TODO: wire to asset registry pipeline
        QMessageBox.information(self, "Import", f"Queued {len(files)} asset(s).")
