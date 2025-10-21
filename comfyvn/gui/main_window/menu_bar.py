
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from comfyvn.core.settings_manager import SettingsManager

SECTION_ORDER = ["File", "Modules", "Spaces", "Tools", "Extensions", "Settings", "GPU", "Window", "Help"]

BEST_PRACTICE_SECTION_ITEMS = {
    "File": [
        "Open Projects Folder",
        "Open Data Folder",
        "Open Logs Folder",
        "Exit",
    ],
    "Modules": [
        "Studio Center",
        "Scenes",
        "Characters",
        "Assets",
        "Playground",
        "Timeline",
        "Imports",
        "Audio",
        "Advisory",
        "System Status",
        "Log Hub",
    ],
    "Tools": [
        "Reload Menus",
        "Launch Detached Server",
        "Install Base Scripts",
    ],
    "Extensions": [
        "Reload Extensions",
        "Open Extensions Folder",
    ],
    "Settings": [
        "Settings Panel",
    ],
}

_settings_manager = SettingsManager()


def _get_menu_sort_mode() -> str:
    cfg = _settings_manager.load()
    ui_cfg = cfg.get("ui", {})
    return ui_cfg.get("menu_sort_mode", "load_order")


def _sort_items(items, section: str):
    mode = _get_menu_sort_mode()
    enumerated = list(enumerate(items))

    if mode == "alphabetical":
        enumerated.sort(key=lambda pair: pair[1].label.lower())
    elif mode == "best_practice":
        order_map = {
            label: idx
            for idx, label in enumerate(BEST_PRACTICE_SECTION_ITEMS.get(section, []))
        }

        def key(pair):
            idx, item = pair
            if item.order is not None:
                return (0, item.order, idx)
            if item.label in order_map:
                return (1, order_map[item.label], idx)
            return (2, idx)

        enumerated.sort(key=key)
    else:  # load_order (default)
        def key(pair):
            idx, item = pair
            priority = item.order if item.order is not None else 1_000_000
            return (priority, idx)

        enumerated.sort(key=key)

    return [item for _, item in enumerated]


def rebuild_menus_from_registry(window, registry):
    menubar = window.menuBar()
    menubar.clear()

    sections = registry.by_section() if hasattr(registry, "by_section") else {}

    for section in SECTION_ORDER:
        items = sections.get(section, [])
        if not items:
            continue
        sorted_items = _sort_items(items, section)
        menu = menubar.addMenu(section)
        last_sep = False
        for item in sorted_items:
            if getattr(item, "separator_before", False) and not last_sep:
                menu.addSeparator()
            action = QAction(item.label, window)
            if item.callback is not None:
                action.triggered.connect(lambda _, cb=item.callback: cb(window))
            else:
                handler = getattr(window, item.handler, None) if item.handler else None
                if callable(handler):
                    action.triggered.connect(handler)
            menu.addAction(action)
            last_sep = getattr(item, "separator_before", False)


def ensure_menu_bar(window):
    try:
        window._build_menus_from_registry()
    except Exception:
        pass


def update_window_menu_state(window):
    """Placeholder hook for dynamic menu state updates."""
    if not hasattr(window, "menuBar"):
        return
    menu_bar = window.menuBar()
    if menu_bar is None:
        return
    _ = menu_bar.actions()
