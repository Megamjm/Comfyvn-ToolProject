# comfyvn/gui/menus/scenes_menu.py
from comfyvn.gui.menus.menu_utils import make_action


def register_menu(window, menubar):
    menu = menubar.addMenu("Scenes")
    menu.addAction(
        make_action(
            "🧪 Playground",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.playground_tab),
        )
    )
    menu.addAction(
        make_action(
            "🧩 Roleplay Import",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.role_import_tab),
        )
    )
    menu.addAction(
        make_action(
            "🎬 Roleplay Preview",
            window,
            lambda: window.main_tabs.setCurrentWidget(window.role_preview_tab),
        )
    )
    return menu
