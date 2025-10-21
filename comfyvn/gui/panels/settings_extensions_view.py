from PySide6.QtGui import QAction
# comfyvn/gui/panels/settings_extensions_view.py
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from comfyvn.core.extension_loader import reload_extensions
from comfyvn.core.extension_runtime import runtime


class SettingsExtensionsView(QWidget):
    # Simple manager: list + reload button.
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Installed Extensions"))
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        v.addLayout(row)
        self.btn_reload = QPushButton("Reload Extensions")
        row.addStretch(1)
        row.addWidget(self.btn_reload)

        self.btn_reload.clicked.connect(self._reload)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for ext_id, inst in runtime.extensions.items():
            self.list.addItem(
                f"{inst.manifest.name} ({ext_id})  v{inst.manifest.version}"
            )

    def _reload(self):
        try:
            reload_extensions(ctx=None)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Extensions", str(e))
