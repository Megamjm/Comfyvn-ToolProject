from PySide6.QtGui import QAction

# comfyvn/gui/core/dock_manager.py  [Studio-090]
from collections import defaultdict
from PySide6.QtWidgets import QDockWidget
from PySide6.QtCore import Qt


class DockManager:
    def __init__(self, window):
        self.window = window
        self._docks = {}
        self._area_map = defaultdict(list)

    def dock(self, widget, title: str, area=Qt.RightDockWidgetArea):
        if isinstance(widget, QDockWidget):
            dock = widget
        else:
            dock = QDockWidget(title, self.window)
            dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetMovable)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        existing = self._area_map.get(area)
        if existing:
            self.window.addDockWidget(area, dock)
            self.window.tabifyDockWidget(existing[-1], dock)
        else:
            self.window.addDockWidget(area, dock)
        dock.setFloating(False)
        self._docks[title] = dock
        self._area_map[area].append(dock)
        return dock

    def toggle(self, title: str):
        d = self._docks.get(title)
        if not d:
            return
        d.setVisible(not d.isVisible())
