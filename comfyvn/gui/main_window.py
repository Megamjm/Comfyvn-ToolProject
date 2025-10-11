# comfyvn/gui/main_window.py
# 🎨 Main GUI updated for 🧍 Asset Manager with previews (ComfyVN_Architect)

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QAction
from gui.asset_browser import AssetBrowser


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyVN - Main Interface")
        self.resize(800, 600)

        menubar = self.menuBar()
        assets_menu = menubar.addMenu("Assets")

        open_assets_action = QAction("Open Asset Manager", self)
        open_assets_action.triggered.connect(self.open_asset_browser)
        assets_menu.addAction(open_assets_action)

        self.asset_browser = None

    def open_asset_browser(self):
        """Launch the Asset & Sprite System window."""
        if not self.asset_browser:
            self.asset_browser = AssetBrowser()
        self.asset_browser.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
