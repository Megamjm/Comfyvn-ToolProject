from PySide6.QtGui import QAction
# comfyvn/gui/panels/asset_browser_view.py.py
# [COMFYVN Architect | v1.0 | this chat]
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from comfyvn.core.notifier import notifier


class AssetBrowserView(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AssetBrowserView")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("AssetBrowserView"))
        btn = QPushButton("Ping Log")
        btn.clicked.connect(lambda: notifier.toast("info", "AssetBrowserView ping"))
        lay.addWidget(btn)
