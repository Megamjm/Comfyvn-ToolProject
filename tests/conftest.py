from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_pyside6_stub() -> bool:
    try:
        import PySide6  # type: ignore  # noqa: F401

        try:
            import PySide6.QtCore  # type: ignore  # noqa: F401
            import PySide6.QtGui  # type: ignore  # noqa: F401
            import PySide6.QtWidgets  # type: ignore  # noqa: F401

            return False
        except Exception:  # noqa: BLE001 - Qt backend missing system deps
            for name in list(sys.modules):
                if name == "PySide6" or name.startswith("PySide6."):
                    sys.modules.pop(name, None)
            raise
    except Exception:  # noqa: BLE001 - fallback to stub on any import failure
        pass

    class _Signal:
        def __init__(self):
            self._slots = []

        def connect(self, slot):
            if callable(slot):
                self._slots.append(slot)

        def emit(self, *args, **kwargs):
            for slot in list(self._slots):
                slot(*args, **kwargs)

    class Signal:
        def __init__(self, *signature: object):
            self._name = None

        def __set_name__(self, owner, name):
            self._name = name

        def __get__(self, instance, owner):
            if instance is None:
                return self
            sig = instance.__dict__.get(self._name)
            if sig is None:
                sig = _Signal()
                instance.__dict__[self._name] = sig
            return sig

    class QObject:
        def __init__(self, parent=None):
            self._parent = parent

    class QAction(QObject):
        def __init__(self, text: str = "", parent=None):
            super().__init__(parent)
            self.text = text
            self.triggered = _Signal()

        def setShortcut(self, *_):
            return None

        def setIcon(self, *_):
            return None

        def setObjectName(self, *_):
            return None

    class Qt:
        LeftDockWidgetArea = 1
        RightDockWidgetArea = 2
        BottomDockWidgetArea = 4
        Tool = 8
        FramelessWindowHint = 16
        WindowStaysOnTopHint = 32
        WA_TranslucentBackground = 64
        WA_ShowWithoutActivating = 128
        AlignRight = 256

    class QTimer(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.timeout = _Signal()

        def start(self, *_):
            return None

        def stop(self):
            return None

        @staticmethod
        def singleShot(_msec: int, callback):
            if callable(callback):
                callback()

    class QApplication:
        _instance = None

        def __init__(self, *args, **kwargs):
            QApplication._instance = self
            self.args = args
            self.kwargs = kwargs

        @classmethod
        def instance(cls):
            return cls._instance

        def exec(self):
            return 0

        def quit(self):
            return None

    class QWidget(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._visible = False

        def setParent(self, parent):
            self._parent = parent

        def parent(self):
            return self._parent

        def setVisible(self, visible: bool):
            self._visible = bool(visible)

        def isVisible(self) -> bool:
            return self._visible

        def show(self):
            self.setVisible(True)

        def close(self):
            self.setVisible(False)

        def setWindowTitle(self, *_):
            return None

        def resize(self, *_):
            return None

        def setLayout(self, *_):
            return None

        def setStyleSheet(self, *_):
            return None

        def setWordWrap(self, *_):
            return None

        def setToolTip(self, *_):
            return None

        def setAttribute(self, *_):
            return None

        def setWindowFlags(self, *_):
            return None

        def move(self, *_):
            return None

        def geometry(self):
            return types.SimpleNamespace(
                x=lambda: 0,
                y=lambda: 0,
                width=lambda: 0,
                height=lambda: 0,
            )

        def __getattr__(self, _name):
            def _noop(*args, **kwargs):
                return None

            return _noop

    class QDockWidget(QWidget):
        DockWidgetMovable = 1

        def __init__(self, title="", parent=None):
            super().__init__(parent)
            self._title = title
            self._widget = None

        def setWidget(self, widget):
            self._widget = widget

        def widget(self):
            return self._widget

        def setFeatures(self, *_):
            return None

        def setAllowedAreas(self, *_):
            return None

        def setFloating(self, *_):
            return None

        def raise_(self):
            return None

    class QMenu(QWidget):
        def __init__(self, title="", parent=None):
            super().__init__(parent)
            self.title = title
            self.actions = []

        def addAction(self, action):
            self.actions.append(action)
            return action

    class QMenuBar(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._menus = []

        def addMenu(self, title):
            menu = QMenu(title, self)
            self._menus.append(menu)
            return menu

    class QStatusBar(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._message = ""
            self._widgets = []

        def showMessage(self, message, *_):
            self._message = message

        def addPermanentWidget(self, widget, *_):
            self._widgets.append(widget)

    class QMainWindow(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._central = None
            self._menubar = None
            self._status = None
            self._docks = []

        def setCentralWidget(self, widget):
            self._central = widget

        def setMenuBar(self, menu):
            self._menubar = menu

        def menuBar(self):
            return self._menubar

        def setStatusBar(self, status):
            self._status = status

        def statusBar(self):
            return self._status

        def addDockWidget(self, *_):
            return None

        def tabifyDockWidget(self, *_):
            return None

        def saveState(self):
            return QByteArray(b"stub_state")

        def restoreState(self, *_):
            return True

    class QLabel(QWidget):
        def __init__(self, text="", parent=None):
            super().__init__(parent)
            self._text = text

        def setText(self, text):
            self._text = text

        def text(self):
            return self._text

    class QListWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._items = []

        def addItem(self, item):
            self._items.append(item)

        def clear(self):
            self._items.clear()

        def count(self):
            return len(self._items)

    class QPushButton(QWidget):
        def __init__(self, text="", parent=None):
            super().__init__(parent)
            self.text = text
            self.clicked = _Signal()

        def click(self):
            self.clicked.emit()

    class QLayout:
        def __init__(self, parent=None):
            self.parent = parent
            self.children = []

        def addWidget(self, widget, *_):
            self.children.append(widget)

        def addLayout(self, layout, *_):
            self.children.append(layout)

        def addStretch(self, *_):
            return None

        def setContentsMargins(self, *_):
            return None

        def setSpacing(self, *_):
            return None

        def removeWidget(self, widget):
            if widget in self.children:
                self.children.remove(widget)

        def __getattr__(self, _name):
            def _noop(*args, **kwargs):
                return None

            return _noop

    class QVBoxLayout(QLayout):
        pass

    class QHBoxLayout(QLayout):
        pass

    class QByteArray:
        def __init__(self, data: bytes = b""):
            self._data = bytes(data)

        def data(self):
            return self._data

        @classmethod
        def fromHex(cls, data: bytes):
            return cls(bytes.fromhex(data.decode("utf-8")))

    class QUrl:
        def __init__(self, url: str = ""):
            self.url = url

    class QDesktopServices:
        @staticmethod
        def openUrl(_url):
            return True

    class QSettings:
        _store = {}

        def __init__(self, *args, **kwargs):
            self._namespace = "::".join(str(arg) for arg in args) or "default"

        def value(self, key, default=None):
            return self._store.get((self._namespace, key), default)

        def setValue(self, key, value):
            self._store[(self._namespace, key)] = value

    class QFileDialog:
        @staticmethod
        def getOpenFileName(*_, **__):
            return ("", "")

    class QMessageBox:
        @staticmethod
        def information(*_, **__):
            return 0

        @staticmethod
        def warning(*_, **__):
            return 0

        @staticmethod
        def critical(*_, **__):
            return 0

    stub = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Signal = Signal
    qtcore.QObject = QObject
    qtcore.QTimer = QTimer
    qtcore.QSettings = QSettings
    qtcore.QByteArray = QByteArray
    qtcore.QUrl = QUrl
    qtcore.Qt = Qt

    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = QAction
    qtgui.QDesktopServices = QDesktopServices

    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    qtwidgets.QApplication = QApplication
    qtwidgets.QWidget = QWidget
    qtwidgets.QDockWidget = QDockWidget
    qtwidgets.QMainWindow = QMainWindow
    qtwidgets.QMenuBar = QMenuBar
    qtwidgets.QMenu = QMenu
    qtwidgets.QStatusBar = QStatusBar
    qtwidgets.QLabel = QLabel
    qtwidgets.QListWidget = QListWidget
    qtwidgets.QPushButton = QPushButton
    qtwidgets.QVBoxLayout = QVBoxLayout
    qtwidgets.QHBoxLayout = QHBoxLayout
    qtwidgets.QFileDialog = QFileDialog
    qtwidgets.QMessageBox = QMessageBox

    def _attr_factory(module, base):
        def _getattr(name):
            if name.startswith("__"):
                raise AttributeError(name)
            cls = type(name, (base,), {})
            setattr(module, name, cls)
            return cls

        return _getattr

    qtwidgets.__getattr__ = _attr_factory(qtwidgets, QWidget)  # type: ignore[attr-defined]
    qtgui.__getattr__ = _attr_factory(qtgui, QObject)  # type: ignore[attr-defined]
    qtcore.__getattr__ = _attr_factory(qtcore, QObject)  # type: ignore[attr-defined]

    stub.QtCore = qtcore
    stub.QtGui = qtgui
    stub.QtWidgets = qtwidgets
    stub.__dict__.update({"QtCore": qtcore, "QtGui": qtgui, "QtWidgets": qtwidgets})
    stub.__comfyvn_stub__ = True

    sys.modules["PySide6"] = stub
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    sys.modules["PySide6.QtWidgets"] = qtwidgets
    return True


USING_QT_STUB = _install_pyside6_stub()


def pytest_collection_modifyitems(config, items):  # noqa: D401 - pytest hook
    if not USING_QT_STUB:
        return
    skip_reason = pytest.mark.skip(reason="PySide6 backend unavailable in test runner")
    xfail_marker = pytest.mark.xfail(reason="PySide6 backend unavailable", run=False)
    for item in items:
        if item.nodeid.startswith("tests/test_gui_mainwindow_headless.py"):
            skip_reason(item)
            item.add_marker(xfail_marker)


def pytest_ignore_collect(collection_path, path=None, config=None):  # noqa: D401
    if not USING_QT_STUB:
        return False
    candidate = getattr(collection_path, "name", None)
    if candidate is None and hasattr(collection_path, "basename"):
        candidate = collection_path.basename
    return candidate == "test_gui_mainwindow_headless.py"
