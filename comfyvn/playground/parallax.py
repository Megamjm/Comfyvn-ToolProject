from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)

Vec2 = Tuple[float, float]


class SnapshotHook(Protocol):
    def __call__(self, payload: Dict) -> None:  # pragma: no cover - callback protocol
        ...


@dataclass
class CameraPose:
    """Lightweight orbital camera pose consumed by both tiers."""

    yaw: float = 0.0
    pitch: float = -0.1
    distance: float = 4.25
    pan_x: float = 0.0
    pan_y: float = 0.0
    fov: float = 48.0

    def clamp(self) -> "CameraPose":
        self.pitch = max(-math.radians(60.0), min(math.radians(60.0), self.pitch))
        self.distance = max(1.0, min(32.0, self.distance))
        self.fov = max(20.0, min(90.0, self.fov))
        return self

    def to_dict(self) -> Dict[str, float]:
        return {
            "yaw": round(self.yaw, 6),
            "pitch": round(self.pitch, 6),
            "distance": round(self.distance, 6),
            "pan_x": round(self.pan_x, 6),
            "pan_y": round(self.pan_y, 6),
            "fov": round(self.fov, 3),
        }


@dataclass
class ParallaxLayer:
    """Represents a single visual plane within the Tier-0 parallax stack."""

    name: str
    asset_id: str
    depth: float
    overlay: bool = False
    visible: bool = True
    tint: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    parallax_scale: float = 1.0
    metadata: Dict[str, object] = field(default_factory=dict)

    def normalized_depth(self) -> float:
        return max(-10.0, min(10.0, self.depth))

    def to_dict(self) -> Dict[str, object]:
        payload = {
            "name": self.name,
            "asset": self.asset_id,
            "depth": round(self.normalized_depth(), 4),
            "visible": self.visible,
            "overlay": self.overlay,
            "tint": tuple(round(v, 4) for v in self.tint),
            "parallax_scale": round(self.parallax_scale, 4),
        }
        if self.metadata:
            payload["meta"] = self.metadata
        return payload


class OrbitController:
    """Handles smooth pan/orbit/zoom interactions for the parallax camera."""

    def __init__(self, *, smoothing: float = 0.18, seed: Optional[int] = None) -> None:
        self.state = CameraPose()
        self._target = CameraPose()
        self._smoothing = max(0.01, min(1.0, smoothing))
        self._seed = seed or int(time.time()) & 0xFFFFFFFF

    # ------------------------------------------------------------------ mutators
    def pan(self, delta: Vec2) -> None:
        dx, dy = delta
        self._target.pan_x += dx
        self._target.pan_y += dy

    def orbit(self, delta: Vec2) -> None:
        dx, dy = delta
        self._target.yaw += dx
        self._target.pitch += dy
        self._target.clamp()

    def zoom(self, amount: float) -> None:
        self._target.distance += amount
        self._target.clamp()

    def set_fov(self, fov: float) -> None:
        self._target.fov = fov
        self._target.clamp()

    # ------------------------------------------------------------------ update
    def step(self, dt: float) -> CameraPose:
        if dt <= 0.0:
            return self.state

        stiffness = 1.0 - math.exp(-self._smoothing * dt)
        for attr in ("yaw", "pitch", "distance", "pan_x", "pan_y", "fov"):
            current = getattr(self.state, attr)
            target = getattr(self._target, attr)
            setattr(self.state, attr, current + (target - current) * stiffness)
        self.state.clamp()
        return self.state

    # ------------------------------------------------------------------ util
    def serialize(self) -> Dict[str, object]:
        payload = self.state.to_dict()
        payload["seed"] = self._seed
        payload["smoothing"] = round(self._smoothing, 4)
        return payload

    def apply_pose(self, pose: CameraPose) -> CameraPose:
        clone = CameraPose(
            yaw=float(pose.yaw),
            pitch=float(pose.pitch),
            distance=float(pose.distance),
            pan_x=float(pose.pan_x),
            pan_y=float(pose.pan_y),
            fov=float(pose.fov),
        ).clamp()
        self.state = CameraPose(**clone.__dict__)
        self._target = CameraPose(**clone.__dict__)
        return self.state

    def load_from_dict(self, payload: Dict[str, float]) -> CameraPose:
        pose = CameraPose(
            yaw=float(payload.get("yaw", self.state.yaw)),
            pitch=float(payload.get("pitch", self.state.pitch)),
            distance=float(payload.get("distance", self.state.distance)),
            pan_x=float(payload.get("pan_x", self.state.pan_x)),
            pan_y=float(payload.get("pan_y", self.state.pan_y)),
            fov=float(payload.get("fov", self.state.fov)),
        )
        return self.apply_pose(pose)


class ParallaxScene:
    """Tier-0 camera + layer orchestrator used by `PlaygroundView`.

    The scene keeps a minimal state machine so modders can subscribe to hooks
    (`on_stage_load`, `on_stage_snapshot`, `on_layer_change`) without touching
    the GUI code. The compositor itself is UI-agnostic; rendering happens in
    `PlaygroundView`.
    """

    MIN_PLANES = 3
    DEFAULT_LAYERS: Tuple[Tuple[str, str, float, bool], ...] = (
        ("Sky Far", "playground/backgrounds/far_sky", -6.0, False),
        ("Backdrop Mid", "playground/backgrounds/mid_cards", -2.5, False),
        ("Hero Cards", "playground/cards/hero_stack", -0.25, False),
        ("Weather Overlay", "playground/overlays/weather", 1.2, True),
    )

    def __init__(
        self,
        *,
        seed: Optional[int] = None,
        hooks: Optional[Dict[str, Iterable[SnapshotHook]]] = None,
    ) -> None:
        self._seed = seed or int(time.time()) & 0xFFFFFFFF
        self._orbit = OrbitController(seed=self._seed)
        self._layers: List[ParallaxLayer] = []
        self._hooks: Dict[str, List[SnapshotHook]] = {
            "on_stage_load": [],
            "on_stage_snapshot": [],
            "on_layer_change": [],
        }
        if hooks:
            for key, callbacks in hooks.items():
                for cb in callbacks:
                    self.register_hook(key, cb)
        self._last_frame: Dict[str, object] = {}
        self._weather_state: Dict[str, object] = {"profile": "clear", "intensity": 0.0}
        self._ensure_min_layers()

    # ------------------------------------------------------------------ hooks
    def register_hook(self, name: str, callback: SnapshotHook) -> None:
        if name not in self._hooks:
            raise ValueError(f"Unknown parallax hook '{name}'")
        self._hooks[name].append(callback)

    def _emit(self, name: str, payload: Dict[str, object]) -> None:
        callbacks = self._hooks.get(name, [])
        for cb in callbacks:
            try:
                cb(dict(payload))
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Parallax hook '%s' failed: %s", name, exc, exc_info=True
                )

    # ------------------------------------------------------------------ layers
    def _ensure_min_layers(self) -> None:
        if len(self._layers) >= self.MIN_PLANES:
            return
        for name, asset, depth, overlay in self.DEFAULT_LAYERS:
            if overlay and any(layer.overlay for layer in self._layers):
                continue
            if any(layer.name == name for layer in self._layers):
                continue
            self._layers.append(
                ParallaxLayer(
                    name=name,
                    asset_id=asset,
                    depth=depth,
                    overlay=overlay,
                    parallax_scale=1.5 if overlay else 1.0,
                    metadata={"seed": self._seed},
                )
            )
        logger.debug("ParallaxScene initialised with %s layers", len(self._layers))
        self._emit("on_stage_load", self.describe())

    def layers(self) -> Tuple[ParallaxLayer, ...]:
        return tuple(self._layers)

    def set_layers(self, layers: Iterable[ParallaxLayer]) -> None:
        self._layers = list(layers)
        self._ensure_min_layers()
        self._emit("on_layer_change", self.describe())

    def load_snapshot(self, payload: Dict[str, object]) -> None:
        if not payload:
            return
        seed = payload.get("seed")
        if isinstance(seed, int):
            self._seed = seed
        camera = payload.get("camera")
        if isinstance(camera, dict):
            self._orbit.load_from_dict(camera)

        layers_payload = payload.get("layers")
        if isinstance(layers_payload, Iterable):
            restored: List[ParallaxLayer] = []
            for index, entry in enumerate(layers_payload):
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or f"Layer-{index}")
                asset = str(entry.get("asset") or entry.get("asset_id") or "")
                if not asset:
                    continue
                depth_value = entry.get("depth")
                if depth_value is None:
                    offset = entry.get("offset")
                    if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                        depth_value = offset[2]
                    else:
                        depth_value = 0.0

                tint_values = entry.get("tint")
                if isinstance(tint_values, dict):
                    tint_seq = list(tint_values.values())
                elif isinstance(tint_values, (list, tuple)):
                    tint_seq = list(tint_values)
                else:
                    tint_seq = [1.0, 1.0, 1.0]
                while len(tint_seq) < 3:
                    tint_seq.append(tint_seq[-1] if tint_seq else 1.0)
                tint = tuple(float(tint_seq[i]) for i in range(3))  # type: ignore[misc]

                parallax_strength = entry.get("parallax_scale")
                if parallax_strength is None:
                    parallax_strength = entry.get("parallax_strength", 1.0)

                restored.append(
                    ParallaxLayer(
                        name=name,
                        asset_id=asset,
                        depth=float(depth_value),
                        overlay=bool(entry.get("overlay", False)),
                        visible=bool(entry.get("visible", True)),
                        tint=tint,
                        parallax_scale=float(parallax_strength),
                        metadata=dict(entry.get("meta") or entry.get("metadata") or {}),
                    )
                )
            if restored:
                self.set_layers(restored)

        weather = payload.get("weather")
        if isinstance(weather, dict):
            profile = str(weather.get("profile", "clear"))
            intensity = float(weather.get("intensity", 0.0))
            self.set_weather(profile, intensity)

        self._last_frame = self._compose_frame(self._orbit.state)
        self._emit("on_stage_load", self.describe())

    def update_layer(
        self,
        name: str,
        *,
        visible: Optional[bool] = None,
        depth: Optional[float] = None,
        tint: Optional[Tuple[float, float, float]] = None,
        parallax_scale: Optional[float] = None,
    ) -> None:
        for layer in self._layers:
            if layer.name != name:
                continue
            if visible is not None:
                layer.visible = bool(visible)
            if depth is not None:
                layer.depth = float(depth)
            if tint is not None:
                layer.tint = tuple(float(v) for v in tint)  # type: ignore[assignment]
            if parallax_scale is not None:
                layer.parallax_scale = float(parallax_scale)
            self._emit("on_layer_change", {"layer": layer.to_dict()})
            return
        raise KeyError(f"No parallax layer named '{name}'")

    # ------------------------------------------------------------------ weather
    def set_weather(self, profile: str, intensity: float) -> None:
        self._weather_state = {
            "profile": profile,
            "intensity": max(0.0, min(1.0, intensity)),
        }
        overlay = next((layer for layer in self._layers if layer.overlay), None)
        if overlay:
            overlay.visible = intensity > 0.01
            overlay.metadata["profile"] = profile
            overlay.metadata["intensity"] = self._weather_state["intensity"]
            overlay.parallax_scale = 1.3 + intensity * 0.4
        self._emit("on_layer_change", {"weather": dict(self._weather_state)})

    # ------------------------------------------------------------------ camera controls
    def orbit(self, delta: Vec2) -> None:
        self._orbit.orbit(delta)

    def pan(self, delta: Vec2) -> None:
        self._orbit.pan(delta)

    def zoom(self, delta: float) -> None:
        self._orbit.zoom(delta)

    def set_fov(self, fov: float) -> None:
        self._orbit.set_fov(fov)

    def step(self, dt: float) -> Dict[str, object]:
        pose = self._orbit.step(dt)
        frame = self._compose_frame(pose)
        self._last_frame = frame
        return frame

    def compose_frame(self) -> Dict[str, object]:
        if not self._last_frame:
            return self.step(0.016)
        return dict(self._last_frame)

    # ------------------------------------------------------------------ snapshot
    def snapshot(self) -> Dict[str, object]:
        camera = self._orbit.serialize()
        layers = [layer.to_dict() for layer in self._layers if layer.visible]
        overlays = [
            layer.to_dict() for layer in self._layers if layer.overlay and layer.visible
        ]
        payload = {
            "mode": "tier0",
            "workflow": "comfyvn.playground.parallax.v1",
            "seed": self._seed,
            "timestamp": time.time(),
            "camera": camera,
            "layers": layers,
            "overlays": overlays,
            "weather": dict(self._weather_state),
            "frame": self.compose_frame(),
        }
        self._emit("on_stage_snapshot", payload)
        return payload

    def save_snapshot(self, path: Path) -> Path:
        payload = self.snapshot()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Parallax snapshot saved to %s", path)
        return path

    # ------------------------------------------------------------------ describe/debug
    def describe(self) -> Dict[str, object]:
        return {
            "seed": self._seed,
            "camera": self._orbit.serialize(),
            "layers": [layer.to_dict() for layer in self._layers],
            "weather": dict(self._weather_state),
        }

    def debug_state(self) -> Dict[str, object]:
        frame = self.compose_frame()
        debug = {
            "frame": frame,
            "weather": dict(self._weather_state),
            "seed": self._seed,
            "layers": [layer.to_dict() for layer in self._layers],
        }
        return debug

    # ------------------------------------------------------------------ internals
    def _compose_frame(self, pose: CameraPose) -> Dict[str, object]:
        view_layers: List[Dict[str, object]] = []
        sin_yaw = math.sin(pose.yaw)
        cos_yaw = math.cos(pose.yaw)
        sin_pitch = math.sin(pose.pitch)
        cos_pitch = math.cos(pose.pitch)

        for layer in self._layers:
            if not layer.visible:
                continue

            depth_factor = 1.0 / (1.0 + abs(layer.depth))
            parallax_strength = layer.parallax_scale * depth_factor
            offset_x = pose.pan_x * parallax_strength + sin_yaw * layer.depth * 0.4
            offset_y = pose.pan_y * parallax_strength + sin_pitch * layer.depth * 0.25
            scale = 1.0 + (layer.depth * -0.05)
            rotation = (
                sin_yaw * 0.02 * layer.parallax_scale,
                -sin_pitch * 0.02 * layer.parallax_scale,
                0.0,
            )

            view_layers.append(
                {
                    "name": layer.name,
                    "asset": layer.asset_id,
                    "overlay": layer.overlay,
                    "offset": (
                        round(offset_x, 5),
                        round(offset_y, 5),
                        round(layer.depth, 5),
                    ),
                    "rotation": tuple(round(r, 6) for r in rotation),
                    "scale": round(scale, 5),
                    "tint": tuple(round(v, 4) for v in layer.tint),
                    "parallax_strength": round(parallax_strength, 5),
                    "meta": layer.metadata,
                }
            )

        frame = {
            "camera": pose.to_dict(),
            "layers": view_layers,
            "orbit": {
                "sin_yaw": round(sin_yaw, 6),
                "cos_yaw": round(cos_yaw, 6),
                "sin_pitch": round(sin_pitch, 6),
                "cos_pitch": round(cos_pitch, 6),
            },
        }
        return frame


__all__ = [
    "CameraPose",
    "ParallaxLayer",
    "ParallaxScene",
]
