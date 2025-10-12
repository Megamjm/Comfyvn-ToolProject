# comfyvn/gui/menus/menu_playground.py
# [🎨 GUI Code Production Chat]
# Menu for Playground and LM Studio interactions

from PySide6.QtGui import QAction

def register_menu(parent):
    menu = parent.addMenu("&Playground")

    act_plan = QAction("Plan Scene (Server)", parent)
    act_apply = QAction("Apply Prompt (LM Studio)", parent)
    act_send = QAction("Send to SillyTavern", parent)

    act_plan.triggered.connect(lambda: print("[Menu] Plan Scene clicked"))
    act_apply.triggered.connect(lambda: print("[Menu] Apply Prompt clicked"))
    act_send.triggered.connect(lambda: print("[Menu] Send to SillyTavern clicked"))

    for a in (act_plan, act_apply, act_send):
        menu.addAction(a)
    return menu