# comfyvn/modules/world_loader.py
# 🌍 World Loader – Clean-State Sync + SillyTavern Integration (Synced v2.3)
# ComfyVN Architect — Production Standard (2025-10)
# [⚙️ 3. Server Core Production Chat]

import os, json, hashlib
from comfyvn.integrations.sillytavern_bridge import SillyTavernBridge


class WorldLoader:
    """Handles loading, merging, caching, and syncing of world lore files."""

    def __init__(self, data_path="./data/worlds"):
        self.data_path = data_path
        self.cache = {}
        self.active_world = "default_world.json"
        self.bridge = SillyTavernBridge()
        os.makedirs(data_path, exist_ok=True)

    # -----------------------------------------------------
    # JSON Utilities
    # -----------------------------------------------------
    def _read_json(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_json(self, path: str, data: dict):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _sha1(self, obj) -> str:
        """Stable checksum for dict or str."""
        if isinstance(obj, (dict, list)):
            obj = json.dumps(obj, sort_keys=True)
        return hashlib.sha1(str(obj).encode("utf-8")).hexdigest()

    # -----------------------------------------------------
    # Core Loading
    # -----------------------------------------------------
    def load_world(self, world_file: str | None = None) -> dict:
        file = world_file or self.active_world
        path = os.path.join(self.data_path, file)
        data = self._read_json(path)
        if data:
            self.cache[file] = data
            self.active_world = file
            print(f"[WorldLoader] Loaded {file}")
        return data

    def merge_worlds(self, files: list[str]) -> dict:
        merged = {"locations": {}, "lore": {}, "factions": {}, "rules": {}}
        for file in files:
            data = self._read_json(os.path.join(self.data_path, file))
            for key in merged.keys():
                merged[key].update(data.get(key, {}))
        self.cache["merged_world"] = merged
        self.active_world = "merged_world"
        print(f"[WorldLoader] Merged {files}")
        return merged

    def list_available_worlds(self) -> list[str]:
        return [f for f in os.listdir(self.data_path) if f.endswith(".json")]

    def get_location_theme(self, location_id: str) -> dict:
        world = self.cache.get(self.active_world, {})
        return world.get("locations", {}).get(location_id, {})

    # -----------------------------------------------------
    # Clean-State Sync (enhanced)
    # -----------------------------------------------------
    def sync_from_sillytavern(self) -> dict:
        """
        Pull and compare world data from SillyTavern.
        Returns:
          {"status": "success" | "no_change" | "fail", "updated": [...], "message": str}
        """
        try:
            remote_worlds = self.bridge.fetch_worlds()
            if not remote_worlds:
                return {
                    "status": "fail",
                    "updated": [],
                    "message": "No data from SillyTavern.",
                }

            updated = []
            for world in remote_worlds:
                wid = world.get("id") or world.get("name", "unknown_world")
                local_path = os.path.join(self.data_path, f"{wid}.json")
                remote_hash = self._sha1(world)
                local_hash = None

                if os.path.exists(local_path):
                    try:
                        local_hash = self._sha1(self._read_json(local_path))
                    except Exception:
                        local_hash = None

                if local_hash != remote_hash:
                    # New or changed
                    self.bridge.download_world(wid, self.data_path)
                    updated.append(wid)

            if updated:
                return {
                    "status": "success",
                    "updated": updated,
                    "message": "Worlds updated.",
                }
            return {
                "status": "no_change",
                "updated": [],
                "message": "No changes detected.",
            }

        except Exception as e:
            print(f"[WorldLoader] Sync Error: {e}")
            return {"status": "fail", "updated": [], "message": str(e)}

    # -----------------------------------------------------
    # Optional: Outdated Check (timestamp fallback)
    # -----------------------------------------------------
    def _is_outdated(self, file_path: str, remote: dict) -> bool:
        try:
            local = self._read_json(file_path)
            return local.get("updated_at") != remote.get("updated_at")
        except Exception:
            return True


def save_world(self, name: str, data: dict):
    """Save a world JSON file into data/worlds."""
    import json, os

    os.makedirs(self.data_path, exist_ok=True)
    file_path = os.path.join(self.data_path, f"{name}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    self.cache[name] = data
    print(f"[WorldLoader] Saved world: {name}")
