from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable

from PySide6.QtGui import QAction

# comfyvn/core/module_discovery.py
# Dynamic menu discovery: reads extension manifests or Python MENU_HOOKS.


DYNAMIC_TAG = "dyn_menu_item"  # objectName used to track injected actions

DEFAULT_SEARCH_PATHS = [
    Path("extensions"),
    Path("comfyvn/modules"),
]


def _get_or_create_menu(window, path_parts: list[str]):
    """
    Ensure nested menu path exists. Return the final QMenu.
    Example: ["File", "Import"] => creates File -> Import submenu if missing.
    """
    mb = window.menuBar()
    current = None
    # top
    top_title = path_parts[0]
    # try to find existing top-level menu
    for a in mb.actions():
        m = a.menu()
        if m and m.title() == top_title:
            current = m
            break
    if current is None:
        current = mb.addMenu(top_title)
    # descend into submenus
    for part in path_parts[1:]:
        found = None
        for a in current.actions():
            m = a.menu()
            if m and m.title() == part:
                found = m
                break
        if found is None:
            found = current.addMenu(part)
        current = found
    return current


def inject_menu_item(
    window,
    menu_path: str,
    label: str,
    callback: Callable,
    *,
    shortcut: str | None = None,
    checkable: bool = False,
):
    """Insert one dynamic menu item."""
    parts = [p.strip() for p in menu_path.split("/") if p.strip()]
    if not parts:
        parts = ["Tools"]  # default bucket
    qmenu = _get_or_create_menu(window, parts)
    act = qmenu.addAction(label)
    act.setObjectName(DYNAMIC_TAG)
    if shortcut:
        act.setShortcut(shortcut)
    if checkable:
        act.setCheckable(True)
    try:
        act.triggered.connect(callback)  # type: ignore[attr-defined]
    except Exception:
        pass
    return act


def clear_dynamic_menus(window):
    """Remove previously injected dynamic actions to avoid duplicates."""
    mb = window.menuBar()
    for a in list(mb.actions()):
        m = a.menu()
        if not m:
            continue
        for act in list(m.actions()):
            if act.objectName() == DYNAMIC_TAG:
                m.removeAction(act)


def _load_manifest(fp: Path) -> list[dict]:
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("type") == "menu_hook":
            return [data]
        if isinstance(data, list):
            return [
                d for d in data if isinstance(d, dict) and d.get("type") == "menu_hook"
            ]
    except Exception:
        pass
    return []


def _resolve_callable(module_name: str, callable_name: str):
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, callable_name, None)
    except Exception:
        return None


def discover_menus(window, search_paths: Iterable[Path] = DEFAULT_SEARCH_PATHS):
    """
    Scan known locations for:
      1) manifest.json with {type:"menu_hook", menu,label,module,callable}
      2) Python modules exposing MENU_HOOKS = [{menu,label,callable:<callable>}]
    """
    # Avoid duplicates on multiple calls
    clear_dynamic_menus(window)

    # 1) Read manifests
    for base in search_paths:
        if not base.exists():
            continue
        for manifest in base.rglob("manifest.json"):
            for hook in _load_manifest(manifest):
                menu = hook.get("menu") or "Tools"
                label = hook.get("label") or "Unnamed"
                module = hook.get("module")
                callable_name = hook.get("callable")
                shortcut = hook.get("shortcut")
                if not module or not callable_name:
                    continue
                cb = _resolve_callable(module, callable_name)
                if cb:
                    inject_menu_item(window, menu, label, cb, shortcut=shortcut)

    # 2) Python MENU_HOOKS
    # modules can declare a global MENU_HOOKS = [{menu,label,callable}]
    candidates = [
        # add any fixed discovery points here if you like
    ]
    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
            hooks = getattr(mod, "MENU_HOOKS", [])
            for h in hooks:
                menu = h.get("menu") or "Tools"
                label = h.get("label") or "Unnamed"
                cb = h.get("callable")
                if cb:
                    inject_menu_item(window, menu, label, cb)
        except Exception:
            pass
