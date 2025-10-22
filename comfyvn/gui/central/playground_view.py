from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from comfyvn.config import feature_flags
from comfyvn.playground.parallax import ParallaxLayer, ParallaxScene

try:  # Qt WebEngine is optional on some deployments.
    from comfyvn.playground.stage3d.bridge import Stage3DView
except Exception:  # pragma: no cover - optional component
    Stage3DView = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

Hook = Callable[[Dict[str, Any]], None]


class ParallaxPreviewWidget(QFrame):
    """Lightweight 2.5D renderer for Tier-0 previews."""

    def __init__(self, scene: ParallaxScene, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ParallaxPreview")
        self.setFrameShape(QFrame.StyledPanel)
        self._scene = scene
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)
        self._last_time = time.monotonic()
        self._dragging = False
        self._orbit_mode = True
        self._last_pos = QPoint()
        self._frame: Dict[str, Any] = {}
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

        # Mirror camera layer changes so users can inspect offsets.
        self._scene.register_hook("on_layer_change", lambda _: self.update())

    # ------------------------------------------------------------------ Qt overrides
    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> QSize:
        return QSize(640, 360)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0f172a"))

        frame = self._frame or self._scene.compose_frame()
        layers = frame.get("layers", [])
        overlays = [layer for layer in layers if layer.get("overlay")]
        base_layers = [layer for layer in layers if not layer.get("overlay")]

        def draw_layer(layer: Dict[str, Any], *, overlay: bool = False) -> None:
            offset = layer.get("offset", (0, 0, 0))
            scale = layer.get("scale", 1.0)
            w = self.width()
            h = self.height()

            cx = w * 0.5 + offset[0] * (w * 0.4)
            cy = h * 0.55 + offset[1] * (h * 0.4)
            width = w * 0.6 * scale
            height = h * 0.35 * scale

            cell = self.rect()
            cell.setWidth(int(width))
            cell.setHeight(int(height))
            cell.moveCenter(QPoint(int(cx), int(cy)))

            tint = layer.get("tint", (1.0, 1.0, 1.0))
            color = QColor(
                int(255 * max(0.0, min(1.0, tint[0]))),
                int(255 * max(0.0, min(1.0, tint[1]))),
                int(255 * max(0.0, min(1.0, tint[2]))),
                220 if overlay else 180,
            )
            painter.setBrush(color)
            border = QColor("#10b981") if overlay else QColor("#38bdf8")
            painter.setPen(QPen(border, 2))
            painter.drawRoundedRect(cell, 18, 18)

            painter.setPen(QColor("#0f172a"))
            label = layer.get("name", "Layer")
            painter.drawText(cell, Qt.AlignCenter, label)

        for layer in sorted(
            base_layers, key=lambda item: item.get("offset", (0, 0, 0))[2]
        ):
            draw_layer(layer, overlay=False)
        for layer in overlays:
            draw_layer(layer, overlay=True)

        painter.setPen(QColor("#f8fafc"))
        camera = frame.get("camera", {})
        painter.drawText(
            self.rect().adjusted(12, 12, -12, -12),
            Qt.AlignTop | Qt.AlignLeft,
            f"Yaw {camera.get('yaw', 0.0):+.2f} • Pitch {camera.get('pitch', 0.0):+.2f} • Zoom {camera.get('distance', 0.0):.2f}",
        )

        weather = self._scene.describe().get("weather", {})
        painter.drawText(
            self.rect().adjusted(12, -32, -12, -12),
            Qt.AlignBottom | Qt.AlignLeft,
            f"Weather: {weather.get('profile', 'clear')} @ {weather.get('intensity', 0.0):.2f}",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() not in {Qt.LeftButton, Qt.RightButton}:
            return
        self._dragging = True
        self._orbit_mode = event.button() == Qt.LeftButton and not (
            event.modifiers() & Qt.ShiftModifier
        )
        self._last_pos = event.position().toPoint()
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            return
        current = event.position().toPoint()
        dx = (current.x() - self._last_pos.x()) / max(1, self.width())
        dy = (current.y() - self._last_pos.y()) / max(1, self.height())
        self._last_pos = current
        if self._orbit_mode:
            self._scene.orbit((dx * 2.2, dy * 2.2))
        else:
            self._scene.pan((dx * 6.0, -dy * 6.0))
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False
        self.setCursor(Qt.ArrowCursor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y() / 120.0
        self._scene.zoom(-delta * 0.35)
        self.update()

    # ------------------------------------------------------------------ internals
    def _tick(self) -> None:
        now = time.monotonic()
        dt = max(1e-3, now - self._last_time)
        self._frame = self._scene.step(dt)
        self._last_time = now
        self.update()


class PlaygroundView(QWidget):
    """Hosts Tier-0 parallax and Tier-1 WebGL playground views."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("PlaygroundView")
        self._snapshot_root = Path("exports/playground")
        self._hooks: Dict[str, List[Hook]] = {
            "on_stage_snapshot": [],
            "on_stage_load": [],
            "on_stage_log": [],
        }

        flags = feature_flags.load_feature_flags()
        self._playground_enabled = bool(flags.get("enable_playground", False))
        self._stage_enabled = bool(flags.get("enable_stage3d", False))
        self._mode = "tier0"
        self._stage_seed = int(time.time()) & 0xFFFFFFFF

        self._parallax_scene = ParallaxScene()
        self._parallax_scene.register_hook(
            "on_stage_snapshot",
            lambda payload: self._emit("on_stage_snapshot", payload),
        )
        self._parallax_scene.register_hook(
            "on_stage_load", lambda payload: self._emit("on_stage_load", payload)
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)

        self._status_label = QLabel("Tier-0 Parallax • Ready")
        self._status_label.setObjectName("PlaygroundStatusLabel")

        self._tier0_button = QPushButton("Tier-0 Parallax")
        self._tier1_button = QPushButton("Tier-1 Stage 3D")
        self._snapshot_button = QPushButton("Snapshot → render_config.json")
        self._snapshot_button.setObjectName("PlaygroundSnapshotButton")

        self._tier0_button.clicked.connect(lambda: self._switch_mode("tier0"))
        self._tier1_button.clicked.connect(lambda: self._switch_mode("tier1"))
        self._snapshot_button.clicked.connect(self._handle_snapshot)

        header.addWidget(self._status_label, 1)
        header.addWidget(self._tier0_button, 0)
        header.addWidget(self._tier1_button, 0)
        header.addWidget(self._snapshot_button, 0)

        layout.addLayout(header)

        self._stack = QStackedWidget(self)

        self._parallax_widget = ParallaxPreviewWidget(self._parallax_scene, self)
        self._stack.addWidget(self._parallax_widget)

        if self._stage_enabled and Stage3DView is not None:
            self._stage_view: Optional[Stage3DView] = Stage3DView(
                self,
                on_stage_snapshot=self._dispatch_stage_snapshot,
                on_stage_load=self._dispatch_stage_load,
            )
            self._stage_view.stage_log.connect(self._dispatch_stage_log)
            stage_widget: QWidget = self._stage_view
        else:
            fallback = QLabel(
                "Stage 3D disabled. Enable feature flags `enable_playground` + `enable_stage3d` to activate."
            )
            fallback.setWordWrap(True)
            fallback.setAlignment(Qt.AlignCenter)
            stage_widget = fallback
            self._stage_view = None  # type: ignore[assignment]

        self._stack.addWidget(stage_widget)
        layout.addWidget(self._stack, 1)

        self._apply_feature_flags()

    # ------------------------------------------------------------------ hooks
    def register_hook(self, name: str, callback: Hook) -> None:
        if name not in self._hooks:
            raise ValueError(f"Unknown playground hook '{name}'")
        self._hooks[name].append(callback)

    def _emit(self, name: str, payload: Dict[str, Any]) -> None:
        callbacks = self._hooks.get(name, [])
        for cb in callbacks:
            try:
                cb(dict(payload))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Playground hook '%s' failed: %s", name, exc, exc_info=True
                )

    def _dispatch_stage_snapshot(self, payload: Dict[str, Any]) -> None:
        payload.setdefault("seed", self._stage_seed)
        self._emit("on_stage_snapshot", payload)

    def _dispatch_stage_load(self, payload: Dict[str, Any]) -> None:
        self._emit("on_stage_load", payload)

    def _dispatch_stage_log(self, payload: Dict[str, Any]) -> None:
        self._emit("on_stage_log", payload)

    # ------------------------------------------------------------------ feature flags
    def _apply_feature_flags(self) -> None:
        self._tier0_button.setEnabled(self._playground_enabled)
        self._tier1_button.setEnabled(self._playground_enabled and self._stage_enabled)
        if not self._playground_enabled:
            self._status_label.setText("Playground disabled via feature flag.")
            self._stack.setCurrentIndex(0)
            self._snapshot_button.setEnabled(False)
        elif not self._stage_enabled:
            self._status_label.setText(
                "Tier-0 active • Stage3D disabled (flag `enable_stage3d`) "
            )
            self._stack.setCurrentIndex(0)
            self._snapshot_button.setEnabled(True)
        else:
            self._status_label.setText("Tier-0 Parallax • Ready")
            self._stack.setCurrentIndex(0)
            self._snapshot_button.setEnabled(True)

    # ------------------------------------------------------------------ mode switching
    def _switch_mode(self, mode: str) -> None:
        if mode == "tier1" and not (self._playground_enabled and self._stage_enabled):
            QMessageBox.information(
                self,
                "Stage 3D disabled",
                "Enable feature flags `enable_playground` and `enable_stage3d` to use the WebGL stage.",
            )
            return
        self._mode = mode
        if mode == "tier0":
            self._stack.setCurrentIndex(0)
            self._status_label.setText("Tier-0 Parallax • Ready")
        else:
            self._stack.setCurrentIndex(1)
            self._status_label.setText("Tier-1 Stage 3D • Ready")
            if self._stage_view:
                self._stage_view.reload_stage()

    # ------------------------------------------------------------------ snapshot handling
    def _handle_snapshot(self) -> None:
        if self._mode == "tier1" and self._stage_view:
            self._stage_view.request_snapshot(self._finalize_snapshot)
        else:
            payload = self._parallax_scene.snapshot()
            self._finalize_snapshot(payload)

    def _finalize_snapshot(self, payload: Optional[Dict[str, Any]]) -> None:
        if not payload:
            QMessageBox.warning(
                self, "Snapshot Error", "No payload returned from stage."
            )
            return

        payload.setdefault(
            "workflow",
            (
                "comfyvn.playground.parallax.v1"
                if self._mode == "tier0"
                else "comfyvn.playground.stage3d.v1"
            ),
        )
        payload.setdefault(
            "seed", self._stage_seed if self._mode == "tier1" else payload.get("seed")
        )
        payload.setdefault("mode", self._mode)
        payload.setdefault("timestamp", time.time())

        file_path = self._snapshot_root / "render_config.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Playground snapshot saved → %s", file_path)
        self._status_label.setText(f"Snapshot saved: {file_path}")

        self._emit("on_stage_snapshot", {**payload, "path": str(file_path)})

    # ------------------------------------------------------------------ public API helpers
    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        if not snapshot:
            return
        mode = snapshot.get("mode") or (
            "tier1" if "actors" in snapshot and "camera" in snapshot else "tier0"
        )

        if mode == "tier0":
            self._parallax_scene.load_snapshot(snapshot)
            self._mode = "tier0"
            self._stack.setCurrentIndex(0)
            self._status_label.setText("Tier-0 Parallax • Snapshot loaded")
            self._parallax_widget.update()
            return

        if mode == "tier1" and self._stage_view:
            config = snapshot.get("config")
            if not isinstance(config, dict):
                config = self._build_stage_config_from_snapshot(snapshot)
            if config:
                self._stage_view.load_scene(config)
            seed = snapshot.get("seed")
            if isinstance(seed, int):
                self._stage_seed = seed
            self._mode = "tier1"
            self._stack.setCurrentIndex(1)
            self._status_label.setText("Tier-1 Stage 3D • Snapshot loaded")

    def _build_stage_config_from_snapshot(
        self, snapshot: Dict[str, Any]
    ) -> Dict[str, Any]:
        config: Dict[str, Any] = {}
        environment = snapshot.get("environment") or {}
        sets = snapshot.get("sets") or []
        first_set = sets[0] if sets else {}
        if isinstance(first_set, dict) and (
            first_set.get("source") or first_set.get("type")
        ):
            set_entry: Dict[str, Any] = {
                "name": first_set.get("name"),
                "transform": {
                    "position": first_set.get("position"),
                    "rotation": first_set.get("rotation"),
                    "scale": first_set.get("scale"),
                },
                "metadata": first_set.get("metadata"),
            }
            source = first_set.get("source") or {}
            if source.get("gltf"):
                set_entry["gltf"] = source["gltf"]
            if source.get("vrm"):
                set_entry["vrm"] = source["vrm"]
            if source.get("texture"):
                set_entry["billboard"] = {"texture": source["texture"]}
            if isinstance(first_set.get("pickable"), bool):
                set_entry["pickable"] = first_set["pickable"]
            config["set"] = set_entry

        hdr_path = environment.get("hdr")
        if hdr_path:
            config.setdefault("set", {})
            config["set"]["hdr"] = hdr_path
        if environment.get("background"):
            config.setdefault("set", {})
            config["set"]["background"] = environment["background"]

        camera = snapshot.get("camera")
        if isinstance(camera, dict):
            config["camera"] = camera

        lights = snapshot.get("lights")
        if isinstance(lights, list):
            config["lights"] = lights

        def _build_actor(entry: Dict[str, Any]) -> Dict[str, Any]:
            actor: Dict[str, Any] = {
                "name": entry.get("name"),
                "transform": {
                    "position": entry.get("position"),
                    "rotation": entry.get("rotation"),
                    "scale": entry.get("scale"),
                },
                "metadata": entry.get("metadata"),
                "pickable": entry.get("pickable", True),
            }
            source = entry.get("source") or {}
            if source.get("vrm"):
                actor["vrm"] = source["vrm"]
            if source.get("gltf"):
                actor["gltf"] = source["gltf"]
            billboard_src = source.get("billboard") or source.get("texture")
            if billboard_src:
                actor.setdefault("billboard", {})
                actor["billboard"]["texture"] = billboard_src
            return actor

        actors = snapshot.get("actors")
        if isinstance(actors, list):
            config["actors"] = [
                _build_actor(entry) for entry in actors if isinstance(entry, dict)
            ]

        cards = snapshot.get("cards")
        if isinstance(cards, list):
            config["cards"] = []
            for entry in cards:
                if not isinstance(entry, dict):
                    continue
                card: Dict[str, Any] = {
                    "name": entry.get("name"),
                    "position": entry.get("position"),
                    "size": entry.get("size"),
                    "metadata": entry.get("metadata"),
                    "overlay": entry.get("overlay", False),
                    "pickable": entry.get("pickable", True),
                }
                source = entry.get("source") or {}
                texture = (
                    source.get("texture")
                    or source.get("billboard")
                    or source.get("texture_path")
                )
                if texture:
                    card["billboard"] = {"texture": texture}
                config["cards"].append(card)

        return config

    def load_parallax_layers(self, layers: Iterable[ParallaxLayer]) -> None:
        self._parallax_scene.set_layers(layers)

    def set_weather(self, profile: str, intensity: float) -> None:
        self._parallax_scene.set_weather(profile, intensity)
        self._parallax_widget.update()

    def load_stage_scene(self, config: Dict[str, Any]) -> None:
        if not self._stage_view:
            logger.warning("Stage3D disabled; scene load skipped.")
            return
        self._stage_view.load_scene(config)

    def configure_stage_lights(self, entries: List[Dict[str, Any]]) -> None:
        if not self._stage_view:
            logger.warning("Stage3D disabled; light configuration skipped.")
            return
        self._stage_view.configure_lights(entries)

    def debug_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "mode": self._mode,
            "flags": {
                "enable_playground": self._playground_enabled,
                "enable_stage3d": self._stage_enabled,
            },
            "tier0": self._parallax_scene.debug_state(),
        }
        if self._stage_view:
            state["tier1"] = self._stage_view.stage_info()
        else:
            state["tier1"] = {"enabled": False}
        return state

    def fetch_stage_debug(self, callback: Optional[Hook] = None) -> None:
        if not self._stage_view:
            if callback:
                callback({"enabled": False})
            return
        self._stage_view.debug_state(callback)


__all__ = ["PlaygroundView"]
