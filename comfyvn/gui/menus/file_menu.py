from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/gui/menus/file_menu.py
from PySide6.QtWidgets import QMenu
from comfyvn.gui.menus.menu_utils import make_action
import json, os
from PySide6.QtWidgets import QMessageBox


def register_menu(window, menubar):
    menu = menubar.addMenu("File")

    menu.addAction(
        make_action(
            "🆕 New Project", window, window.new_project, "document-new", "Ctrl+N"
        )
    )
    menu.addAction(
        make_action(
            "📂 Open Project", window, window.open_project, "document-open", "Ctrl+O"
        )
    )

    # --- Recent Projects ---
    recent = QMenu("Open Recent", window)
    menu.addMenu(recent)
    recents_path = "./logs/recent_projects.json"

    def refresh_recent():
        recent.clear()
        if os.path.exists(recents_path):
            data = json.load(open(recents_path))
            for path in data[-10:]:
                recent.addAction(
                    make_action(
                        path, window, lambda _, p=path: window.open_project_path(p)
                    )
                )

    refresh_recent()

    menu.addSeparator()
    menu.addAction(
        make_action(
            "💾 Save Snapshot", window, window.save_snapshot, "document-save", "Ctrl+S"
        )
    )
    menu.addAction(
        make_action(
            "♻️ Restore Snapshot",
            window,
            window.restore_snapshot,
            "document-revert",
            "Ctrl+R",
        )
    )
    menu.addSeparator()
    menu.addAction(
        make_action("❌ Exit", window, window.close, "application-exit", "Ctrl+Q")
    )

    return menu