from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .autorig import generate_idle_cycle

Vec3 = Tuple[float, float, float]

DEFAULT_FPS = 24


def _round(value: float, digits: int = 4) -> float:
    return float(f"{value:.{digits}f}")


class MotionGraph:
    """
    Deterministic motion graph used to compose safe preview loops for 2.5D rigs.
    """

    def __init__(
        self,
        rig_payload: Mapping[str, Any],
        *,
        idle_cycle: Mapping[str, Any] | None = None,
    ) -> None:
        self._rig = rig_payload
        self._constraints: Mapping[str, Mapping[str, Any]] = rig_payload.get(
            "constraints", {}
        )
        self._bones: Sequence[Mapping[str, Any]] = rig_payload.get("bones", [])
        self._mouth_shapes: Mapping[str, Mapping[str, Any]] = rig_payload.get(
            "mouth_shapes", {}
        )
        self._idle_cycle = idle_cycle or generate_idle_cycle(rig_payload)

    def _bones_with_role(self, *roles: str) -> List[Mapping[str, Any]]:
        normalized = {role.lower() for role in roles}
        matches: List[Mapping[str, Any]] = []
        for bone in self._bones:
            role = str(bone.get("role") or "").lower()
            bone_id = str(bone.get("id") or "").lower()
            if role in normalized:
                matches.append(bone)
            elif any(role_key in bone_id for role_key in normalized):
                matches.append(bone)
        return matches

    def _guard_turn(self) -> bool:
        target_bones = self._bones_with_role("head", "neck", "spine")
        for bone in target_bones:
            limit = self._constraints.get(str(bone.get("id")), {}).get(
                "rotation_deg", {}
            )
            if (
                float(limit.get("max", 0.0)) >= 18.0
                and float(limit.get("min", 0.0)) <= -18.0
            ):
                return True
        return False

    def _guard_emote(self) -> bool:
        if not self._mouth_shapes:
            return False
        active = [shape for shape, payload in self._mouth_shapes.items() if payload]
        return bool(active)

    def _sample_idle(self, duration: float, fps: int) -> List[Dict[str, Any]]:
        idle = generate_idle_cycle(self._rig, duration=duration, fps=fps)
        frames = idle.get("frames", [])
        for frame in frames:
            frame["state"] = "idle"
        return frames

    def _sample_turn(self, duration: float, fps: int) -> List[Dict[str, Any]]:
        frames: List[Dict[str, Any]] = []
        frame_count = max(1, int(duration * fps))
        target_bones = self._bones_with_role("head", "neck", "spine")
        if not target_bones:
            return frames
        # use the most expressive bone as primary driver
        primary = target_bones[0]
        primary_limit = self._constraints.get(str(primary.get("id")), {}).get(
            "rotation_deg", {}
        )
        max_angle = min(
            45.0,
            float(primary_limit.get("max", 30.0)) * 0.8,
            abs(float(primary_limit.get("min", -30.0))) * 0.8,
        )
        sway_limit = self._constraints.get(str(primary.get("id")), {}).get(
            "translate", {}
        )
        sway_x = float(sway_limit.get("x", (0.0, 0.03))[1]) * 0.5

        for idx in range(frame_count):
            progress = idx / (frame_count - 1) if frame_count > 1 else 0.0
            swing = math.sin(progress * math.pi)  # 0 -> 1 -> 0
            angle = _round(swing * max_angle, 4)
            translate_x = _round(math.sin(progress * math.pi) * sway_x, 5)
            frame_bones: Dict[str, Any] = {}
            for bone in self._bones:
                bone_id = str(bone.get("id"))
                transform = {
                    "translate": [0.0, 0.0, 0.0],
                    "rotate": 0.0,
                    "scale": [1.0, 1.0, 1.0],
                }
                if bone_id == primary.get("id"):
                    transform["rotate"] = angle
                    transform["translate"][0] = translate_x
                elif bone in target_bones[1:]:
                    transform["rotate"] = _round(angle * 0.5, 4)
                    transform["translate"][0] = _round(translate_x * 0.5, 5)
                frame_bones[bone_id] = transform
            frames.append(
                {"time": _round(idx / fps, 5), "bones": frame_bones, "state": "turn"}
            )
        return frames

    def _sample_emote(
        self, duration: float, fps: int, sequence: Sequence[str] | None = None
    ) -> List[Dict[str, Any]]:
        shapes = {key: value for key, value in self._mouth_shapes.items() if value}
        if not shapes:
            return []
        frame_count = max(1, int(duration * fps))
        sequence = sequence or ["A", "I", "U", "E", "O"]
        active_sequence = [shape for shape in sequence if shape in shapes]
        if not active_sequence:
            active_sequence = list(shapes.keys())
        frame_segments = max(1, frame_count // max(1, len(active_sequence)))
        frames: List[Dict[str, Any]] = []

        for idx in range(frame_count):
            seq_index = min(idx // frame_segments, len(active_sequence) - 1)
            shape_name = active_sequence[seq_index]
            shape_payload = shapes.get(shape_name, {})
            local_progress = (idx % frame_segments) / max(1, frame_segments - 1)
            ease = math.sin(local_progress * math.pi)
            frame_bones: Dict[str, Any] = {}
            for bone in self._bones:
                bone_id = str(bone.get("id"))
                base = {
                    "translate": [0.0, 0.0, 0.0],
                    "rotate": 0.0,
                    "scale": [1.0, 1.0, 1.0],
                }
                if bone_id in shape_payload:
                    target = shape_payload[bone_id]
                    base["translate"] = [
                        _round(target["translate"][axis] * ease, 5) for axis in range(3)
                    ]
                    base["rotate"] = _round(target["rotate"] * ease, 4)
                    base["scale"] = [
                        _round(1.0 + (target["scale"][axis] - 1.0) * ease, 4)
                        for axis in range(3)
                    ]
                frame_bones[bone_id] = base
            frames.append(
                {
                    "time": _round(idx / fps, 5),
                    "bones": frame_bones,
                    "state": "emote",
                    "shape": shape_name,
                }
            )
        return frames

    def generate_preview_loop(
        self,
        *,
        duration: float = 4.0,
        fps: int = DEFAULT_FPS,
    ) -> Dict[str, Any]:
        fps = max(12, int(fps))
        duration = max(3.0, float(duration))

        idle_duration = min(
            duration * 0.35, max(1.0, self._idle_cycle.get("duration", 1.8))
        )
        turn_duration = 0.9 if self._guard_turn() else 0.6
        emote_duration = 1.2 if self._guard_emote() else 0.7
        tail_duration = max(
            0.6, duration - (idle_duration + turn_duration + emote_duration)
        )

        frames: List[Dict[str, Any]] = []
        frames.extend(self._sample_idle(idle_duration, fps))
        if self._guard_turn():
            frames.extend(self._sample_turn(turn_duration, fps))
        else:
            frames.extend(self._sample_idle(turn_duration, fps))

        if self._guard_emote():
            frames.extend(self._sample_emote(emote_duration, fps))
        else:
            frames.extend(self._sample_idle(emote_duration, fps))

        # Tail idle segment to complete the loop smoothly.
        frames.extend(self._sample_idle(tail_duration, fps))

        if not frames:
            return {"frames": [], "fps": fps, "duration": 0.0}

        for idx, frame in enumerate(frames):
            frame["time"] = _round(idx / fps, 5)
        return {
            "frames": frames,
            "fps": fps,
            "duration": _round(len(frames) / fps, 5),
            "states": [frame.get("state", "idle") for frame in frames],
        }


__all__ = ["MotionGraph"]
