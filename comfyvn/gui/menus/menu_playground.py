# comfyvn/gui/menus/menu_playground.py
# 🎨 Playground Menu — LM Studio / ComfyUI Actions

from PySide6.QtGui import QAction


def register_menu(window, menubar):
    menu = menubar.addMenu("Playground")

    act_plan = QAction("🧠 Plan Scene (Server)", window)
    act_apply = QAction("✨ Apply Prompt (LM Studio)", window)
    act_send = QAction("📤 Send to SillyTavern", window)

    act_plan.triggered.connect(lambda: print("[Playground] Plan Scene clicked"))
    act_apply.triggered.connect(lambda: print("[Playground] Apply Prompt clicked"))
    act_send.triggered.connect(
        lambda: print("[Playground] Send to SillyTavern clicked")
    )

    for a in (act_plan, act_apply, act_send):
        menu.addAction(a)
    return menu
