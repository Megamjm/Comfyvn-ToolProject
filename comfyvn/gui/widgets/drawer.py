from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


class Drawer(QWidget):
    """Simple collapsible drawer used to group related controls."""

    def __init__(
        self,
        title: str,
        content: QWidget,
        *,
        start_open: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._content = content

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toggle = QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.DownArrow if start_open else Qt.RightArrow)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(start_open)
        self._toggle.setStyleSheet("QToolButton { font-weight: bold; padding: 6px; }")
        self._toggle.clicked.connect(self._handle_toggle)

        frame = QFrame(self)
        frame.setFrameShape(QFrame.NoFrame)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 4, 0, 12)
        frame_layout.addWidget(content)

        layout.addWidget(self._toggle)
        layout.addWidget(frame)

        self._frame = frame
        if not start_open:
            self._frame.setVisible(False)

    def _handle_toggle(self) -> None:
        expanded = self._toggle.isChecked()
        self._frame.setVisible(expanded)
        self._toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)


class DrawerContainer(QWidget):
    """Vertical container that stacks drawers with consistent spacing."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addStretch(1)

    def add_drawer(self, drawer: Drawer) -> None:
        stretch_item = self._layout.takeAt(self._layout.count() - 1)
        self._layout.addWidget(drawer)
        if stretch_item:
            self._layout.addItem(stretch_item)

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
