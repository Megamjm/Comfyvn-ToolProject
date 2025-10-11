# comfyvn/modules/export_manager.py
# Export Manager — alpha-safe export + license snapshot + Asset Index
# ComfyVN_Architect (Asset Sprite Research Branch)

import os, json
from datetime import datetime
from typing import Dict, List, Optional

from comfyvn.modules.asset_index import add_record  # new

COMMUNITY_ASSET_PATH = "./comfyvn/data/community_assets_registry.json"

def _load_registry():
    try:
        with open(COMMUNITY_ASSET_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"verified_assets": [], "unverified_user": []}

class ExportManager:
    """Handles exporting of sprites, dumps, and asset bundles with style/control metadata."""

    def __init__(self, export_dir: str = "./exports/assets"):
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

    def _stampdir(self, prefix: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.export_dir, f"{prefix}_{ts}")
        os.makedirs(path, exist_ok=True)
        return path

    def _write_empty_png(self, file_path: str, with_alpha: bool = True):
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
        snapshot = {"sources": sources}
        with open(os.path.join(folder, "license.json"), "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)

    def export_character_dump(
        self,
        character_data: Dict,
        style_id: Optional[str] = None,
        control_stack: Optional[List[Dict]] = None,
        identity_profile: Optional[Dict] = None,
        sprite_png_bytes: Optional[bytes] = None,
        transparent: bool = True,
        sources: Optional[List[Dict]] = None
    ) -> str:
        char_id = character_data.get("id", "unknown")
        folder = self._stampdir(char_id)

        meta = {
            "type": "character",
            "id": char_id,
            "character": character_data,
            "style_id": style_id,
            "control_stack": control_stack or [],
            "identity_profile": identity_profile or {},
            "transparent": bool(transparent)
        }

        with open(os.path.join(folder, f"{char_id}.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        sprite_path = os.path.join(folder, f"{char_id}.png")
        if sprite_png_bytes:
            with open(sprite_path, "wb") as f:
                f.write(sprite_png_bytes)
        else:
            self._write_empty_png(sprite_path, with_alpha=True)

        # license snapshot
        self._write_license_snapshot(folder, sources or [])

        # asset index record
        add_record({
            "type": "character",
            "character": character_data,
            "style_id": style_id,
            "export_path": folder,
            "png_path": sprite_path
        })

        return folder

    def export_scene_layer(
        self,
        scene_id: str,
        assets: List[str],
        style_id: Optional[str] = None,
        control_stack: Optional[List[Dict]] = None,
        identity_profile: Optional[Dict] = None,
        transparent: bool = True,
        sources: Optional[List[Dict]] = None
    ) -> str:
        path = os.path.join(self.export_dir, f"{scene_id}_bundle.json")
        bundle = {
            "type": "scene",
            "scene_id": scene_id,
            "assets": assets,
            "style_id": style_id,
            "control_stack": control_stack or [],
            "identity_profile": identity_profile or {},
            "transparent": bool(transparent)
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        # asset index record
        add_record({
            "type": "scene",
            "scene_id": scene_id,
            "style_id": style_id,
            "export_path": path,
            "assets": assets
        })

        return path
        # license snapshot