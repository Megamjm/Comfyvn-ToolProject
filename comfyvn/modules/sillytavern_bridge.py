# comfyvn/modules/sillytavern_bridge.py
# 🌐 SillyTavern Bridge (World Lore Sync)

import requests
import os
import json

class SillyTavernBridge:
    """Handles data pulling from SillyTavern world/lore system."""

    def __init__(self, api_url="http://127.0.0.1:8000/api/v1/lorebooks", token=None):
        self.api_url = api_url
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def fetch_worlds(self):
        """Fetch available lorebooks/worlds from SillyTavern."""
        try:
            response = requests.get(self.api_url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[SillyTavernBridge] Failed to fetch worlds: {e}")
            return []

    def download_world(self, world_id, save_path="./data/worlds"):
        """Download specific lorebook/world file."""
        try:
            r = requests.get(f"{self.api_url}/{world_id}", headers=self.headers)
            r.raise_for_status()
            data = r.json()
            os.makedirs(save_path, exist_ok=True)
            file_path = os.path.join(save_path, f"{world_id}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"[SillyTavernBridge] Downloaded: {file_path}")
            return file_path
        except Exception as e:
            print(f"[SillyTavernBridge] Download error: {e}")
            return None
