from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

try:  # GUI dependencies are optional in headless contexts.
    from PySide6.QtCore import Qt  # type: ignore
    from PySide6.QtGui import QColor, QPainter  # type: ignore
    from PySide6.QtWidgets import QWidget  # type: ignore
except Exception:  # pragma: no cover - defensive stubs for non-GUI usage
    Qt = None  # type: ignore
    QColor = None  # type: ignore
    QPainter = None  # type: ignore
    QWidget = object  # type: ignore


@dataclass(frozen=True)
class FilterPass:
    color: Tuple[int, int, int, int]
    composition: str
    opacity: float = 1.0


@dataclass(frozen=True)
class FilterSpec:
    key: str
    label: str
    description: str
    passes: Tuple[FilterPass, ...] = ()


def _comp(name: str) -> int:
    if QPainter is None:
        return 0
    mapping = {
        "sourceover": QPainter.CompositionMode_SourceOver,
        "multiply": QPainter.CompositionMode_Multiply,
        "screen": QPainter.CompositionMode_Screen,
        "overlay": QPainter.CompositionMode_Overlay,
        "soft_light": QPainter.CompositionMode_SoftLight,
        "hard_light": QPainter.CompositionMode_HardLight,
        "color": QPainter.CompositionMode_Color,
        "saturation": QPainter.CompositionMode_Saturation,
        "luminosity": QPainter.CompositionMode_Luminosity,
        "difference": QPainter.CompositionMode_Difference,
        "exclusion": QPainter.CompositionMode_Exclusion,
    }
    return mapping.get(name.lower(), QPainter.CompositionMode_SourceOver)


def _qcolor(rgba: Tuple[int, int, int, int]):
    if QColor is None:
        return None
    r, g, b, a = rgba
    return QColor(int(r), int(g), int(b), int(a))


AVAILABLE_FILTERS: Tuple[FilterSpec, ...] = (
    FilterSpec(
        key="none",
        label="None",
        description="Disable color grading adjustments.",
        passes=(),
    ),
    FilterSpec(
        key="grayscale",
        label="Grayscale Boost",
        description="Desaturates the viewer for high readability previews.",
        passes=(
            FilterPass(
                color=(127, 127, 127, 255), composition="saturation", opacity=1.0
            ),
            FilterPass(color=(0, 0, 0, 120), composition="luminosity", opacity=0.35),
        ),
    ),
    FilterSpec(
        key="deuteranopia",
        label="Deuteranopia Friendly",
        description="Balances red/green contrast using overlay and soft-light cues.",
        passes=(
            FilterPass(
                color=(60, 120, 240, 180), composition="soft_light", opacity=0.65
            ),
            FilterPass(color=(255, 200, 140, 200), composition="color", opacity=0.40),
        ),
    ),
    FilterSpec(
        key="protanopia",
        label="Protanopia Friendly",
        description="Adds warm highlights and cool shadows to strengthen reds.",
        passes=(
            FilterPass(
                color=(255, 180, 120, 200), composition="soft_light", opacity=0.55
            ),
            FilterPass(color=(70, 110, 255, 160), composition="overlay", opacity=0.45),
        ),
    ),
    FilterSpec(
        key="tritanopia",
        label="Tritanopia Friendly",
        description="Shifts blues and yellows with a soft overlay tuned for UI.",
        passes=(
            FilterPass(color=(250, 220, 120, 210), composition="color", opacity=0.45),
            FilterPass(
                color=(70, 160, 255, 180), composition="soft_light", opacity=0.45
            ),
        ),
    ),
    FilterSpec(
        key="inverted",
        label="High Inversion",
        description="Inverts the viewer for dark-on-light previews without re-rendering.",
        passes=(
            FilterPass(
                color=(255, 255, 255, 255), composition="difference", opacity=1.0
            ),
            FilterPass(color=(10, 10, 10, 120), composition="overlay", opacity=0.40),
        ),
    ),
)

FILTER_INDEX: Dict[str, FilterSpec] = {spec.key: spec for spec in AVAILABLE_FILTERS}


def canonical_filter_key(raw: str) -> str:
    key = (raw or "none").strip().lower()
    if key in FILTER_INDEX:
        return key
    for spec in AVAILABLE_FILTERS:
        if spec.label.lower() == key:
            return spec.key
    return "none"


def list_filters() -> List[Dict[str, str]]:
    return [
        {"key": spec.key, "label": spec.label, "description": spec.description}
        for spec in AVAILABLE_FILTERS
    ]


if QWidget is object:  # pragma: no cover - stubbed in headless environments

    class FilterOverlay:  # type: ignore[override]
        def __init__(self, *_args, **_kwargs) -> None:
            self._key = "none"

        def set_filter(self, key: str) -> None:
            self._key = canonical_filter_key(key)

        def current_filter(self) -> str:
            return self._key

else:

    class FilterOverlay(QWidget):
        """Transparent overlay that applies LUT-inspired tint passes to the viewer."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._key = "none"
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.hide()

        def current_filter(self) -> str:
            return self._key

        def set_filter(self, key: str) -> None:
            canonical = canonical_filter_key(key)
            if canonical == self._key:
                return
            self._key = canonical
            if canonical == "none":
                self.hide()
            else:
                self.show()
                self.raise_()
            self.update()

        # QWidget overrides -------------------------------------------------
        def paintEvent(self, event):  # type: ignore[override]
            if QPainter is None or QColor is None or self._key == "none":
                return
            spec = FILTER_INDEX.get(self._key)
            if spec is None or not spec.passes:
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, False)
            rect = self.rect()
            for p in spec.passes:
                color = _qcolor(p.color)
                if color is None:
                    continue
                painter.setOpacity(max(0.0, min(p.opacity, 1.0)))
                painter.setCompositionMode(_comp(p.composition))
                painter.fillRect(rect, color)
            painter.end()


__all__ = [
    "FilterOverlay",
    "FilterPass",
    "FilterSpec",
    "AVAILABLE_FILTERS",
    "list_filters",
    "canonical_filter_key",
]
