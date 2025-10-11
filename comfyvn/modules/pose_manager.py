# comfyvn/modules/pose_manager.py
# 🧍 PoseManager – Fetches, imports, and manages pose libraries (ComfyVN_Architect)

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional

class PoseManager:
    """
    Handles automatic fetching, parsing, and indexing of pose packs
    from open repositories (e.g. Pose Depot, OpenPoses.com).
    """

    def __init__(self, base_dir: str = "./assets/poses"):
        self.base_dir = base_dir
        self.registry_path = os.path.join(self.base_dir, "pose_index.json")
        os.makedirs(self.base_dir, exist_ok=True)
        self.registry: Dict[str, dict] = {}

        if os.path.exists(self.registry_path):
            with open(self.registry_path, "r", encoding="utf-8") as f:
                self.registry = json.load(f)

    # -----------------------------------------------------------
    # 📦 Pose Fetching
    # -----------------------------------------------------------
    def fetch_pose_pack(self, url: str, pack_name: str):
        """
        Download a remote JSON pose pack (if available) and register poses.
        Supports public JSON URLs (e.g. from Pose Depot / HuggingFace repos).
        """
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[ERROR] Failed to fetch pose pack '{pack_name}': {e}")
            return None

        if not isinstance(data, dict) or "poses" not in data:
            print(f"[WARN] Pose pack format invalid at {url}")
            return None

        poses = data["poses"]
        for pose_id, pose_info in poses.items():
            entry = {
                "pose_id": pose_id,
                "metadata": {
                    "source": pack_name,
                    "imported_at": datetime.now().isoformat()
                },
                "skeleton": pose_info.get("skeleton", {}),
                "preview_image": pose_info.get("preview", "")
            }
            self.registry[pose_id] = entry

        self._save_registry()
        print(f"[OK] Imported {len(poses)} poses from {pack_name}")
        return poses

    # -----------------------------------------------------------
    # 📂 Local Import
    # -----------------------------------------------------------
    def import_local_pose_folder(self, folder_path: str, pack_name: str):
        """
        Import all JSON skeleton files from a local folder.
        """
        count = 0
        for fname in os.listdir(folder_path):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(folder_path, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    skeleton = json.load(f)
                pose_id = os.path.splitext(fname)[0]
                entry = {
                    "pose_id": pose_id,
                    "metadata": {"source": pack_name},
                    "skeleton": skeleton,
                    "preview_image": ""
                }
                self.registry[pose_id] = entry
                count += 1
            except Exception as e:
                print(f"[WARN] Skipped {fname}: {e}")

        self._save_registry()
        print(f"[OK] Imported {count} local poses from {pack_name}")
        return count

    # -----------------------------------------------------------
    # 🔎 Accessors
    # -----------------------------------------------------------
    def list_poses(self) -> List[str]:
        return list(self.registry.keys())

    def get_pose(self, pose_id: str) -> Optional[dict]:
        return self.registry.get(pose_id)

    def _save_registry(self):
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2)

    # -----------------------------------------------------------
    # 🔁 Auto Fetch Utility
    # -----------------------------------------------------------
    def auto_fetch_all(self):
        """
        Automatically fetch open pose sources and register them.
        These sources are known to contain JSON-based or convertible pose data.
        """
        sources = {
            "PoseDepot": "https://raw.githubusercontent.com/a-lgil/pose-depot/main/poses.json",
            "DynamicPosePackage": "https://raw.githubusercontent.com/NextDiffusionAI/dynamic-pose-package/main/poses.json",
            "OpenPoses": "https://raw.githubusercontent.com/openposes/openposes/main/data/poses.json"
        }

        for name, url in sources.items():
            print(f"Fetching {name}...")
            self.fetch_pose_pack(url, name)
