
# comfyvn/gui/main_window/quick_access_toolbar.py  [Studio-090]
from PySide6.QtWidgets import QToolBar
from PySide6.QtGui import QAction

class QuickAccessToolbarMixin:
    def _init_quick_toolbar(self):
        tb = QToolBar("Quick")
        tb.setMovable(False)
        self.addToolBar(tb)
        for label, fn in [
            ("Dashboard", getattr(self, "open_dashboard", lambda: None)),
            ("Assets", getattr(self, "open_assets", lambda: None)),
            ("GPU", getattr(self, "open_gpu_local", lambda: None)),
            ("Logs", getattr(self, "toggle_log_console", lambda: None)),
        ]:
            a = QAction(label, self)
            a.triggered.connect(fn)
            tb.addAction(a)