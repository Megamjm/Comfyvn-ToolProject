# comfyvn/assets/pose_manager.py
# 🧍 Pose Manager — Handles pose registry, metadata, and auto-fetch
# Integrated for ComfyVN v0.4-dev (Phase 3.4)
# Works with: comfyvn/gui/pose_browser.py  &  comfyvn/gui/asset_browser.py

import os, json
from datetime import datetime


class PoseManager:
    """Central registry and loader for character poses."""

    def __init__(self, data_path: str = "./data/poses"):
        self.data_path = os.path.abspath(data_path)
        os.makedirs(self.data_path, exist_ok=True)
        self.registry = self._load_registry()

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------
    def _pose_file(self, pose_id: str) -> str:
        """Return absolute path to a pose’s JSON file."""
        return os.path.join(self.data_path, f"{pose_id}.json")

    def _load_registry(self) -> dict:
        """Load all pose JSON files from disk into memory."""
        registry = {}
        for root, _, files in os.walk(self.data_path):
            for f in files:
                if not f.endswith(".json"):
                    continue
                pose_id = os.path.splitext(f)[0]
                try:
                    with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                        registry[pose_id] = json.load(fh)
                except Exception as e:
                    print(f"[PoseManager] ⚠️ Failed to load {f}: {e}")
        print(f"[PoseManager] Loaded {len(registry)} poses from {self.data_path}")
        return registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_pose(self, pose_id: str) -> dict | None:
        """Retrieve a single pose by ID."""
        return self.registry.get(pose_id)

    def list_poses(self) -> list[str]:
        """Return a list of all pose IDs."""
        return list(self.registry.keys())

    def add_pose(self, pose_id: str, data: dict):
        """Add or update a pose and persist it to disk."""
        self.registry[pose_id] = data
        path = self._pose_file(pose_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[PoseManager] ✅ Saved pose '{pose_id}'")
        except Exception as e:
            print(f"[PoseManager] ❌ Failed to save '{pose_id}': {e}")

    def delete_pose(self, pose_id: str):
        """Delete a pose JSON and remove it from registry."""
        if pose_id in self.registry:
            del self.registry[pose_id]
        try:
            os.remove(self._pose_file(pose_id))
            print(f"[PoseManager] 🗑 Deleted pose '{pose_id}'")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[PoseManager] ⚠️ Delete failed for '{pose_id}': {e}")

    def auto_fetch_all(self):
        """Simulate downloading sample pose packs from online repositories."""
        print("[PoseManager] 🌐 Simulating pose pack fetch...")
        demo_pose = {
            "pose_id": "standing_default",
            "preview_image": "",
            "metadata": {
                "source": "builtin",
                "imported_at": datetime.now().isoformat(),
                "description": "Basic upright standing pose.",
            },
            "skeleton": {
                "hip": [0, 0],
                "spine": [0, 0.5],
                "head": [0, 1],
                "left_arm": [-0.3, 0.6],
                "right_arm": [0.3, 0.6],
            },
        }
        self.add_pose(demo_pose["pose_id"], demo_pose)
        print("[PoseManager] ✅ Demo pose pack fetched successfully.")

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def summary(self) -> str:
        """Return a text summary of the registry contents."""
        return f"PoseManager: {len(self.registry)} poses loaded from {self.data_path}"


# ----------------------------------------------------------------------
# Self-test block — used by Auto-Heal or manual verification
# ----------------------------------------------------------------------
if __name__ == "__main__":
    pm = PoseManager()
    print(pm.summary())

    if not pm.list_poses():
        print("[PoseManager] No poses found; generating demo pose...")
        pm.auto_fetch_all()
        print(pm.summary())
    else:
        print(f"[PoseManager] Existing poses: {pm.list_poses()}")
