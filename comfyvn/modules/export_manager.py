# comfyvn/modules/export_manager.py
# 🧍 Asset & Sprite System Production Chat Implementation

import os, shutil, json
from datetime import datetime

class ExportManager:
    """Handles exporting of sprites, dumps, and asset bundles."""

    def __init__(self, export_dir="./exports/assets"):
        self.export_dir = export_dir
        os.makedirs(export_dir, exist_ok=True)

    def export_character_dump(self, character_data: dict):
        """Export full character sprite data to a .json + .png pair."""
        char_id = character_data.get("id", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(self.export_dir, f"{char_id}_{timestamp}")
        os.makedirs(folder, exist_ok=True)

        # Save metadata
        meta_path = os.path.join(folder, f"{char_id}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(character_data, f, indent=2)

        # Copy or simulate sprite export
        sprite_path = os.path.join(folder, f"{char_id}.png")
        with open(sprite_path, "wb") as f:
            f.write(b"")  # placeholder empty sprite file

        return folder

    def export_scene_layer(self, scene_id: str, assets: list):
        """Export a scene layer bundle (background + sprites + effects)."""
        path = os.path.join(self.export_dir, f"{scene_id}_bundle.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"scene": scene_id, "assets": assets}, f, indent=2)
        return path
