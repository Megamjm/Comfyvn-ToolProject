from PySide6.QtGui import QAction
# comfyvn/gui/panels/settings_providers_view.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QHBoxLayout, QPushButton, QMessageBox
from comfyvn.core.settings_manager import SettingsManager
import json

class SettingsProvidersView(QWidget):
    # Plain JSON editor for provider configs. Validate/Apply/Revert supported.
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sm = SettingsManager()
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Remote GPU & Provider Settings (JSON)"))
        self.edit = QTextEdit(); v.addWidget(self.edit, 1)

        btns = QHBoxLayout(); v.addLayout(btns)
        self.btn_validate = QPushButton("Validate JSON")
        self.btn_load     = QPushButton("Revert")
        self.btn_save     = QPushButton("Apply")
        btns.addStretch(1); btns.addWidget(self.btn_load); btns.addWidget(self.btn_validate); btns.addWidget(self.btn_save)

        self.btn_validate.clicked.connect(self._validate)
        self.btn_save.clicked.connect(self.apply)
        self.btn_load.clicked.connect(self.revert)

        self.revert()

    def _validate(self):
        txt = self.edit.toPlainText()
        try:
            json.loads(txt or "{}")
            QMessageBox.information(self, "Providers", "Valid JSON.")
        except Exception as e:
            QMessageBox.critical(self, "Providers", f"Invalid JSON: {e}")

    def apply(self):
        cfg = self.sm.load()
        cfg["providers_json"] = self.edit.toPlainText()
        self.sm.save(cfg)
        QMessageBox.information(self, "Providers", "Saved provider configuration.")

    def revert(self):
        cfg = self.sm.load()
        txt = cfg.get("providers_json", "{\n  \"priority_order\": [\"local\"],\n  \"providers\": {}\n}")
        if not isinstance(txt, str):
            try:
                txt = json.dumps(txt, indent=2)
            except Exception:
                txt = "{}"
        self.edit.setPlainText(txt)