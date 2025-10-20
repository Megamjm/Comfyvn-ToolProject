from PySide6.QtGui import QAction
# comfyvn/gui/asset_browser.py
# [Main window update chat]
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
class AssetBrowser(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Assets (stub)"))