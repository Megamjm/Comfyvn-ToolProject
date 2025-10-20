from PySide6.QtGui import QAction
# comfyvn/gui/panels/settings_workspace_view.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox, QHBoxLayout, QSpinBox
from comfyvn.core.settings_manager import SettingsManager

class SettingsWorkspaceView(QWidget):
    # Autosave toggle + interval (seconds).
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sm = SettingsManager()
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Workspace"))
        self.chk_autosave = QCheckBox("Enable autosave")
        row = QHBoxLayout()
        row.addWidget(QLabel("Autosave interval (seconds):"))
        self.spin_interval = QSpinBox(); self.spin_interval.setRange(5, 3600); self.spin_interval.setSingleStep(5)
        row.addWidget(self.spin_interval)
        v.addWidget(self.chk_autosave)
        v.addLayout(row)
        v.addStretch(1)
        self.revert()

    def apply(self):
        cfg = self.sm.load()
        ws  = cfg.setdefault("workspace", {})
        ws["autosave"] = bool(self.chk_autosave.isChecked())
        ws["autosave_interval"] = int(self.spin_interval.value())
        self.sm.save(cfg)

    def revert(self):
        cfg = self.sm.load()
        ws  = cfg.get("workspace", {})
        self.chk_autosave.setChecked(bool(ws.get("autosave", True)))
        self.spin_interval.setValue(int(ws.get("autosave_interval", 60)))