import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox

from comfyvn.config.runtime_paths import diagnostics_dir

# comfyvn/gui/menus/system_menu.py
from comfyvn.gui.menus.menu_utils import make_action


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
    menu.addAction(
        make_action(
            "🧩 Debug Integrations",
            window,
            window.open_debug_integrations,
        )
    )
    menu.addSeparator()

    def open_diagnostics():
        diag = diagnostics_dir("startup_report.json")
        if not diag.exists():
            QMessageBox.warning(window, "Diagnostics", "No startup diagnostics found.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(diag)))

    menu.addAction(
        make_action("🧾 Diagnostics Viewer", window, open_diagnostics, "text-x-generic")
    )
    return menu
