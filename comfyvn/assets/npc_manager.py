from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/modules/npc_manager.py
# 🧍 Asset & Sprite System Production Chat Implementation

import random, json, os


class NPCManager:
    """Generates faceless background NPCs for scenes."""

    def __init__(self, data_path="./data/npc"):
        self.data_path = data_path
        self.config = {
            "density": "medium",  # low | medium | high
            "detail": "faceless",  # faceless | shadow | silhouette
            "variation": True,
        }
        os.makedirs(self.data_path, exist_ok=True)

    def generate(self, scene_context: dict) -> list:
        """Generate placeholder NPCs based on scene context and density."""
        npc_count = {"low": 2, "medium": 5, "high": 10}.get(self.config["density"], 3)

        npcs = []
        for i in range(npc_count):
            detail = self.config["detail"]
            npc_id = f"npc_{i}_{random.randint(100,999)}"
            sprite = f"{detail}_npc.png"
            npcs.append(
                {
                    "id": npc_id,
                    "sprite": sprite,
                    "context": scene_context.get("location", "default"),
                }
            )

        return npcs

    def save_to_file(self, scene_id: str, npcs: list):
        """Cache NPCs to a JSON file for reuse."""
        path = os.path.join(self.data_path, f"{scene_id}_npcs.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(npcs, f, indent=2)

    def load_from_file(self, scene_id: str):
        """Load previously generated NPCs."""
        path = os.path.join(self.data_path, f"{scene_id}_npcs.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []