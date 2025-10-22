from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Dict, Mapping, Optional

try:  # GUI dependencies are optional when running headless.
    from PySide6.QtGui import QColor, QFont, QPalette  # type: ignore
    from PySide6.QtWidgets import QApplication  # type: ignore
except Exception:  # pragma: no cover - headless environments
    QFont = None  # type: ignore
    QPalette = None  # type: ignore
    QColor = None  # type: ignore
    QApplication = None  # type: ignore

from comfyvn.config import runtime_paths
from comfyvn.core.notifier import notifier
from comfyvn.core.settings_manager import DEFAULTS as SETTINGS_DEFAULTS
from comfyvn.core.settings_manager import SettingsManager

try:  # Optional on pure client builds
    from comfyvn.core import modder_hooks  # type: ignore
except Exception:  # pragma: no cover - defensive
    modder_hooks = None  # type: ignore

from . import filters  # noqa: E402  (local import after optional deps)
from .ui_scale import (
    clamp_scale as _clamp_ui_scale,
)
from .ui_scale import (
    normalize_overrides as _normalize_overrides,
)
from .ui_scale import (
    ui_scale_manager,
)

LOGGER = logging.getLogger("comfyvn.accessibility")


@dataclass
class AccessibilityState:
    """Mutable snapshot of accessibility preferences and runtime overlays."""

    font_scale: float = 1.0
    color_filter: str = "none"
    high_contrast: bool = False
    subtitles_enabled: bool = True
    ui_scale: float = 1.0
    view_overrides: Dict[str, float] = field(default_factory=dict)
    subtitle_text: str = ""
    subtitle_origin: Optional[str] = None
    subtitle_expires_at: Optional[float] = None

    def to_persisted_dict(self) -> Dict[str, Any]:
        """Return only the fields that should persist to the settings file."""
        return {
            "font_scale": float(self.font_scale),
            "color_filter": str(self.color_filter or "none"),
            "high_contrast": bool(self.high_contrast),
            "subtitles_enabled": bool(self.subtitles_enabled),
            "ui_scale": float(self.ui_scale),
            "view_overrides": {
                str(key): float(value)
                for key, value in (self.view_overrides or {}).items()
            },
        }

    @classmethod
    def from_mapping(cls, payload: Dict[str, Any]) -> "AccessibilityState":
        state = cls()
        state.font_scale = _clamp(
            float(payload.get("font_scale", state.font_scale)), 0.5, 3.0
        )
        state.color_filter = filters.canonical_filter_key(
            str(payload.get("color_filter", state.color_filter))
        )
        state.high_contrast = bool(payload.get("high_contrast", state.high_contrast))
        state.subtitles_enabled = bool(
            payload.get("subtitles_enabled", state.subtitles_enabled)
        )
        state.ui_scale = _clamp_ui_scale(payload.get("ui_scale", state.ui_scale))
        state.view_overrides = _normalize_overrides(
            payload.get("view_overrides", state.view_overrides)
        )
        return state


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


class AccessibilityManager:
    """Central orchestrator for accessibility state, persistence, and observers."""

    def __init__(self, settings_manager: Optional[SettingsManager] = None) -> None:
        self._settings = settings_manager or SettingsManager()
        self._state = AccessibilityState.from_mapping(
            self._settings.get("accessibility", {})
        )
        self._subscribers: Dict[str, Callable[[AccessibilityState], None]] = {}
        self._subtitle_timer: Optional[threading.Timer] = None

        self._base_font: Optional[QFont] = None
        self._base_point_size: Optional[float] = None
        self._base_palette: Optional[QPalette] = None
        self._high_contrast_palette: Optional[QPalette] = None

        self._ensure_logger()
        self._apply_appearance()  # honour persisted state on startup

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> AccessibilityState:
        return AccessibilityState(**asdict(self._state))

    def snapshot(self) -> AccessibilityState:
        return self.state

    def export_profile(self) -> Dict[str, Any]:
        return self._state.to_persisted_dict()

    def import_profile(self, payload: Mapping[str, Any]) -> AccessibilityState:
        if not payload:
            return self.snapshot()
        normalized = AccessibilityState.from_mapping(dict(payload))
        return self.update(**normalized.to_persisted_dict())

    # ---------------------------------------------------------------- subscribers
    def subscribe(self, callback: Callable[[AccessibilityState], None]) -> str:
        token = uuid.uuid4().hex
        self._subscribers[token] = callback
        try:
            callback(self.snapshot())
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug(
                "Accessibility subscriber callback failed during attach", exc_info=True
            )
        return token

    def unsubscribe(self, token: str) -> None:
        self._subscribers.pop(token, None)

    def _notify(self) -> None:
        snapshot = self.snapshot()
        for token, callback in list(self._subscribers.items()):
            try:
                callback(snapshot)
            except Exception:  # pragma: no cover - defensive
                LOGGER.warning(
                    "Accessibility subscriber failure (%s)", token, exc_info=True
                )

    # ---------------------------------------------------------------- updates
    def update(self, **fields: Any) -> AccessibilityState:
        if not fields:
            return self.snapshot()

        new_payload = asdict(self._state)
        if "font_scale" in fields:
            new_payload["font_scale"] = _clamp(float(fields["font_scale"]), 0.5, 3.0)
        if "color_filter" in fields:
            new_payload["color_filter"] = filters.canonical_filter_key(
                str(fields["color_filter"])
            )
        if "high_contrast" in fields:
            new_payload["high_contrast"] = bool(fields["high_contrast"])
        if "subtitles_enabled" in fields:
            new_payload["subtitles_enabled"] = bool(fields["subtitles_enabled"])
        if "ui_scale" in fields:
            new_payload["ui_scale"] = _clamp_ui_scale(fields["ui_scale"])
        if "view_overrides" in fields:
            new_payload["view_overrides"] = _normalize_overrides(
                fields["view_overrides"]
            )

        updated = AccessibilityState.from_mapping(new_payload)
        # preserve ephemeral subtitle fields
        updated.subtitle_text = self._state.subtitle_text
        updated.subtitle_origin = self._state.subtitle_origin
        updated.subtitle_expires_at = self._state.subtitle_expires_at

        if updated.to_persisted_dict() == self._state.to_persisted_dict():
            return self.snapshot()

        self._state = updated
        self._settings.patch("accessibility", self._state.to_persisted_dict())
        self._emit_settings_update()
        self._apply_appearance()
        self._notify()
        return self.snapshot()

    def reset(self) -> AccessibilityState:
        defaults = AccessibilityState.from_mapping(
            SETTINGS_DEFAULTS.get("accessibility", {})
        )
        return self.update(
            font_scale=defaults.font_scale,
            color_filter=defaults.color_filter,
            high_contrast=defaults.high_contrast,
            subtitles_enabled=defaults.subtitles_enabled,
            ui_scale=defaults.ui_scale,
            view_overrides=defaults.view_overrides,
        )

    # ----------------------------------------------------------- subtitles
    def push_subtitle(
        self,
        text: str,
        *,
        origin: Optional[str] = None,
        ttl: float = 5.0,
    ) -> AccessibilityState:
        clean = (text or "").strip()
        self._cancel_subtitle_timer()
        if not clean:
            return self.clear_subtitle()

        self._state.subtitle_text = clean
        self._state.subtitle_origin = origin
        expires_at = None
        if ttl and ttl > 0:
            expires_at = time.time() + ttl
            timer = threading.Timer(ttl, self.clear_subtitle)
            timer.daemon = True
            timer.start()
            self._subtitle_timer = timer
        else:
            self._subtitle_timer = None
        self._state.subtitle_expires_at = expires_at
        self._emit_subtitle_event(
            "accessibility.subtitle.push", clean, origin, expires_at
        )
        self._notify()
        return self.snapshot()

    def clear_subtitle(self) -> AccessibilityState:
        self._cancel_subtitle_timer()
        if not self._state.subtitle_text:
            return self.snapshot()
        self._state.subtitle_text = ""
        self._state.subtitle_origin = None
        self._state.subtitle_expires_at = None
        self._emit_subtitle_event("accessibility.subtitle.clear", "", None, None)
        self._notify()
        return self.snapshot()

    def _cancel_subtitle_timer(self) -> None:
        timer = self._subtitle_timer
        if timer is not None:
            timer.cancel()
        self._subtitle_timer = None

    # ------------------------------------------------------- appearance
    def ensure_applied(self) -> None:
        self._apply_appearance()

    def _apply_appearance(self) -> None:
        self._apply_ui_scale()
        self._apply_font_scale()
        self._apply_contrast_palette()

    def _apply_ui_scale(self) -> None:
        ui_scale_manager.configure(
            global_scale=self._state.ui_scale,
            overrides=self._state.view_overrides,
        )

    def _apply_font_scale(self) -> None:
        if QApplication is None or QFont is None:
            return
        app = QApplication.instance()
        if app is None:
            return
        current_font = app.font()
        if self._base_font is None:
            self._base_font = QFont(current_font)
        if self._base_point_size is None or self._base_point_size <= 0:
            size = float(current_font.pointSizeF())
            if size <= 0:
                size = float(current_font.pointSize() or 12)
            self._base_point_size = size
        target_size = max(6.0, (self._base_point_size or 12.0) * self._state.font_scale)
        if abs(current_font.pointSizeF() - target_size) < 0.01:
            return
        updated_font = QFont(self._base_font or current_font)
        updated_font.setPointSizeF(target_size)
        app.setFont(updated_font)

    def _apply_contrast_palette(self) -> None:
        if QApplication is None or QPalette is None or QColor is None:
            return
        app = QApplication.instance()
        if app is None:
            return
        palette = app.palette()
        if self._base_palette is None:
            self._base_palette = QPalette(palette)
        if not self._state.high_contrast:
            if self._base_palette is not None:
                app.setPalette(self._base_palette)
            return
        if self._high_contrast_palette is None:
            hc = QPalette(self._base_palette or palette)
            window_bg = QColor("#101820")
            window_text = QColor("#F4F7FA")
            accent = QColor("#FFC20E")
            hc.setColor(QPalette.Window, window_bg)
            hc.setColor(QPalette.Base, QColor("#0B1119"))
            hc.setColor(QPalette.Button, QColor("#131D2B"))
            hc.setColor(QPalette.Text, window_text)
            hc.setColor(QPalette.WindowText, window_text)
            hc.setColor(QPalette.ButtonText, window_text)
            hc.setColor(QPalette.Highlight, accent)
            hc.setColor(QPalette.HighlightedText, QColor("#1B1B1B"))
            self._high_contrast_palette = hc
        app.setPalette(self._high_contrast_palette)

    # ------------------------------------------------------- logging + hooks
    def _ensure_logger(self) -> None:
        if getattr(LOGGER, "_comfyvn_accessibility_configured", False):
            return
        logs_path = runtime_paths.logs_dir("accessibility.log")
        handler = RotatingFileHandler(
            logs_path,
            maxBytes=500_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        handler._comfyvn_accessibility = True  # type: ignore[attr-defined]
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)
        LOGGER._comfyvn_accessibility_configured = True  # type: ignore[attr-defined]
        LOGGER.info(
            "Accessibility manager ready", extra={"event": "accessibility.init"}
        )

    def _emit_settings_update(self) -> None:
        payload = self._state.to_persisted_dict()
        LOGGER.info(
            "Accessibility settings updated",
            extra={"event": "accessibility.settings", "data": payload},
        )
        notifier.toast(
            "info",
            "Accessibility updated",
            meta={
                "accessibility": payload,
                "feature_flags": {"high_contrast": payload["high_contrast"]},
                "ui_scale": {
                    "global": payload.get("ui_scale", 1.0),
                    "overrides": dict(payload.get("view_overrides") or {}),
                },
            },
        )
        if modder_hooks:
            try:
                modder_hooks.emit(
                    "on_accessibility_settings",
                    {
                        "state": payload,
                        "timestamp": time.time(),
                        "source": "accessibility.manager",
                    },
                )
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug(
                    "Failed to emit accessibility settings hook", exc_info=True
                )

    def _emit_subtitle_event(
        self,
        reason: str,
        text: str,
        origin: Optional[str],
        expires_at: Optional[float],
    ) -> None:
        LOGGER.info(
            "Accessibility subtitle event",
            extra={
                "event": reason,
                "subtitle": {
                    "text": text,
                    "origin": origin,
                    "expires_at": expires_at,
                    "enabled": self._state.subtitles_enabled,
                },
            },
        )
        if modder_hooks:
            try:
                modder_hooks.emit(
                    "on_accessibility_subtitle",
                    {
                        "text": text,
                        "origin": origin,
                        "expires_at": expires_at,
                        "enabled": self._state.subtitles_enabled,
                        "timestamp": time.time(),
                        "reason": reason,
                    },
                )
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug(
                    "Failed to emit accessibility subtitle hook", exc_info=True
                )


accessibility_manager = AccessibilityManager()

__all__ = ["AccessibilityManager", "AccessibilityState", "accessibility_manager"]
