from __future__ import annotations

import textwrap

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from comfyvn.core.settings_manager import SettingsManager

SECTION_ORDER = [
    "File",
    "Modules",
    "Spaces",
    "Tools",
    "Extensions",
    "Settings",
    "GPU",
    "Window",
    "Help",
]

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
        "Import Processing",
        "Audio",
        "Advisory",
        "System Status",
        "Log Hub",
    ],
    "Tools": [
        "Reload Menus",
        "Launch Detached Server",
        "External Tool Installer",
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


def _item_signature(item) -> tuple:
    return (
        item.label,
        item.handler or "",
        bool(getattr(item, "separator_before", False)),
        getattr(item, "order", None),
    )


def rebuild_menus_from_registry(window, registry):
    menubar = window.menuBar()
    if menubar is None:
        return

    sections = registry.by_section() if hasattr(registry, "by_section") else {}
    ordered_sections = []

    for section in SECTION_ORDER:
        items = sections.get(section, [])
        if not items:
            continue
        sorted_items = _sort_items(items, section)
        ordered_sections.append((section, sorted_items))

    signature = tuple(
        (section, tuple(_item_signature(item) for item in items))
        for section, items in ordered_sections
    )
    previous_signature = getattr(window, "_menu_signature", None)
    if previous_signature == signature:
        return

    menubar.clear()

    for section, sorted_items in ordered_sections:
        menu = menubar.addMenu(section)
        menu.setStyleSheet("QMenu { menu-scrollable: 1; }")
        last_sep = False
        for item in sorted_items:
            if getattr(item, "separator_before", False) and not last_sep:
                menu.addSeparator()
            display_label = _wrap_label(item.label)
            action = QAction(display_label, window)
            action.setProperty("_sourceLabel", item.label)
            if item.callback is not None:
                action.triggered.connect(lambda _, cb=item.callback: cb(window))
            else:
                handler = getattr(window, item.handler, None) if item.handler else None
                if callable(handler):
                    action.triggered.connect(handler)
            menu.addAction(action)
            last_sep = getattr(item, "separator_before", False)

    labels = [action.text().replace("&", "") for action in menubar.actions()]
    if __debug__:
        assert len(labels) == len(
            set(labels)
        ), f"Duplicate top-level menus detected: {labels}"
    setattr(window, "_menu_signature", signature)


def ensure_menu_bar(window):
    if not hasattr(window, "menuBar"):
        return
    menu_bar = window.menuBar()
    if menu_bar is None:
        return
    if getattr(window, "_menus_built", False):
        return
    menu_bar.clear()


def update_window_menu_state(window):
    """Placeholder hook for dynamic menu state updates."""
    if not hasattr(window, "menuBar"):
        return
    menu_bar = window.menuBar()
    if menu_bar is None:
        return
    _ = menu_bar.actions()


def _wrap_label(label: str, width: int = 32) -> str:
    if len(label) <= width:
        return label
    wrapped = textwrap.fill(label, width=width)
    return wrapped
