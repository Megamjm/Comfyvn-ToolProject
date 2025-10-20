from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/gui/menus/system_menu.py
from comfyvn.gui.menus.menu_utils import make_action
from PySide6.QtWidgets import QFileDialog, QMessageBox
import os  # <-- added


def register_menu(window, menubar):
    menu = menubar.addMenu("System")
    menu.addAction(
        make_action(
            "⚙ System Control",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.server_control_tab),
        )
    )
    menu.addAction(make_action("🧠 Server Console", window))
    menu.addAction(
        make_action(
            "🪄 Settings",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.settings_tab),
        )
    )
    menu.addSeparator()

    def open_diagnostics():
        diag = "./logs/diagnostics/startup_report.json"
        if not os.path.exists(diag):
            QMessageBox.warning(window, "Diagnostics", "No startup diagnostics found.")
            return
        os.startfile(diag)

    menu.addAction(
        make_action("🧾 Diagnostics Viewer", window, open_diagnostics, "text-x-generic")
    )
    return menu