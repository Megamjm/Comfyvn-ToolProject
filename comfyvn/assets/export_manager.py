# comfyvn/modules/export_manager.py
# 🧍 Export Manager v0.4 — Pose, License, and Asset Index Integration
# ComfyVN_Architect (Unified Asset Sprite System)

import os
import json
from datetime import datetime
from typing import Dict, List, Optional

# --- Linked Modules ---
from comfyvn.modules.pose_manager import PoseManager
from comfyvn.modules.asset_index import add_record  # global registry for all assets

# --- Community asset registry for license verification ---
COMMUNITY_ASSET_PATH = "./comfyvn/data/community_assets_registry.json"


def _load_registry():
    """Load verified/unverified community asset info for license tracking."""
    try:
        with open(COMMUNITY_ASSET_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"verified_assets": [], "unverified_user": []}


class ExportManager:
    """
    Handles exporting of sprites, dumps, and asset bundles.
    Integrates:
    - Pose metadata and registry sync
    - Alpha-safe sprite creation
    - License snapshot generation
    - Asset Index registry updates
    """

    def __init__(self, export_dir: str = "./exports/assets"):
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

        # linked managers
        self.pose_manager = PoseManager()
        self.community_registry = _load_registry()

    # ------------------------------------------------------------
    # 🔧 Utility Helpers
    # ------------------------------------------------------------
    def _stampdir(self, prefix: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.export_dir, f"{prefix}_{ts}")
        os.makedirs(path, exist_ok=True)
        return path

    def _write_empty_png(self, file_path: str, with_alpha: bool = True):
        """Write a 1x1 transparent or opaque PNG placeholder for missing sprites."""
        rgba_1x1_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
            b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00"
            b"\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        rgb_1x1_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
            b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with open(file_path, "wb") as f:
            f.write(rgba_1x1_png if with_alpha else rgb_1x1_png)

    def _write_license_snapshot(self, folder: str, sources: List[Dict]):
        """Write license snapshot file containing attribution and verification info."""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "sources": sources,
            "verified_assets": self.community_registry.get("verified_assets", []),
        }
        with open(os.path.join(folder, "license.json"), "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)

    # ------------------------------------------------------------
    # 💾 CHARACTER EXPORT
    # ------------------------------------------------------------
    def export_character_dump(
        self,
        character_data: Dict,
        style_id: Optional[str] = None,
        control_stack: Optional[List[Dict]] = None,
        identity_profile: Optional[Dict] = None,
        pose_id: Optional[str] = None,
        sprite_png_bytes: Optional[bytes] = None,
        transparent: bool = True,
        sources: Optional[List[Dict]] = None,
    ) -> str:
        """Export full character sprite with pose, license, and asset index metadata."""
        char_id = character_data.get("id", "unknown")
        folder = self._stampdir(char_id)

        # --- Pose integration ---
        pose_data = None
        if pose_id:
            pose_data = self.pose_manager.get_pose(pose_id)
            if not pose_data:
                print(f"[WARN] Pose '{pose_id}' not found in registry.")
            else:
                self.pose_manager.registry[pose_id] = pose_data
                self.pose_manager._save_registry()
                print(f"[OK] Linked pose '{pose_id}' for {char_id}.")

        # --- Metadata assembly ---
        meta = {
            "type": "character",
            "id": char_id,
            "character": character_data,
            "style_id": style_id,
            "control_stack": control_stack or [],
            "identity_profile": identity_profile or {},
            "pose_id": pose_id,
            "pose_data": pose_data,
            "transparent": bool(transparent),
            "export_time": datetime.now().isoformat(),
        }

        # Write metadata JSON
        meta_path = os.path.join(folder, f"{char_id}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # --- Sprite export ---
        sprite_path = os.path.join(folder, f"{char_id}.png")
        if sprite_png_bytes:
            with open(sprite_path, "wb") as f:
                f.write(sprite_png_bytes)
        else:
            self._write_empty_png(sprite_path, with_alpha=True)

        # --- License snapshot ---
        self._write_license_snapshot(folder, sources or [])

        # --- Asset Index sync ---
        add_record({
            "type": "character",
            "character": character_data,
            "style_id": style_id,
            "pose_id": pose_id,
            "export_path": folder,
            "png_path": sprite_path,
            "control_stack": control_stack or [],
            "identity_profile": identity_profile or {},
            "license_sources": sources or []
        })

        print(f"[EXPORT] Character '{char_id}' exported to {folder}")
        return folder

    # ------------------------------------------------------------
    # 🧩 SCENE EXPORT
    # ------------------------------------------------------------
    def export_scene_layer(
        self,
        scene_id: str,
        assets: List[str],
        style_id: Optional[str] = None,
        control_stack: Optional[List[Dict]] = None,
        identity_profile: Optional[Dict] = None,
        pose_ids: Optional[List[str]] = None,
        transparent: bool = True,
        sources: Optional[List[Dict]] = None,
    ) -> str:
        """Export a full scene bundle (background + characters + poses)."""
        path = os.path.join(self.export_dir, f"{scene_id}_bundle.json")

        # --- Pose embedding ---
        pose_entries = []
        if pose_ids:
            for pid in pose_ids:
                pose = self.pose_manager.get_pose(pid)
                if pose:
                    pose_entries.append(pose)

        bundle = {
            "type": "scene",
            "scene_id": scene_id,
            "assets": assets,
            "style_id": style_id,
            "control_stack": control_stack or [],
            "identity_profile": identity_profile or {},
            "poses_used": pose_entries,
            "transparent": bool(transparent),
            "export_time": datetime.now().isoformat(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        # --- Asset Index sync ---
        add_record({
            "type": "scene",
            "scene_id": scene_id,
            "style_id": style_id,
            "export_path": path,
            "assets": assets,
            "poses_used": pose_entries,
            "license_sources": sources or []
        })

        # --- License snapshot ---
        if sources:
            license_folder = os.path.dirname(path)
            self._write_license_snapshot(license_folder, sources)

        print(f"[EXPORT] Scene '{scene_id}' exported with {len(pose_entries)} poses.")
        return path

    # ------------------------------------------------------------
    # 🔁 POSE SYNC UTILITY
    # ------------------------------------------------------------
    def sync_existing_exports(self) -> int:
        """Re-scan exports and ensure PoseManager registry includes all poses."""
        synced = 0
        for root, _, files in os.walk(self.export_dir):
            for file in files:
                if file.endswith(".json"):
                    path = os.path.join(root, file)
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "pose_id" in data and data["pose_id"]:
                        pid = data["pose_id"]
                        if pid not in self.pose_manager.registry and "pose_data" in data:
                            self.pose_manager.registry[pid] = data["pose_data"]
                            synced += 1
        if synced > 0:
            self.pose_manager._save_registry()
            print(f"[SYNC] {synced} new poses synced into PoseManager registry.")
        return synced
