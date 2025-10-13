# comfyvn/modules/sillytavern_bridge.py
# 🌐 SillyTavern Bridge – Async World Lore Sync (Patch L)
# ComfyVN Architect | Server Core Integration Sync
# [⚙️ 3. Server Core Production Chat]

import os, json, httpx
from typing import Optional, Any, Dict, List


class SillyTavernBridge:
    """Handles async data pulling from SillyTavern's world / lorebook API."""

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:8000/api/v1/lorebooks",
        token: Optional[str] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client: Optional[httpx.AsyncClient] = None

    # -------------------------------------------------
    # Lifecycle
    # -------------------------------------------------
    async def _get_client(self) -> httpx.AsyncClient:
        if not self.client:
            self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0))
        return self.client

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None

    # -------------------------------------------------
    # Fetch / Download
    # -------------------------------------------------
    async def fetch_worlds(self) -> List[Dict[str, Any]]:
        """Fetch available lorebooks / worlds from SillyTavern."""
        try:
            client = await self._get_client()
            r = await client.get(self.api_url, headers=self.headers)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[SillyTavernBridge] Failed to fetch worlds: {e}")
            return []

    async def download_world(
        self, world_id: str, save_path: str = "./data/worlds"
    ) -> Optional[str]:
        """Download and persist a lorebook JSON file by ID."""
        try:
            client = await self._get_client()
            r = await client.get(f"{self.api_url}/{world_id}", headers=self.headers)
            r.raise_for_status()
            data = r.json()
            os.makedirs(save_path, exist_ok=True)
            path = os.path.join(save_path, f"{world_id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[SillyTavernBridge] Downloaded → {path}")
            return path
        except Exception as e:
            print(f"[SillyTavernBridge] Download error: {e}")
            return None
