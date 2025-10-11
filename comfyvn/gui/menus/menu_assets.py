# comfyvn/gui/menus/menu_assets.py
# [🎨 GUI Code Production Chat]
# Menu for asset import/export and cache operations

from PySide6.QtWidgets import QAction

def register_menu(parent):
    menu = parent.addMenu("&Assets")

    act_import = QAction("Import Asset", parent)
    act_export = QAction("Export Scene", parent)
    act_refresh = QAction("Refresh Assets", parent)

    act_import.triggered.connect(lambda: print("[Menu] Import Asset clicked"))
    act_export.triggered.connect(lambda: print("[Menu] Export Scene clicked"))
    act_refresh.triggered.connect(lambda: print("[Menu] Refresh Assets clicked"))

    for a in (act_import, act_export, act_refresh):
        menu.addAction(a)
    return menu
