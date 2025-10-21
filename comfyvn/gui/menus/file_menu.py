import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
import json

# comfyvn/gui/menus/file_menu.py
from PySide6.QtWidgets import QMenu, QMessageBox

from comfyvn.config.runtime_paths import recent_projects_file
from comfyvn.gui.menus.menu_utils import make_action


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
    recents_path = recent_projects_file()

    def refresh_recent():
        recent.clear()
        if recents_path.exists():
            try:
                data = json.loads(recents_path.read_text(encoding="utf-8"))
            except Exception:
                data = []
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
