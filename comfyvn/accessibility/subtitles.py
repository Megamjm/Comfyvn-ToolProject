from __future__ import annotations

from typing import Optional

try:
    from PySide6.QtCore import Qt  # type: ignore
    from PySide6.QtGui import QFont  # type: ignore
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget  # type: ignore
except Exception:  # pragma: no cover - defensive stubs for non-GUI usage
    Qt = None  # type: ignore
    QFont = None  # type: ignore
    QLabel = None  # type: ignore
    QVBoxLayout = None  # type: ignore
    QWidget = object  # type: ignore


if QWidget is object:  # pragma: no cover - stub fallback

    class SubtitleOverlay:  # type: ignore[override]
        def __init__(self, *_args, **_kwargs) -> None:
            self._enabled = False
            self._text = ""

        def update_state(
            self,
            *,
            enabled: bool,
            text: str,
            font_scale: float = 1.0,
            origin: Optional[str] = None,
        ) -> None:
            self._enabled = enabled
            self._text = text

        def current_text(self) -> str:
            return self._text

else:

    class SubtitleOverlay(QWidget):
        """Bottom-aligned subtitle overlay that honours accessibility settings."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self._enabled = True
            self._text = ""

            layout = QVBoxLayout(self)
            layout.setContentsMargins(24, 24, 24, 24)
            layout.setSpacing(0)
            layout.addStretch(1)

            container = QWidget(self)
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(18, 14, 18, 12)
            container_layout.setSpacing(4)

            self._title = QLabel("")
            self._title.setObjectName("SubtitleOverlayOrigin")
            self._title.setVisible(False)
            self._title.setStyleSheet(
                "color: #BFC9D9; font-size: 13px; font-weight: 600; text-transform: uppercase;"
            )

            self._label = QLabel("")
            self._label.setObjectName("SubtitleOverlayText")
            self._label.setWordWrap(True)
            self._label.setStyleSheet(
                "color: #FFFFFF; font-size: 18px; font-weight: 500; line-height: 150%;"
            )

            container_layout.addWidget(self._title)
            container_layout.addWidget(self._label)
            container.setLayout(container_layout)
            container.setStyleSheet(
                """
                QWidget#SubtitleOverlayContainer {
                    background-color: rgba(12, 22, 36, 210);
                    border-radius: 12px;
                    border: 1px solid rgba(191, 201, 217, 60);
                }
                """
            )
            container.setObjectName("SubtitleOverlayContainer")

            layout.addWidget(container, alignment=Qt.AlignBottom)
            self.setLayout(layout)
            self.hide()

        def current_text(self) -> str:
            return self._text

        def update_state(
            self,
            *,
            enabled: bool,
            text: str,
            font_scale: float = 1.0,
            origin: Optional[str] = None,
        ) -> None:
            clean = (text or "").strip()
            self._enabled = bool(enabled)
            self._text = clean
            if not self._enabled or not clean:
                self.hide()
                return

            if origin:
                self._title.setText(origin.upper())
                self._title.setVisible(True)
            else:
                self._title.setVisible(False)
            self._label.setText(clean)

            if QFont is not None:
                base_size = 18.0
                size = max(12.0, base_size * max(0.6, font_scale))
                font = self._label.font()
                font.setPointSizeF(size)
                self._label.setFont(font)

            self.show()
            self.raise_()


__all__ = ["SubtitleOverlay"]
