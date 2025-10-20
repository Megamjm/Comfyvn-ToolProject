from PySide6.QtGui import QAction
# comfyvn/gui/panels/roleplay_import_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from comfyvn.core.notifier import notifier

class RoleplayImportView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RoleplayImportView")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("RoleplayImportView"))
        btn = QPushButton("Ping Log"); btn.clicked.connect(lambda: notifier.toast("info", "RoleplayImportView ping"))
        lay.addWidget(btn)