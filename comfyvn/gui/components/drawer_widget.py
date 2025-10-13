# comfyvn/gui/components/drawer_widget.py
# 🧱 DrawerWidget — Animated collapsible panels with auto height (outer page scroll only)
# [COMFYVN Architect | settings_ui sync]

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QFrame, QSizePolicy


class DrawerWidget(QWidget):
    """Collapsible sections with height animation. No per-section scrollbars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.sections = []
        self._anims = []  # hold animations to avoid GC

    def add_section(self, title: str, widget: QWidget):
        header = QToolButton()
        header.setText(title)
        header.setCheckable(True)
        header.setChecked(False)
        header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        header.setArrowType(Qt.RightArrow)
        header.setStyleSheet(
            """
            QToolButton {
                font-weight: bold; padding: 6px 10px;
                border: 1px solid #555; border-radius: 6px;
                text-align: left; background-color: #2b2b2b; color: #ddd;
            }
            QToolButton:hover { background-color: #3c3c3c; }
        """
        )

        content_frame = QFrame()
        content_frame.setFrameShape(QFrame.StyledPanel)
        content_frame.setStyleSheet("background-color:#1e1e1e; border-radius:4px;")
        content_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(12, 8, 12, 8)
        content_layout.setSpacing(8)
        content_layout.addWidget(widget)

        # start closed
        content_frame.setMaximumHeight(0)
        content_frame.setVisible(False)

        self.layout.addWidget(header)
        self.layout.addWidget(content_frame)

        section = {"header": header, "content": content_frame}
        self.sections.append(section)
        header.toggled.connect(
            lambda checked, s=section: self._toggle_section(s, checked)
        )
        return section

    def _toggle_section(self, section, checked: bool):
        header = section["header"]
        content = section["content"]

        # compute natural height
        content.setVisible(True)
        content.adjustSize()
        target_height = content.sizeHint().height() if checked else 0

        anim = QPropertyAnimation(content, b"maximumHeight", self)
        anim.setDuration(220)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(content.maximumHeight())
        anim.setEndValue(target_height)

        self._anims.append(anim)

        def _cleanup():
            if not checked:
                content.setVisible(False)
            try:
                self._anims.remove(anim)
            except ValueError:
                pass

        anim.finished.connect(_cleanup)

        header.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        anim.start()

    def expand_all(self):
        for s in self.sections:
            if not s["header"].isChecked():
                s["header"].setChecked(True)

    def collapse_all(self):
        for s in self.sections:
            if s["header"].isChecked():
                s["header"].setChecked(False)
