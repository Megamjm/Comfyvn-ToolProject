# comfyvn/modules/export_manager.py
# 🧩 Export Manager – Asset / Scene / Ren'Py Exporter (Patch O)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import os, shutil, json
from datetime import datetime
from typing import List, Dict, Any

class ExportManager:
    """Handles exporting of sprites, scene layers, and VN script bundles."""

    def __init__(self, export_dir: str = "./exports/assets"):
        self.export_dir = os.path.abspath(export_dir)
        os.makedirs(self.export_dir, exist_ok=True)

    # -------------------------------------------------
    # Character Export
    # -------------------------------------------------
    def export_character_dump(self, character_data: Dict[str, Any]) -> str:
        """
        Export full character sprite data to a JSON + PNG pair.
        If sprite file exists in character_data["sprite"], copy it to output.
        """
        char_id = character_data.get("id", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(self.export_dir, f"{char_id}_{timestamp}")
        os.makedirs(folder, exist_ok=True)

        # Metadata JSON
        meta_path = os.path.join(folder, f"{char_id}.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(character_data, f, indent=2, ensure_ascii=False)

        # Sprite handling
        sprite_src = character_data.get("sprite")
        sprite_dest = os.path.join(folder, f"{char_id}.png")
        try:
            if sprite_src and os.path.exists(sprite_src):
                shutil.copy(sprite_src, sprite_dest)
            else:
                with open(sprite_dest, "wb") as f:
                    f.write(b"")  # placeholder file
            print(f"[ExportManager] Exported character '{char_id}' → {folder}")
        except Exception as e:
            print(f"[ExportManager] Sprite copy error: {e}")

        return folder

    # -------------------------------------------------
    # Scene Layer Export
    # -------------------------------------------------
    def export_scene_layer(self, scene_id: str, assets: List[Dict[str, Any]]) -> str:
        """
        Export a scene layer bundle (background + sprites + effects).
        """
        bundle_path = os.path.join(self.export_dir, f"{scene_id}_bundle.json")
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump({"scene": scene_id, "assets": assets}, f, indent=2, ensure_ascii=False)
        print(f"[ExportManager] Scene bundle saved → {bundle_path}")
        return bundle_path

    # -------------------------------------------------
    # Ren'Py Export Hook
    # -------------------------------------------------
    def export_to_renpy(self, scene_graph: List[Dict[str, Any]], renpy_dir: str = "./exports/renpy") -> str:
        """
        Converts a scene JSON graph into Ren'Py script files.
        Each scene becomes a label with dialogue lines.
        """
        os.makedirs(renpy_dir, exist_ok=True)
        for scene in scene_graph:
            file_name = f"{scene.get('scene_id', 'scene')}.rpy"
            path = os.path.join(renpy_dir, file_name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"label {scene.get('scene_id', 'scene')}:\n")
                for line in scene.get("lines", []):
                    f.write(f'    "{line.get("speaker", "??")}": "{line.get("text", "")}"\n')
            print(f"[ExportManager] Wrote Ren'Py scene → {path}")
        return renpy_dir
