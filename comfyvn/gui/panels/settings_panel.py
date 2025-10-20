from PySide6.QtGui import QAction

# comfyvn/gui/panels/settings_panel.py  [Studio-090]
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QPushButton, QDockWidget, QMessageBox
from PySide6.QtCore import Qt
from comfyvn.gui.services.server_bridge import ServerBridge

class SettingsPanel(QDockWidget):
    def __init__(self, bridge: ServerBridge):
        super().__init__("Settings")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.bridge = bridge
        w = QWidget(); form = QFormLayout(w)
        self.api = QLineEdit(self.bridge.base)
        self.remote_list = QLineEdit(self.bridge.get("REMOTE_GPU_LIST", default="http://127.0.0.1:8001"))
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._save)
        form.addRow("API Base:", self.api)
        form.addRow("Remote GPU Endpoints (comma):", self.remote_list)
        form.addRow(btn_save)
        self.setWidget(w)

    def _save(self):
        self.bridge.set_host(self.api.text().strip())
        ok = self.bridge.save_settings({
            "API_BASE": self.api.text().strip(),
            "REMOTE_GPU_LIST": self.remote_list.text().strip()
        })
        QMessageBox.information(self, "Settings", "Saved" if ok else "Failed")