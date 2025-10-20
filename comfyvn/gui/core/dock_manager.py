from PySide6.QtGui import QAction

# comfyvn/gui/core/dock_manager.py  [Studio-090]
from PySide6.QtWidgets import QDockWidget
from PySide6.QtCore import Qt

class DockManager:
    def __init__(self, window):
        self.window = window
        self._docks = {}

    def dock(self, widget, title: str, area=Qt.RightDockWidgetArea):
        if isinstance(widget, QDockWidget):
            dock = widget
        else:
            dock = QDockWidget(title, self.window)
            dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.window.addDockWidget(area, dock)
        self._docks[title] = dock
        return dock

    def toggle(self, title: str):
        d = self._docks.get(title)
        if not d: return
        d.setVisible(not d.isVisible())