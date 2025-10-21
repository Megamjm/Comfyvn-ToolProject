import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/gui/menus/help_menu.py
import webbrowser

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from comfyvn.config.runtime_paths import diagnostics_dir
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

    def _open_diagnostics():
        target = diagnostics_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    menu.addAction(make_action("🧾 Diagnostics Folder", window, _open_diagnostics))
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
