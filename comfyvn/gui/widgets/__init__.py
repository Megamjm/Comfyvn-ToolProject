from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QSpacerItem,
                               QTextEdit, QVBoxLayout, QWidget)

# comfyvn/gui/widgets/__init__.py
# [Main window update chat] — shared widgets as a package


def HSpacer():
    return QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum)


def VSpacer():
    return QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding)


class Line(QFrame):
    def __init__(self, vertical: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.VLine if vertical else QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)


class SearchBox(QLineEdit):
    def __init__(self, placeholder: str = "Search…", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)


class SectionHeader(QWidget):
    def __init__(self, text: str = "Section", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lab = QLabel(text)
        lab.setProperty("class", "section-header")
        lay.addWidget(lab)
        lay.addItem(HSpacer())


class IconButton(QPushButton):
    def __init__(self, text: str = "", icon: QIcon | None = None, parent=None):
        super().__init__(text, parent)
        if icon:
            self.setIcon(icon)


class StatusBadge(QLabel):
    def __init__(self, text: str = "OK", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setProperty("class", "status-badge")


class BusyOverlay(QWidget):
    def __init__(self, text: str = "Working…", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(lab)
        lay.addStretch(1)


class ElideLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)


class LabeledAction(QWidget):
    def __init__(self, label: str, button_text: str = "Run", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.addWidget(QLabel(label))
        btn = QPushButton(button_text)
        lay.addWidget(btn)
        lay.addItem(HSpacer())


class FormRow(QWidget):
    def __init__(self, label: str, widget: QWidget | None = None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.addWidget(QLabel(label))
        lay.addWidget(widget or QWidget())
        lay.addItem(HSpacer())


class ToggleRow(FormRow):
    pass


class KVList(QWidget):
    def __init__(self, items: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        for k, v in (items or {}).items():
            row = QHBoxLayout()
            row.addWidget(QLabel(str(k)))
            row.addWidget(QLabel(str(v)))
            row.addItem(HSpacer())
            c = QWidget()
            c.setLayout(row)
            lay.addWidget(c)


KeyValueList = KVList
Pill = StatusBadge
HintLabel = QLabel
Toolbar = QWidget
PathPicker = QWidget
LogConsole = QTextEdit

__all__ = [
    "HSpacer",
    "VSpacer",
    "Line",
    "SearchBox",
    "SectionHeader",
    "IconButton",
    "StatusBadge",
    "BusyOverlay",
    "ElideLabel",
    "LabeledAction",
    "FormRow",
    "ToggleRow",
    "KVList",
    "KeyValueList",
    "Pill",
    "HintLabel",
    "Toolbar",
    "PathPicker",
    "LogConsole",
]


# Important: ignore dunder names so importlib doesn't trip (e.g., __path__)
def __getattr__(name: str):
    if name.startswith("_"):
        raise AttributeError(name)

    class _Fallback(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(kwargs.get("parent", None))
            lay = QVBoxLayout(self)
            lab = QLabel(name)
            lab.setAlignment(Qt.AlignCenter)
            lay.addWidget(lab)

    _Fallback.__name__ = name
    globals()[name] = _Fallback
    return _Fallback
