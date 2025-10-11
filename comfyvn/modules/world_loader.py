# comfyvn/modules/world_loader.py
# 🌍 World Loader with Clean-State Sync and SillyTavern Integration
# ComfyVN Architect — Production Standard (2025-10)

import json, os
from modules.sillytavern_bridge import SillyTavernBridge


class WorldLoader:
    """Handles loading, merging, caching, and syncing of world lore files."""

    def __init__(self, data_path="./data/worlds"):
        self.data_path = data_path
        self.cache = {}
        self.active_world = "default_world.json"
        self.bridge = SillyTavernBridge()
        os.makedirs(data_path, exist_ok=True)

    # -----------------------------
    # Core JSON Loading
    # -----------------------------
    def _read_json(self, file_path: str) -> dict:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"[WorldLoader] Missing file: {file_path}")
        except json.JSONDecodeError:
            print(f"[WorldLoader] Corrupt JSON: {file_path}")
        return {}

    # -----------------------------
    # Primary Loading Methods
    # -----------------------------
    def load_world(self, world_file: str = None) -> dict:
        file = world_file or self.active_world
        path = os.path.join(self.data_path, file)
        data = self._read_json(path)
        if data:
            self.cache[file] = data
            self.active_world = file
            print(f"[WorldLoader] Loaded: {file}")
        return data

    def merge_worlds(self, files: list) -> dict:
        merged = {"locations": {}, "lore": {}, "factions": {}, "rules": {}}
        for file in files:
            data = self._read_json(os.path.join(self.data_path, file))
            for key in merged.keys():
                if key in data:
                    merged[key].update(data[key])
        self.cache["merged_world"] = merged
        self.active_world = "merged_world"
        print(f"[WorldLoader] Merged: {files}")
        return merged

    def get_location_theme(self, location_id: str) -> dict:
        world = self.cache.get(self.active_world, {})
        return world.get("locations", {}).get(location_id, {})

    def list_available_worlds(self) -> list:
        return [f for f in os.listdir(self.data_path) if f.endswith(".json")]

    # -----------------------------
    # Clean-State Sync
    # -----------------------------
    def sync_from_sillytavern(self) -> dict:
        """Sync worlds manually with clean status reporting."""
        try:
            remote_worlds = self.bridge.fetch_worlds()
            if not remote_worlds:
                return {
                    "status": "fail",
                    "updated": [],
                    "message": "No data received from SillyTavern (check URL or server)."
                }

            updated = []
            for world in remote_worlds:
                world_id = world.get("id") or world.get("name", "unknown_world")
                file_path = os.path.join(self.data_path, f"{world_id}.json")

                # Check if world is outdated or missing
                if not os.path.exists(file_path) or self._is_outdated(file_path, world):
                    self.bridge.download_world(world_id, self.data_path)
                    updated.append(world_id)

            if updated:
                return {"status": "success", "updated": updated, "message": "Worlds updated successfully."}
            else:
                return {"status": "no_changes", "updated": [], "message": "No changes detected."}

        except Exception as e:
            print(f"[WorldLoader] Sync Error: {e}")
            return {"status": "fail", "updated": [], "message": str(e)}

    def _is_outdated(self, file_path, remote_data):
        """Basic version/timestamp comparison."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                local = json.load(f)
            return local.get("updated_at") != remote_data.get("updated_at")
        except Exception:
            return True
