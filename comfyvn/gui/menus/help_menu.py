# comfyvn/gui/menus/help_menu.py
import webbrowser, os
from PySide6.QtWidgets import QMessageBox
from comfyvn.gui.menus.menu_utils import make_action


def register_menu(window, menubar):
    menu = menubar.addMenu("Help")
    menu.addAction(
        make_action(
            "📖 Documentation",
            window,
            lambda: webbrowser.open_new_tab(
                "https://github.com/Megamjm/Comfyvn-ToolProject"
            ),
        )
    )
    menu.addAction(
        make_action(
            "🧾 Diagnostics Folder", window, lambda: os.startfile("./logs/diagnostics")
        )
    )
    about_act = make_action(
        "ℹ️ About",
        window,
        lambda: QMessageBox.information(
            window,
            "About ComfyVN",
            "ComfyVN Visual Novel Framework\nVersion 4.1 GUI Modular",
        ),
    )
    menu.addAction(about_act)
    return menu
