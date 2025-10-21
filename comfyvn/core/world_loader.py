from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/modules/world_loader.py
# 🌍 World Loader – Clean-State Sync + SillyTavern Integration (Synced v2.3)
# ComfyVN Architect — Production Standard (2025-10)
# [⚙️ 3. Server Core Production Chat]

import os, json, hashlib, shutil
from pathlib import Path
from comfyvn.integrations.sillytavern_bridge import SillyTavernBridge, SillyTavernBridgeError
from comfyvn.config.runtime_paths import data_dir


class WorldLoader:
    """Handles loading, merging, caching, and syncing of world lore files."""

    def __init__(self, data_path: str | None = None):
        resolved_path = data_dir("worlds") if data_path is None else data_path
        self.data_path = resolved_path
        self.cache = {}
        self.active_world = "default_world.json"
        self.bridge = SillyTavernBridge()
        os.makedirs(self.data_path, exist_ok=True)
        self._ensure_default_world()

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

    def configure_remote(
        self,
        *,
        base_url: str | None = None,
        plugin_base: str | None = None,
        token: str | None = None,
        user_id: str | None = None,
        persist: bool = False,
    ) -> None:
        """Update the SillyTavern bridge endpoint."""
        self.bridge.set_endpoint(
            base_url=base_url,
            plugin_base=plugin_base,
            token=token,
            user_id=user_id,
            persist=persist,
        )

    def _ensure_default_world(self) -> None:
        """Copy packaged default worlds into the user data directory if missing."""
        base = Path(__file__).resolve().parents[2] / "defaults" / "worlds"
        if not base.exists():
            return
        destination = Path(self.data_path)
        placeholder_missing = not (Path(self.data_path) / self.active_world).exists()
        for source in base.glob("*.json"):
            target = destination / source.name
            if not target.exists():
                try:
                    shutil.copy2(source, target)
                except OSError:
                    continue
            if placeholder_missing:
                self.active_world = target.name
                placeholder_missing = False

    # -----------------------------------------------------
    # Clean-State Sync (enhanced)
    # -----------------------------------------------------
    def sync_from_sillytavern(self, *, user_id: str | None = None) -> dict:
        """
        Pull and compare world data from SillyTavern.
        Returns:
          {"status": "success" | "no_change" | "fail", "updated": [...], "message": str}
        """
        try:
            remote_worlds = self.bridge.fetch_worlds(user_id=user_id)
            if not remote_worlds:
                return {
                    "status": "fail",
                    "updated": [],
                    "message": "No data from SillyTavern.",
                }

            updated = []
            for world in remote_worlds:
                wid = world.get("id") or world.get("name") or "unknown_world.json"
                if not wid.lower().endswith(".json"):
                    wid = f"{wid}.json"
                local_path = os.path.join(self.data_path, wid)
                remote_data = world.get("data") or {}
                remote_hash = self._sha1(remote_data)
                local_hash = None

                if os.path.exists(local_path):
                    try:
                        local_hash = self._sha1(self._read_json(local_path))
                    except Exception:
                        local_hash = None

                if local_hash != remote_hash:
                    # New or changed
                    self._write_json(local_path, remote_data)
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

        except SillyTavernBridgeError as exc:
            logger.warning("World sync failed via SillyTavern bridge: %s", exc)
            return {"status": "fail", "updated": [], "message": str(exc)}
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("WorldLoader encountered an unexpected error during sync")
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
