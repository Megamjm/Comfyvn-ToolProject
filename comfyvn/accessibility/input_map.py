from __future__ import annotations

import copy
import logging
import time
import uuid
import weakref
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

try:  # Qt shortcuts are optional for headless/testing modes.
    from PySide6.QtGui import QKeySequence  # type: ignore
    from PySide6.QtWidgets import QShortcut, QWidget  # type: ignore
except Exception:  # pragma: no cover - optional dependency missing
    QKeySequence = None  # type: ignore
    QShortcut = None  # type: ignore
    QWidget = object  # type: ignore

try:  # Controller support relies on QtGamepad when available.
    from PySide6.QtCore import QObject  # type: ignore
    from PySide6.QtGamepad import QGamepad, QGamepadManager  # type: ignore
except Exception:  # pragma: no cover - optional dependency missing
    QObject = object  # type: ignore
    QGamepad = None  # type: ignore
    QGamepadManager = None  # type: ignore

from comfyvn.config import feature_flags
from comfyvn.core.notifier import notifier
from comfyvn.core.settings_manager import DEFAULTS as SETTINGS_DEFAULTS
from comfyvn.core.settings_manager import SettingsManager

try:  # Optional for GUI-less tooling.
    from comfyvn.core import modder_hooks  # type: ignore
except Exception:  # pragma: no cover - fallback for pure client usage
    modder_hooks = None  # type: ignore

LOGGER = logging.getLogger("comfyvn.accessibility.input_map")


_DEFAULT_BINDINGS_RAW: Dict[str, Dict[str, Any]] = copy.deepcopy(
    SETTINGS_DEFAULTS.get("input_map", {}).get("bindings", {})
)

_GAMEPAD_LABELS: Dict[str, str] = {
    "": "Unassigned",
    "button_a": "South / A",
    "button_b": "East / B",
    "button_x": "West / X",
    "button_y": "North / Y",
    "button_start": "Start / Options",
    "button_select": "Select / Back",
    "button_l1": "Bumper L1",
    "button_r1": "Bumper R1",
    "dpad_up": "D-Pad Up",
    "dpad_down": "D-Pad Down",
    "dpad_left": "D-Pad Left",
    "dpad_right": "D-Pad Right",
}

_GAMEPAD_SIGNAL_MAP: Dict[str, str] = {
    "button_a": "buttonAChanged",
    "button_b": "buttonBChanged",
    "button_x": "buttonXChanged",
    "button_y": "buttonYChanged",
    "button_start": "buttonStartChanged",
    "button_select": "buttonSelectChanged",
    "button_l1": "buttonL1Changed",
    "button_r1": "buttonR1Changed",
    "dpad_up": "buttonUpChanged",
    "dpad_down": "buttonDownChanged",
    "dpad_left": "buttonLeftChanged",
    "dpad_right": "buttonRightChanged",
}


@dataclass
class InputBinding:
    action: str
    label: str
    primary: Optional[str] = None
    secondary: Optional[str] = None
    gamepad: Optional[str] = None
    category: str = "viewer"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "label": self.label,
            "primary": self.primary,
            "secondary": self.secondary,
            "gamepad": self.gamepad,
            "category": self.category,
        }

    def clone(self) -> "InputBinding":
        return InputBinding(**self.to_dict())


@dataclass
class _TargetRef:
    widget_ref: Callable[[], QWidget]
    actions: Dict[str, Callable[[], None]]
    shortcuts: List[Any] = field(default_factory=list)


class _GamepadAdapter(QObject):  # type: ignore[misc]
    def __init__(self, manager: "InputMapManager") -> None:
        super().__init__()
        self._manager = manager
        self._gamepad: QGamepad | None = None
        self._connections: list[tuple[Any, Callable[[float], None]]] = []
        if not feature_flags.is_enabled("enable_controller_profiles", default=True):
            LOGGER.info(
                "Controller profiles disabled via feature flag; gamepad adapter inactive."
            )
            self._enabled = False
            return
        if QGamepadManager is None or QGamepad is None:
            LOGGER.info("QtGamepad not available; controller remaps disabled.")
            self._enabled = False
            return
        self._manager_ref = QGamepadManager.instance()
        try:
            self._manager_ref.connectedGamepadsChanged.connect(self._refresh_devices)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("QGamepadManager does not expose connectedGamepadsChanged")
        self._enabled = True
        self._refresh_devices()

    def _refresh_devices(self) -> None:
        if not self._enabled:
            return
        try:
            ids = list(self._manager_ref.connectedGamepads())  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            ids = []
        if not ids:
            self._set_gamepad(None)
            return
        self._set_gamepad(QGamepad(ids[0], self))  # take the first device

    def _set_gamepad(self, gamepad: QGamepad | None) -> None:
        if self._gamepad is gamepad:
            return
        self._disconnect_all()
        self._gamepad = gamepad
        self.refresh()

    def refresh(self) -> None:
        if not self._enabled or self._gamepad is None:
            return
        self._disconnect_all()
        bindings = self._manager.bindings()
        for action, binding in bindings.items():
            key = (binding.gamepad or "").lower().strip()
            if not key:
                continue
            signal_name = _GAMEPAD_SIGNAL_MAP.get(key)
            if not signal_name:
                continue
            signal = getattr(self._gamepad, signal_name, None)
            if signal is None:
                LOGGER.debug(
                    "Gamepad signal %s missing for action %s", signal_name, action
                )
                continue

            def _handler(value: float, act: str = action) -> None:
                if value >= 0.5:  # avoid repeat spam while held
                    self._manager.trigger(act, source="controller")

            try:
                signal.connect(_handler)  # type: ignore[attr-defined]
                self._connections.append((signal, _handler))
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug(
                    "Failed to bind gamepad signal %s", signal_name, exc_info=True
                )

    def _disconnect_all(self) -> None:
        for signal, handler in self._connections:
            try:
                signal.disconnect(handler)  # type: ignore[attr-defined]
            except Exception:
                continue
        self._connections.clear()


class InputMapManager:
    def __init__(self, settings_manager: Optional[SettingsManager] = None) -> None:
        self._settings = settings_manager or SettingsManager()
        self._bindings: Dict[str, InputBinding] = self._load_bindings()
        self._targets: Dict[int, _TargetRef] = {}
        self._callbacks: Dict[str, List[Callable[[], None]]] = {}
        self._subscribers: Dict[str, Callable[[Dict[str, InputBinding]], None]] = {}
        self._gamepad_adapter = _GamepadAdapter(self)
        self._notify_subscribers()

    # ------------------------------------------------------------ accessors
    def bindings(self) -> Dict[str, InputBinding]:
        return {key: binding.clone() for key, binding in self._bindings.items()}

    def available_gamepad_bindings(self) -> List[Tuple[str, str]]:
        return list(_GAMEPAD_LABELS.items())

    def default_bindings(self) -> Dict[str, InputBinding]:
        return {
            key: binding.clone() for key, binding in self._default_bindings().items()
        }

    # --------------------------------------------------------------- public
    def register_widget(
        self,
        widget: QWidget,
        actions: Dict[str, Callable[[], None]],
    ) -> None:
        if QWidget is object:  # pragma: no cover - headless fallback
            return
        widget_id = id(widget)
        for action, callback in actions.items():
            self._callbacks.setdefault(action, []).append(callback)
        target = _TargetRef(widget_ref=weakref.ref(widget), actions=actions)
        self._targets[widget_id] = target
        self._apply_shortcuts(target)
        try:
            widget.destroyed.connect(lambda *_: self.unregister_widget(widget))  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug(
                "Widget does not expose destroyed signal for input map", exc_info=True
            )
        self._gamepad_adapter.refresh()

    def unregister_widget(self, widget: QWidget) -> None:
        widget_id = id(widget)
        target = self._targets.pop(widget_id, None)
        if target is None:
            return
        for shortcuts in target.shortcuts:
            try:
                shortcuts.setParent(None)  # type: ignore[attr-defined]
            except Exception:
                continue
        for action, callback in target.actions.items():
            callbacks = self._callbacks.get(action, [])
            try:
                callbacks.remove(callback)
            except ValueError:
                pass
            if not callbacks:
                self._callbacks.pop(action, None)
        self._gamepad_adapter.refresh()

    def update_binding(
        self,
        action: str,
        *,
        primary: Optional[str] = None,
        secondary: Optional[str] = None,
        gamepad: Optional[str] = None,
    ) -> InputBinding:
        binding = self._bindings.get(action)
        if binding is None:
            raise KeyError(f"Unknown input action: {action}")
        changed = False
        if primary is not None and binding.primary != self._clean_sequence(primary):
            binding.primary = self._clean_sequence(primary)
            changed = True
        if secondary is not None and binding.secondary != self._clean_sequence(
            secondary
        ):
            binding.secondary = self._clean_sequence(secondary)
            changed = True
        if gamepad is not None:
            clean_pad = (gamepad or "").strip().lower() or None
            if binding.gamepad != clean_pad:
                binding.gamepad = clean_pad
                changed = True
        if not changed:
            return binding.clone()
        self._persist()
        self._refresh_targets()
        self._gamepad_adapter.refresh()
        notifier.toast(
            "info",
            f"Input binding updated → {binding.label}",
            meta={
                "input": binding.to_dict(),
            },
        )
        self._emit_binding_event(binding, reason="update")
        self._notify_subscribers()
        return binding.clone()

    def reset(self) -> None:
        self._bindings = self._load_bindings(reset=True)
        self._persist()
        self._refresh_targets()
        self._gamepad_adapter.refresh()
        notifier.toast(
            "info",
            "Input bindings reset to defaults",
            meta={"input": {"count": len(self._bindings)}},
        )
        LOGGER.info(
            "Input bindings reset",
            extra={
                "event": "accessibility.input_map.reset",
                "count": len(self._bindings),
            },
        )
        for binding in self._bindings.values():
            self._emit_binding_event(binding, reason="reset")
        self._notify_subscribers()

    def trigger(
        self,
        action: str,
        *,
        source: str = "local",
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        callbacks = list(self._callbacks.get(action, ()))
        if not callbacks:
            LOGGER.debug("No callbacks registered for action %s", action)
        previous_source = getattr(self, "_current_source", None)
        previous_meta = getattr(self, "_current_meta", None)
        self._current_source = source
        self._current_meta = meta or {}
        try:
            for callback in callbacks:
                try:
                    callback()
                except Exception:  # pragma: no cover - defensive
                    LOGGER.warning(
                        "Input callback failure for %s", action, exc_info=True
                    )
        finally:
            self._current_source = previous_source
            self._current_meta = previous_meta
        payload = {
            "action": action,
            "source": source,
            "meta": meta or {},
        }
        LOGGER.info(
            "Input action triggered",
            extra={"event": "accessibility.input.trigger", **payload},
        )
        if modder_hooks:
            try:
                modder_hooks.emit(
                    "on_accessibility_input",
                    {
                        **payload,
                        "timestamp": time.time(),
                        "event_id": uuid.uuid4().hex,
                    },
                )
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Failed to emit accessibility input hook", exc_info=True)
        return bool(callbacks)

    def current_source(self) -> Optional[str]:
        return getattr(self, "_current_source", None)

    def current_meta(self) -> Optional[Dict[str, Any]]:
        return getattr(self, "_current_meta", None)

    def subscribe(self, callback: Callable[[Dict[str, InputBinding]], None]) -> str:
        token = uuid.uuid4().hex
        self._subscribers[token] = callback
        try:
            callback(self.bindings())
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Input map subscriber failed during attach", exc_info=True)
        return token

    def unsubscribe(self, token: str) -> None:
        self._subscribers.pop(token, None)

    # ------------------------------------------------------------- internals
    def _load_bindings(self, *, reset: bool = False) -> Dict[str, InputBinding]:
        defaults = self._default_bindings()
        if reset:
            return defaults
        stored = self._settings.get("input_map", {})
        raw_bindings = stored.get("bindings", {}) if isinstance(stored, dict) else {}
        result: Dict[str, InputBinding] = {}
        for action, default in defaults.items():
            raw = raw_bindings.get(action, {})
            if isinstance(raw, Mapping):
                result[action] = self._binding_from_payload(action, raw, default)
            else:
                result[action] = default.clone()
        for action, raw in raw_bindings.items():
            if action in result:
                continue
            if isinstance(raw, Mapping):
                result[action] = self._binding_from_payload(action, raw, None)
        return result

    def _default_bindings(self) -> Dict[str, InputBinding]:
        defaults: Dict[str, InputBinding] = {}
        for action, payload in _DEFAULT_BINDINGS_RAW.items():
            defaults[action] = InputBinding(
                action=action,
                label=str(payload.get("label") or action),
                primary=self._clean_sequence(payload.get("primary")),
                secondary=self._clean_sequence(payload.get("secondary")),
                gamepad=(payload.get("gamepad") or None),
                category=str(payload.get("category") or "viewer"),
            )
        return defaults

    def export_bindings(self) -> Dict[str, Dict[str, Any]]:
        return {action: binding.to_dict() for action, binding in self._bindings.items()}

    def import_bindings(
        self, payload: Mapping[str, Any], *, merge: bool = False
    ) -> Dict[str, InputBinding]:
        if not isinstance(payload, Mapping):
            raise TypeError("Input bindings payload must be a mapping.")
        base = self._bindings if merge else self._default_bindings()
        incoming: Dict[str, Mapping[str, Any]] = {}
        for action, raw in payload.items():
            if isinstance(raw, InputBinding):
                incoming[action] = raw.to_dict()
            elif isinstance(raw, Mapping):
                incoming[action] = raw
            else:
                continue
        updated: Dict[str, InputBinding] = {}
        for action in sorted(set(base.keys()) | set(incoming.keys())):
            source = incoming.get(action)
            fallback = base.get(action)
            if source is None:
                if fallback is None:
                    continue
                updated[action] = fallback.clone()
            else:
                updated[action] = self._binding_from_payload(action, source, fallback)
        self._bindings = updated
        self._persist()
        self._refresh_targets()
        self._gamepad_adapter.refresh()
        self._notify_subscribers()
        notifier.toast(
            "info",
            "Input bindings imported",
            meta={"input": {"count": len(updated), "merge": merge}},
        )
        LOGGER.info(
            "Input bindings imported",
            extra={
                "event": "accessibility.input_map.import",
                "count": len(updated),
                "merge": merge,
            },
        )
        for binding in updated.values():
            self._emit_binding_event(binding, reason="import")
        return self.bindings()

    def _binding_from_payload(
        self,
        action: str,
        payload: Mapping[str, Any],
        default: Optional[InputBinding] = None,
    ) -> InputBinding:
        base = (
            default.clone()
            if default
            else InputBinding(
                action=action,
                label=action,
                category="viewer",
            )
        )
        label = payload.get("label")
        if isinstance(label, str) and label.strip():
            base.label = label.strip()
        primary = payload.get("primary", base.primary)
        secondary = payload.get("secondary", base.secondary)
        gamepad = payload.get("gamepad", base.gamepad)
        category = payload.get("category", base.category)
        base.primary = self._clean_sequence(primary)
        base.secondary = self._clean_sequence(secondary)
        base.gamepad = (str(gamepad).strip().lower() or None) if gamepad else None
        if isinstance(category, str) and category.strip():
            base.category = category.strip()
        return base

    def _persist(self) -> None:
        self._settings.patch("input_map", {"bindings": self.export_bindings()})

    def _refresh_targets(self) -> None:
        for key, target in list(self._targets.items()):
            widget = target.widget_ref()
            if widget is None:
                self._targets.pop(key, None)
                continue
            self._apply_shortcuts(target)

    def _apply_shortcuts(self, target: _TargetRef) -> None:
        for shortcut in target.shortcuts:
            try:
                shortcut.setParent(None)  # type: ignore[attr-defined]
            except Exception:
                continue
        target.shortcuts.clear()
        widget = target.widget_ref()
        if widget is None or QShortcut is None or QKeySequence is None:
            return
        for action, callback in target.actions.items():
            binding = self._bindings.get(action)
            if binding is None:
                continue
            for seq in (binding.primary, binding.secondary):
                if not seq:
                    continue
                try:
                    shortcut = QShortcut(QKeySequence(seq), widget)
                    shortcut.activated.connect(callback)  # type: ignore[attr-defined]
                    target.shortcuts.append(shortcut)
                except Exception:  # pragma: no cover - defensive
                    LOGGER.debug(
                        "Failed to register shortcut %s for %s",
                        seq,
                        action,
                        exc_info=True,
                    )

    def _clean_sequence(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _emit_binding_event(self, binding: InputBinding, *, reason: str) -> None:
        payload = binding.to_dict()
        LOGGER.info(
            "Input binding event",
            extra={
                "event": "accessibility.input_map.binding",
                "binding": payload,
                "reason": reason,
            },
        )
        if modder_hooks:
            try:
                modder_hooks.emit(
                    "on_accessibility_input_map",
                    {
                        "action": binding.action,
                        "binding": payload,
                        "timestamp": time.time(),
                        "event_id": uuid.uuid4().hex,
                        "reason": reason,
                    },
                )
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Failed to emit input map hook", exc_info=True)

    def _notify_subscribers(self) -> None:
        snapshot = self.bindings()
        for token, callback in list(self._subscribers.items()):
            try:
                callback(snapshot)
            except Exception:  # pragma: no cover - defensive
                LOGGER.warning(
                    "Input map subscriber failure (%s)", token, exc_info=True
                )


input_map_manager = InputMapManager()


__all__ = ["InputBinding", "InputMapManager", "input_map_manager"]
