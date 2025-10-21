import logging
logger = logging.getLogger(__name__)
# comfyvn/modules/playground_manager.py
# 🧪 Playground Manager – Unified Scene & Pose Sandbox (v0.4.3)
# [ComfyVN Architect | Server Core + GUI Integration Sync]

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from comfyvn.assets.pose_manager import PoseManager
from comfyvn.assets.pose_utils import apply_delta


class PlaygroundManager:
    """
    Central manager for both prompt-driven scene mutations (NLP layer)
    and pose interpolation workflows (GUI + ComfyUI bridge).
    """

    def __init__(
        self,
        pose_dir: str | Path | None = None,
        delta_dir: str | Path = "./data/pose_deltas",
    ):
        # Prompt mutation memory
        self.history: Dict[str, List[str]] = {}

        # Pose management paths
        self.pose_dir = Path(pose_dir).expanduser() if pose_dir else None
        self.delta_dir = Path(delta_dir).expanduser()
        self.delta_dir.mkdir(parents=True, exist_ok=True)
        if self.pose_dir:
            self.pose_dir.mkdir(parents=True, exist_ok=True)
            self.pose_manager = PoseManager(self.pose_dir)
        else:
            self.pose_manager = PoseManager()

    # -------------------------------------------------
    # 🔤 Prompt Sandbox (from Patch E)
    # -------------------------------------------------
    def apply_prompt(self, scene_id: str, prompt: str) -> Dict[str, Any]:
        """Record a text mutation for a scene."""
        if not scene_id or not prompt:
            return {"status": "error", "message": "scene_id and prompt required"}
        self.history.setdefault(scene_id, []).append(prompt)
        print(f"[Playground] Applied prompt → {scene_id}: {prompt}")
        return {
            "scene_id": scene_id,
            "prompt": prompt,
            "status": "ok",
            "history_len": len(self.history[scene_id]),
        }

    def get_history(self, scene_id: str) -> List[str]:
        """Return the stored mutation history for a scene."""
        return self.history.get(scene_id, [])

    # -------------------------------------------------
    # 🧍 Pose Interpolation System
    # -------------------------------------------------
    def list_poses(self) -> List[Dict[str, Any]]:
        return self.pose_manager.list_poses()

    def get_pose(self, pose_id: str) -> Optional[Dict[str, Any]]:
        return self.pose_manager.get_pose(pose_id)

    def list_deltas(self) -> List[str]:
        if not self.delta_dir.exists():
            return []
        return sorted([path.name for path in self.delta_dir.glob("*.json")])

    def load_delta(self, name: str) -> Dict[str, Any]:
        path = self.delta_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    def interpolate(self, pose_a_id: str, delta_name: str, t: float) -> Dict[str, Any]:
        pose_a = self.get_pose(pose_a_id)
        delta = self.load_delta(delta_name)
        return apply_delta(pose_a, delta, t)

    def save_interpolated(self, pose_out: Dict[str, Any]) -> str:
        pid = pose_out.get("pose_id", "interpolated")
        self.pose_manager.add_pose(pid, pose_out)
        print(f"[Playground] 💾 Saved interpolated pose: {pid}")
        return pid
