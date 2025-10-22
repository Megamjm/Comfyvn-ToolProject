# comfyvn/gui/core/dock_manager.py  [Studio-090]
import re
from collections import defaultdict
from functools import partial

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDockWidget, QMenu


class DockManager:
    def __init__(self, window):
        self.window = window
        self._docks = {}
        self._area_map = defaultdict(list)
        self._registered_names: set[str] = set()

    @staticmethod
    def _slug(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
        return slug or "dock"

    def _assign_object_name(self, dock: QDockWidget, title: str) -> None:
        if dock.objectName():
            self._registered_names.add(dock.objectName())
            return
        base = f"dock_{self._slug(title)}"
        candidate = base
        index = 1
        while candidate in self._registered_names or self.window.findChild(
            QDockWidget, candidate
        ):
            index += 1
            candidate = f"{base}_{index}"
        dock.setObjectName(candidate)
        self._registered_names.add(candidate)

    def _register_area(self, dock: QDockWidget, area: Qt.DockWidgetArea) -> None:
        for docks in self._area_map.values():
            if dock in docks:
                docks.remove(dock)
        self._area_map[area].append(dock)

    def _move_dock(self, dock: QDockWidget, area: Qt.DockWidgetArea) -> None:
        if dock is None:
            return
        current_area = self.window.dockWidgetArea(dock)
        if current_area == area:
            return
        self.window.addDockWidget(area, dock)
        self._register_area(dock, area)
        dock.setVisible(True)
        dock.raise_()

    def dock(self, widget, title: str, area=Qt.RightDockWidgetArea):
        if isinstance(widget, QDockWidget):
            dock = widget
        else:
            dock = QDockWidget(title, self.window)
            dock.setWidget(widget)
        self._assign_object_name(dock, dock.windowTitle() or title)
        dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
            | Qt.TopDockWidgetArea
            | Qt.BottomDockWidgetArea
        )
        dock.setContextMenuPolicy(Qt.CustomContextMenu)
        dock.customContextMenuRequested.connect(
            lambda pos, d=dock: self._dock_menu(d, pos)
        )
        existing = self._area_map.get(area)
        if existing:
            self.window.addDockWidget(area, dock)
            self.window.tabifyDockWidget(existing[-1], dock)
        else:
            self.window.addDockWidget(area, dock)
        dock.setFloating(False)
        self._docks[title] = dock
        self._register_area(dock, area)
        return dock

    def _dock_menu(self, dock: QDockWidget, pos: QPoint):
        menu = QMenu(dock)
        menu.addAction("Close", dock.close)
        move_menu = menu.addMenu("Move to Dock Area")
        for label, target_area in [
            ("Left", Qt.LeftDockWidgetArea),
            ("Right", Qt.RightDockWidgetArea),
            ("Top", Qt.TopDockWidgetArea),
            ("Bottom", Qt.BottomDockWidgetArea),
        ]:
            move_menu.addAction(label, partial(self._move_dock, dock, target_area))
        menu.exec(dock.mapToGlobal(pos))

    def toggle(self, title: str):
        d = self._docks.get(title)
        if not d:
            return
        d.setVisible(not d.isVisible())
