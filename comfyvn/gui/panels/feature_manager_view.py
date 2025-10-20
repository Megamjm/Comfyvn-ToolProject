from PySide6.QtGui import QAction
# comfyvn/gui/panels/feature_manager_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from comfyvn.core.notifier import notifier

class FeatureManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FeatureManager")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("FeatureManager"))
        btn = QPushButton("Ping Log"); btn.clicked.connect(lambda: notifier.toast("info", "FeatureManager ping"))
        lay.addWidget(btn)