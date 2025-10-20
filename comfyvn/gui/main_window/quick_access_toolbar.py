
# comfyvn/gui/main_window/quick_access_toolbar.py  [Studio-090]
from PySide6.QtWidgets import QToolBar
from PySide6.QtGui import QAction

class QuickAccessToolbarMixin:
    """Mixin to expose a Quick Access toolbar for frequently used actions."""

    def _ensure_quick_toolbar(self) -> QToolBar:
        toolbar = getattr(self, "_quick_toolbar", None)
        if toolbar is None:
            toolbar = QToolBar("Quick Access")
            toolbar.setMovable(False)
            self.addToolBar(toolbar)
            self._quick_toolbar = toolbar
        return toolbar

    def build_quick_access_toolbar(self, actions_iterable) -> None:
        """Populate quick access toolbar from Shortcut records."""
        toolbar = self._ensure_quick_toolbar()
        toolbar.clear()
        for action in actions_iterable:
            label = getattr(action, "label", None)
            handler_name = getattr(action, "handler", None)
            if not label or not handler_name:
                continue
            handler = getattr(self, handler_name, None)
            if not callable(handler):
                continue
            act = QAction(label, self)
            act.triggered.connect(handler)
            toolbar.addAction(act)

    def _init_quick_toolbar(self) -> None:
        """Legacy initializer for static buttons."""
        toolbar = self._ensure_quick_toolbar()
        for label, fn in [
            ("Dashboard", getattr(self, "open_dashboard", lambda: None)),
            ("Assets", getattr(self, "open_asset_browser", lambda: None)),
            ("GPU", getattr(self, "open_gpu_local", lambda: None)),
            ("Logs", getattr(self, "open_log_hub", lambda: None)),
        ]:
            action = QAction(label, self)
            action.triggered.connect(fn)
            toolbar.addAction(action)
