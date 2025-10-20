from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/assets/pose_utils.py
# 🧍 Pose Utilities — helper for blending/interpolating pose deltas
# [ComfyVN Architect | Safe Fallback Implementation]

import json, os
from pathlib import Path


def apply_delta(base_pose: dict, delta: dict, t: float = 1.0) -> dict:
    """
    Linearly interpolate numeric fields of a pose dictionary using a delta.
    Fallback-safe version: only applies to numeric values.
    """
    result = {}
    for k, v in base_pose.items():
        if isinstance(v, (int, float)) and k in delta:
            try:
                result[k] = v + (delta[k] - v) * t
            except Exception:
                result[k] = v
        else:
            result[k] = v
    return result


def load_pose(path: str | Path) -> dict:
    """Load a pose JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pose(data: dict, path: str | Path):
    """Save a pose JSON file safely."""
    path = Path(path)
    os.makedirs(path.parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def diff_pose(pose_a: dict, pose_b: dict) -> dict:
    """Compute numeric deltas between two poses."""
    delta = {}
    for k, v in pose_a.items():
        if (
            k in pose_b
            and isinstance(v, (int, float))
            and isinstance(pose_b[k], (int, float))
        ):
            delta[k] = pose_b[k] - v
    return delta


def list_pose_files(folder="./data/poses") -> list[str]:
    """List available pose JSON files."""
    path = Path(folder)
    if not path.exists():
        return []
    return [f.stem for f in path.glob("*.json")]