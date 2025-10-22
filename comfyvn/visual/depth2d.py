from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Mapping, Optional, Tuple

from comfyvn.config import feature_flags

LOGGER = logging.getLogger(__name__)


def _clamp_plane_count(value: int) -> int:
    return max(3, min(int(value), 6))


class Depth2DManager:
    """
    Resolve depth planes for 2D scenes via auto heuristics or author-supplied masks.

    The manager honours feature flag ``enable_depth2d`` (disabled by default). Manual
    masks live under ``data/depth_masks/{scene_id}.json`` and override the automatic
    heuristic when the scene mode is set to ``manual``. Scene mode preferences persist
    to ``cache/depth2d_state.json`` so toggles survive restarts.
    """

    def __init__(
        self,
        *,
        manual_root: Path = Path("data/depth_masks"),
        state_path: Path = Path("cache/depth2d_state.json"),
    ) -> None:
        self._manual_root = manual_root
        self._state_path = state_path
        self._lock = RLock()
        self._state = self._load_state()

    # ---------------------------------------------------------------- utilities
    @property
    def enabled(self) -> bool:
        return feature_flags.is_enabled("enable_depth2d", default=False)

    def _load_state(self) -> Dict[str, Any]:
        if not self._state_path.exists():
            return {"scene_modes": {}}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(data, Mapping):
                raise ValueError("state root must be an object")
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Failed to read depth2d state; resetting", exc_info=True)
            return {"scene_modes": {}}
        scene_modes = data.get("scene_modes")
        if not isinstance(scene_modes, Mapping):
            scene_modes = {}
        return {"scene_modes": dict(scene_modes)}

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {"scene_modes": dict(self._state.get("scene_modes", {}))}
        self._state_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    def _manual_path(self, scene_id: str) -> Path:
        return self._manual_root / f"{scene_id}.json"

    def scene_mode(self, scene_id: str) -> str:
        with self._lock:
            modes = self._state.get("scene_modes", {})
            return str(modes.get(scene_id, "auto"))

    def set_scene_mode(self, scene_id: str, mode: str) -> None:
        if mode not in {"auto", "manual"}:
            raise ValueError("mode must be 'auto' or 'manual'")
        with self._lock:
            self._state.setdefault("scene_modes", {})[scene_id] = mode
            self._save_state()

    # ---------------------------------------------------------------- manual masks
    def _normalise_manual_planes(
        self, scene_id: str, payload: Any
    ) -> Optional[List[Dict[str, Any]]]:
        if isinstance(payload, Mapping):
            payload = payload.get("planes")
        if not isinstance(payload, list):
            LOGGER.debug("Manual depth payload for %s missing planes list", scene_id)
            return None
        planes: List[Dict[str, Any]] = []
        for index, entry in enumerate(payload):
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("name") or f"plane_{index}")
            depth = entry.get("depth")
            try:
                depth_value = float(depth) if depth is not None else index
            except (TypeError, ValueError):
                depth_value = float(index)
            planes.append(
                {
                    "name": name,
                    "depth": depth_value,
                    "mask": entry.get("mask"),
                    "meta": entry.get("meta") or {},
                }
            )
        return planes or None

    def load_manual_masks(self, scene_id: str) -> Optional[List[Dict[str, Any]]]:
        path = self._manual_path(scene_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - defensive
            LOGGER.warning("Failed to parse manual depth mask for %s", scene_id)
            return None
        return self._normalise_manual_planes(scene_id, payload)

    # ---------------------------------------------------------------- auto heuristic
    def auto_planes(
        self,
        *,
        plane_count: int = 4,
        image_size: Tuple[int, int] = (1920, 1080),
    ) -> List[Dict[str, Any]]:
        count = _clamp_plane_count(plane_count)
        width, height = image_size
        height = max(1, int(height))
        step = 1.0 / count
        planes: List[Dict[str, Any]] = []
        for index in range(count):
            near = index * step
            far = (index + 1) * step
            if index == 0:
                near = 0.0
            if index == count - 1:
                far = 1.0
            planes.append(
                {
                    "name": f"plane_{index}",
                    "depth": round((near + far) / 2, 4),
                    "bounds": {
                        "top": int(near * height),
                        "bottom": int(far * height),
                        "width": width,
                    },
                    "mask": None,
                    "meta": {"auto": True},
                }
            )
        return planes

    # ---------------------------------------------------------------- resolver
    def resolve(
        self,
        scene_id: str,
        *,
        plane_count: int = 4,
        image_size: Tuple[int, int] = (1920, 1080),
        prefer_manual: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Resolve depth planes for ``scene_id`` honoring feature flags and manual masks.

        Returns a payload with ``enabled`` (bool), ``mode`` (auto|manual), and ``planes``.
        """

        if not self.enabled:
            return {"enabled": False, "mode": "auto", "planes": []}

        mode = prefer_manual
        if mode is None:
            mode = self.scene_mode(scene_id) == "manual"

        manual_planes = self.load_manual_masks(scene_id) if mode else None
        if manual_planes:
            return {
                "enabled": True,
                "mode": "manual",
                "planes": manual_planes,
                "source": "manual",
            }

        auto = self.auto_planes(plane_count=plane_count, image_size=image_size)
        return {
            "enabled": True,
            "mode": "auto",
            "planes": auto,
            "source": "auto",
        }


DEPTH2D = Depth2DManager()


def resolve_depth_planes(
    scene_id: str,
    *,
    plane_count: int = 4,
    image_size: Tuple[int, int] = (1920, 1080),
    prefer_manual: Optional[bool] = None,
) -> Dict[str, Any]:
    return DEPTH2D.resolve(
        scene_id,
        plane_count=plane_count,
        image_size=image_size,
        prefer_manual=prefer_manual,
    )


def set_depth_scene_mode(scene_id: str, mode: str) -> None:
    DEPTH2D.set_scene_mode(scene_id, mode)


def load_manual_depth_masks(scene_id: str) -> Optional[List[Dict[str, Any]]]:
    return DEPTH2D.load_manual_masks(scene_id)


__all__ = [
    "DEPTH2D",
    "Depth2DManager",
    "resolve_depth_planes",
    "set_depth_scene_mode",
    "load_manual_depth_masks",
]
