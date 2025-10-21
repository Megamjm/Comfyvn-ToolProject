from __future__ import annotations

from PySide6.QtGui import QAction


def install_panels(main_window, base_url: str = "http://127.0.0.1:8001"):
    # Lazy imports to avoid hard deps if Qt variant changes
    try:
        from comfyvn.gui.widgets.flow_selector import FlowSelectorDock
        from comfyvn.gui.widgets.ops_panel import OpsPanelDock
    except Exception as e:
        print("[Panels] import failed:", e)
        return

    # Create or find docks
    mw = main_window
    docks = {
        d.objectName(): d for d in mw.findChildren(type(mw), lambda _: False)
    }  # noop, keep type checker happy

    fs = getattr(mw, "_dock_flow_selector", None)
    if fs is None or getattr(fs, "parent", lambda: None)() is None:
        fs = FlowSelectorDock(base_url, mw)
        setattr(mw, "_dock_flow_selector", fs)
        mw.addDockWidget(0x1, fs)  # LeftDockWidgetArea

    op = getattr(mw, "_dock_ops_panel", None)
    if op is None or getattr(op, "parent", lambda: None)() is None:
        op = OpsPanelDock(base_url, mw)
        setattr(mw, "_dock_ops_panel", op)
        mw.addDockWidget(0x2, op)  # RightDockWidgetArea

    # Add a Panels menu if missing
    try:
        mb = mw.menuBar()
        panels_menu = None
        for a in mb.actions():
            if a.text().strip().lower() == "panels":
                panels_menu = a.menu()
                break
        if panels_menu is None:
            panels_menu = mb.addMenu("Panels")
        act1 = panels_menu.addAction("Flow Selector")
        act2 = panels_menu.addAction("System Ops")
        act1.triggered.connect(lambda: fs.show())
        act2.triggered.connect(lambda: op.show())
    except Exception as e:
        print("[Panels] menu wiring failed:", e)
