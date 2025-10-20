from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/gui/widgets/shortcut_capture.py
from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

# A line-edit that records the next keypress sequence (no free text).
class ShortcutCapture(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Press keys…")
        self.setReadOnly(True)
        self._seq = None

    def keyPressEvent(self, e):
        # build a normalized sequence (Ctrl/Alt/Shift/Meta + Key)
        seq = QKeySequence(e.modifiers() | e.key())
        text = seq.toString(QKeySequence.PortableText)
        # filter out "?" / empty / modifier-only
        if not text or text in ("?", "Ctrl", "Alt", "Shift", "Meta"):
            e.accept(); return
        self._seq = text
        self.setText(text)
        e.accept()

    def sequence(self) -> str | None:
        return self._seq