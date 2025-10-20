from PySide6.QtGui import QAction

# comfyvn/gui/panels/settings_panel.py  [Studio-090]
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QPushButton, QDockWidget, QMessageBox, QComboBox
from PySide6.QtCore import Qt
from comfyvn.gui.services.server_bridge import ServerBridge
from comfyvn.core.settings_manager import SettingsManager

class SettingsPanel(QDockWidget):
    def __init__(self, bridge: ServerBridge):
        super().__init__("Settings")
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.bridge = bridge
        self.settings_manager = SettingsManager()
        w = QWidget(); form = QFormLayout(w)
        self.api = QLineEdit(self.bridge.base)
        self.remote_list = QLineEdit(self.bridge.get("REMOTE_GPU_LIST", default="http://127.0.0.1:8001"))
        self.menu_sort = QComboBox()
        self.menu_sort.addItem("Load order (default)", "load_order")
        self.menu_sort.addItem("Best practice structure", "best_practice")
        self.menu_sort.addItem("Alphabetical", "alphabetical")
        current_mode = self.settings_manager.load().get("ui", {}).get("menu_sort_mode", "load_order")
        index = self.menu_sort.findData(current_mode)
        if index != -1:
            self.menu_sort.setCurrentIndex(index)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._save)
        form.addRow("API Base:", self.api)
        form.addRow("Remote GPU Endpoints (comma):", self.remote_list)
        form.addRow("Menu Sort Order:", self.menu_sort)
        form.addRow(btn_save)
        self.setWidget(w)

    def _save(self):
        self.bridge.set_host(self.api.text().strip())
        ok = self.bridge.save_settings({
            "API_BASE": self.api.text().strip(),
            "REMOTE_GPU_LIST": self.remote_list.text().strip()
        })
        cfg = self.settings_manager.load()
        ui_cfg = cfg.get("ui", {})
        ui_cfg["menu_sort_mode"] = self.menu_sort.currentData()
        cfg["ui"] = ui_cfg
        self.settings_manager.save(cfg)
        parent = self.parent()
        if hasattr(parent, "reload_menus"):
            try:
                parent.reload_menus()
            except Exception:
                pass
        QMessageBox.information(self, "Settings", "Saved" if ok else "Failed")
