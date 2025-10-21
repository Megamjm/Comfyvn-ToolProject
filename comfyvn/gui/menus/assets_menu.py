import logging

from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)
# comfyvn/gui/menus/assets_menu.py
from comfyvn.gui.menus.menu_utils import make_action


def register_menu(window, menubar):
    menu = menubar.addMenu("Assets")
    menu.addAction(
        make_action(
            "🖼 Asset Browser",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.assets_tab),
            "folder-pictures",
        )
    )
    menu.addAction(
        make_action(
            "🧍 Pose Manager",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.assets_tab),
            "user-identity",
        )
    )
    menu.addAction(
        make_action(
            "🎨 LoRA Manager",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.lora_tab),
            "color-management",
        )
    )
    return menu
