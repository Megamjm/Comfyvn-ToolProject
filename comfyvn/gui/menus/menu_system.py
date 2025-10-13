# comfyvn/gui/menus/menu_system.py
# 🧩 System Menu — Internal reloads, info, and maintenance

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMessageBox


def register_menu(window, menubar):
    menu = menubar.addMenu("System")

    def _about():
        QMessageBox.information(
            window,
            "About ComfyVN",
            "ComfyVN v4.0-dev\nVisual Novel Studio Environment\n© ComfyVN Team",
        )

    act_reload = QAction("🔁 Reload Menus", window)
    act_reload.triggered.connect(
        lambda: window.menu_bar.load_menus() if hasattr(window, "menu_bar") else None
    )

    act_about = QAction("ℹ️ About ComfyVN", window)
    act_about.triggered.connect(_about)

    menu.addAction(act_reload)
    menu.addSeparator()
    menu.addAction(act_about)
    return menu
