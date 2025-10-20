
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

SECTION_ORDER = ["File","View","Spaces","Tools","GPU","Window","Help"]

def rebuild_menus_from_registry(w, registry):
    mb = w.menuBar()
    # clear existing top-level menus (non-destructive for QMainWindow)
    for m in list(mb.findChildren(QMenu)):
        mb.removeAction(m.menuAction())
    # build by section
    by = registry.by_section() if hasattr(registry,"by_section") else {}
    for sec in SECTION_ORDER:
        items = by.get(sec, [])
        if not items: continue
        m = mb.addMenu(sec)
        last_sep = False
        for it in items:
            if getattr(it, "separator_before", False) and not last_sep:
                m.addSeparator()
            a = QAction(it.label, w)
            # hook action to method on window if present
            handler = getattr(w, it.handler, None)
            if callable(handler):
                a.triggered.connect(handler)
            m.addAction(a)
            last_sep = getattr(it, "separator_before", False)

# Dynamic menus are handled by comfyvn.core.menu_runtime_bridge
def ensure_menu_bar(window):
    try:
        window._build_menus_from_registry()
    except Exception:
        pass


def update_window_menu_state(window):
    """Placeholder for dynamic menu state refresh; ensures menus exist even if no runtime bridge."""
    if not hasattr(window, "menuBar"):
        return
    menu_bar = window.menuBar()
    if menu_bar is None:
        return
    # No-op for now; hook for future enable/disable logic
    _ = menu_bar.actions()
