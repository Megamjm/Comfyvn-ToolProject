from PySide6.QtGui import QAction
# comfyvn/gui/panels/settings_commands_view.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QPushButton, QHBoxLayout, QMessageBox
from comfyvn.core.command_registry import registry

class SettingsCommandsView(QWidget):
    # Shows all registered commands and allows executing selected.
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Registered Commands"))
        self.list = QListWidget(); v.addWidget(self.list, 1)
        row = QHBoxLayout(); v.addLayout(row)
        self.btn_run = QPushButton("Run Selected")
        row.addStretch(1); row.addWidget(self.btn_run)
        self.btn_run.clicked.connect(self._run)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for cid, cmd in registry.list().items():
            label = f"{cmd.title or cid}   [{cid}]"
            if cmd.shortcut:
                label += f"  ⌨ {cmd.shortcut}"
            self.list.addItem(label)

    def _run(self):
        it = self.list.currentItem()
        if not it: return
        text = it.text()
        if "[" in text and "]" in text:
            cid = text[text.rfind("[")+1:text.rfind("]")].strip()
            try:
                registry.run(cid)
            except Exception as e:
                QMessageBox.critical(self, "Command", str(e))