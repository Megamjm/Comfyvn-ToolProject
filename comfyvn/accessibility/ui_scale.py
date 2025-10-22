from __future__ import annotations

import logging
import math
import uuid
import weakref
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

try:  # GUI dependencies are optional in headless/test contexts.
    from PySide6.QtCore import QObject  # type: ignore
    from PySide6.QtGui import QFont  # type: ignore
    from PySide6.QtWidgets import QApplication, QLayout, QWidget  # type: ignore
except Exception:  # pragma: no cover - headless fallback
    QWidget = object  # type: ignore[assignment]
    QLayout = object  # type: ignore[assignment]
    QApplication = None  # type: ignore[assignment]
    QFont = None  # type: ignore[assignment]
    QObject = object  # type: ignore[assignment]

LOGGER = logging.getLogger("comfyvn.accessibility.ui_scale")


def clamp_scale(value: float) -> float:
    """Clamp UI scale between 1.0× (100%) and 2.0× (200%)."""
    try:
        numeric = float(value)
    except Exception:
        numeric = 1.0
    return max(1.0, min(numeric, 2.0))


def normalize_overrides(payload: Mapping[str, Any] | None) -> Dict[str, float]:
    if not payload:
        return {}
    result: Dict[str, float] = {}
    for key, raw in payload.items():
        if not key:
            continue
        try:
            scale = clamp_scale(float(raw))
        except Exception:
            continue
        result[str(key)] = scale
    return result


@dataclass
class UIScaleConfig:
    global_scale: float = 1.0
    overrides: Dict[str, float] = field(default_factory=dict)


@dataclass
class _ScaleTarget:
    token: str
    widget_ref: weakref.ReferenceType[QWidget]  # type: ignore[type-var]
    view: Optional[str]


class UIScaleManager:
    """Adjusts global Qt widget/layout metrics with optional per-view overrides."""

    def __init__(self) -> None:
        self._config = UIScaleConfig()
        self._targets: Dict[str, _ScaleTarget] = {}
        self._base_fonts: Dict[int, QFont] = {}
        self._base_font_sizes: Dict[int, float] = {}
        self._base_layout_spacing: Dict[int, int] = {}
        self._base_layout_margins: Dict[int, tuple[int, int, int, int]] = {}

    # ------------------------------------------------------------------ state
    def config(self) -> UIScaleConfig:
        return UIScaleConfig(
            global_scale=self._config.global_scale,
            overrides=dict(self._config.overrides),
        )

    def scale_for(self, view: str | None = None) -> float:
        if view:
            override = self._config.overrides.get(view)
            if override:
                return override
        return self._config.global_scale

    def configure(
        self,
        *,
        global_scale: float | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> None:
        changed = False
        if global_scale is not None:
            target = clamp_scale(global_scale)
            if not math.isclose(target, self._config.global_scale, rel_tol=1e-4):
                self._config.global_scale = target
                changed = True
        if overrides is not None:
            clean = normalize_overrides(overrides)
            if clean != self._config.overrides:
                self._config.overrides = clean
                changed = True
        if changed:
            LOGGER.info(
                "UI scale updated",
                extra={
                    "event": "accessibility.ui_scale.update",
                    "scale": self._config.global_scale,
                    "overrides": dict(self._config.overrides),
                },
            )
            self._apply_all()

    # -------------------------------------------------------------- widgets
    def register_widget(self, widget: QWidget, view: str | None = None) -> str:
        if QWidget is object:  # type: ignore[comparison-overlap]
            return "stub"
        token = uuid.uuid4().hex
        target = _ScaleTarget(token=token, widget_ref=weakref.ref(widget), view=view)
        self._targets[token] = target
        try:
            widget.destroyed.connect(lambda *_: self.unregister_widget(token))  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("UIScale widget destroyed signal unavailable", exc_info=True)
        self._snapshot_widget(widget)
        self._apply_to_widget(widget, self.scale_for(view))
        return token

    def unregister_widget(self, token: str) -> None:
        self._targets.pop(token, None)

    # ---------------------------------------------------------------- export
    def export_profile(self) -> Dict[str, Any]:
        return {
            "ui_scale": self._config.global_scale,
            "view_overrides": dict(self._config.overrides),
        }

    # ---------------------------------------------------------------- internals
    def _apply_all(self) -> None:
        if QWidget is object:
            return
        for token, target in list(self._targets.items()):
            widget = target.widget_ref()
            if widget is None:
                self._targets.pop(token, None)
                continue
            self._snapshot_widget(widget)
            self._apply_to_widget(widget, self.scale_for(target.view))

    def _snapshot_widget(self, widget: QWidget) -> None:
        if QWidget is object:
            return
        queue = [widget]
        while queue:
            current = queue.pop()
            widget_id = id(current)
            if QFont is not None:
                if widget_id not in self._base_fonts:
                    try:
                        font = current.font()
                    except Exception:  # pragma: no cover - defensive
                        font = None
                    if font is not None:
                        base_font = QFont(font)
                        self._base_fonts[widget_id] = base_font
                        size = font.pointSizeF()
                        if size <= 0:
                            size = float(font.pointSize() or 12)
                        self._base_font_sizes[widget_id] = size
            layout = current.layout() if hasattr(current, "layout") else None
            if layout and not isinstance(layout, QLayout):  # type: ignore[arg-type]
                layout = None
            if layout is not None and id(layout) not in self._base_layout_spacing:
                try:
                    spacing = layout.spacing()
                    margins = layout.getContentsMargins()
                except Exception:  # pragma: no cover - defensive
                    spacing = -1
                    margins = (0, 0, 0, 0)
                self._base_layout_spacing[id(layout)] = spacing
                self._base_layout_margins[id(layout)] = margins
            try:
                children = current.findChildren(QWidget)  # type: ignore[arg-type]
            except Exception:  # pragma: no cover - defensive
                children = []
            queue.extend(children)

    def _apply_to_widget(self, widget: QWidget, scale: float) -> None:
        if QWidget is object:
            return
        targets = [widget]
        while targets:
            current = targets.pop()
            widget_id = id(current)
            if QFont is not None and widget_id in self._base_fonts:
                base_font = self._base_fonts[widget_id]
                base_size = self._base_font_sizes.get(widget_id, 12.0)
                scaled_font = QFont(base_font)
                scaled_font.setPointSizeF(max(6.0, base_size * scale))
                try:
                    current.setFont(scaled_font)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.debug(
                        "UIScale failed to set font on %s", current, exc_info=True
                    )
            layout = current.layout() if hasattr(current, "layout") else None
            if layout and not isinstance(layout, QLayout):  # type: ignore[arg-type]
                layout = None
            if layout is not None:
                layout_id = id(layout)
                spacing = self._base_layout_spacing.get(layout_id)
                if spacing is not None and spacing >= 0:
                    new_spacing = max(0, int(round(spacing * scale)))
                    try:
                        layout.setSpacing(new_spacing)
                    except Exception:  # pragma: no cover - defensive
                        LOGGER.debug(
                            "UIScale failed to set layout spacing", exc_info=True
                        )
                margins = self._base_layout_margins.get(layout_id)
                if margins:
                    scaled_margins = tuple(
                        max(0, int(round(value * scale))) for value in margins
                    )
                    try:
                        layout.setContentsMargins(*scaled_margins)
                    except Exception:  # pragma: no cover - defensive
                        LOGGER.debug(
                            "UIScale failed to set layout margins", exc_info=True
                        )
            try:
                current.setProperty("comfyvn_ui_scale", scale)
            except Exception:  # pragma: no cover - defensive
                pass
            try:
                children = current.findChildren(QWidget)  # type: ignore[arg-type]
            except Exception:  # pragma: no cover - defensive
                children = []
            targets.extend(children)
        if QApplication is not None:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()


ui_scale_manager = UIScaleManager()

__all__ = [
    "UIScaleManager",
    "UIScaleConfig",
    "ui_scale_manager",
    "clamp_scale",
    "normalize_overrides",
]
