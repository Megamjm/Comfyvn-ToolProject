# comfyvn/gui/menus/menu_system.py
# [🎨 GUI Code Production Chat]
# System-level tools and layout/profile menu

from PySide6.QtGui import QAction, QMessageBox

def register_menu(parent):
    menu = parent.addMenu("&System")

    def _about():
        QMessageBox.information(parent, "About ComfyVN",
            "ComfyVN v0.4-dev\nVisual Novel Studio Environment\n© ComfyVN Team")

    act_about = QAction("About ComfyVN", parent)
    act_about.triggered.connect(_about)

    act_reload = QAction("Reload Menus", parent)
    act_reload.triggered.connect(parent.parent()._reload_menus if hasattr(parent.parent(), "_reload_menus") else lambda: None)

    menu.addAction(act_reload)
    menu.addSeparator()
    menu.addAction(act_about)
    return menu