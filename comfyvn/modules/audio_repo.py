# comfyvn/modules/audio_repo.py
# 🔎 Audio provider registry, catalog loading & search
# [⚙️ 3. Server Core Production Chat]

from __future__ import annotations
import os, json
from pathlib import Path
from typing import List, Dict, Optional
from .audio_sources import AudioAsset

CATALOG_DIR = Path("./data/audio/providers").resolve()
CATALOG_DIR.mkdir(parents=True, exist_ok=True)

# Each provider has a manifest JSON file with a list of AudioAsset-like dicts.
# Example file: data/audio/providers/kenney.json


class AudioRepo:
    def __init__(self, providers: Optional[List[str]] = None):
        self.providers = providers or ["kenney", "freepd", "pixabay", "opengameart"]
        self._cache: Dict[str, List[Dict]] = {}

    def list_providers(self) -> List[str]:
        return list(self.providers)

    def _manifest_path(self, provider: str) -> Path:
        return CATALOG_DIR / f"{provider}.json"

    def load_catalog(self, provider: str) -> List[Dict]:
        if provider in self._cache:
            return self._cache[provider]
        path = self._manifest_path(provider)
        if not path.exists():
            # Create an empty manifest placeholder for admins to fill later
            path.write_text("[]", encoding="utf-8")
            self._cache[provider] = []
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
        self._cache[provider] = data
        return data

    def all_assets(self) -> List[Dict]:
        out: List[Dict] = []
        for p in self.providers:
            out.extend(self.load_catalog(p))
        return out

    def search(
        self,
        q: Optional[str] = None,
        license_filter: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        provider: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict]:
        records = self.load_catalog(provider) if provider else self.all_assets()

        def keep(x: Dict) -> bool:
            if license_filter and x.get("license") not in license_filter:
                return False
            if categories and x.get("category") not in categories:
                return False
            if q:
                ql = q.lower()
                if ql not in (
                    x.get("title", "").lower()
                    + " "
                    + " ".join(x.get("tags", [])).lower()
                    + " "
                    + x.get("provider", "").lower()
                ):
                    return False
            return True

        result = [r for r in records if keep(r)]
        return result[:limit]
