from PySide6.QtGui import QAction
# comfyvn/gui/panels/settings_hub_view.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QListWidget, QStackedWidget, QListWidgetItem, QVBoxLayout, QFrame, QPushButton
from PySide6.QtCore import Qt, Signal

class SettingsHub(QWidget):
    # Unified settings hub with section list left, panels right, footer with Apply/Revert.
    applied = Signal()
    reverted = Signal()

    def __init__(self, sections: dict[str, QWidget], parent=None):
        super().__init__(parent)
        self.sections = sections

        root = QHBoxLayout(self)
        root.setContentsMargins(8,8,8,8)
        root.setSpacing(8)

        self.list = QListWidget(self)
        self.list.setFixedWidth(220)
        self.stack = QStackedWidget(self)

        # Right container with stack + footer buttons
        right = QVBoxLayout()
        right.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0,0,0,0)
        footer.setSpacing(8)
        footer_frame = QFrame(); footer_frame.setLayout(footer)
        self.btn_apply = QPushButton("Apply")
        self.btn_revert = QPushButton("Revert")
        footer.addStretch(1)
        footer.addWidget(self.btn_revert)
        footer.addWidget(self.btn_apply)

        right.addWidget(footer_frame, 0)

        root.addWidget(self.list)
        root.addLayout(right, 1)

        for name, widget in self.sections.items():
            item = QListWidgetItem(name)
            self.list.addItem(item)
            self.stack.addWidget(widget)

        if self.list.count() > 0:
            self.list.setCurrentRow(0)

        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)

        self.btn_apply.clicked.connect(self._apply_all)
        self.btn_revert.clicked.connect(self._revert_all)

    def _apply_all(self):
        # Panels can implement an apply() method optionally
        for i in range(self.stack.count()):
            w = self.stack.widget(i)
            fn = getattr(w, "apply", None)
            if callable(fn):
                fn()
        self.applied.emit()

    def _revert_all(self):
        # Panels can implement a revert() method optionally
        for i in range(self.stack.count()):
            w = self.stack.widget(i)
            fn = getattr(w, "revert", None)
            if callable(fn):
                fn()
        self.reverted.emit()