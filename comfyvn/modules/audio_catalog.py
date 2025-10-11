# comfyvn/modules/audio_catalog.py
# 📚 Curated “packs”, quotas, and install policy
# [⚙️ 3. Server Core Production Chat]

from __future__ import annotations
from typing import Dict, List

DEFAULT_QUOTAS = {
    "ui": 20,
    "sfx": 60,
    "ambience": 40,
    "music": 30,
    "foley": 40,
    "stinger": 20,
    "footsteps": 20,
    "weather": 20
}

# Pack descriptors can refer to provider+id combos
# Example: {"name":"Minimal VN UI","assets":[{"provider":"kenney","id":"ui-click-01"}, ...]}
class AudioCatalog:
    def __init__(self):
        self.quotas = dict(DEFAULT_QUOTAS)
        self.packs: List[Dict] = []

    def set_quotas(self, quotas: Dict[str,int]) -> Dict[str,int]:
        self.quotas.update({k:int(v) for k,v in quotas.items()})
        return dict(self.quotas)

    def list_quotas(self) -> Dict[str,int]:
        return dict(self.quotas)

    def register_pack(self, pack: Dict) -> Dict:
        self.packs.append(pack)
        return {"ok": True, "count": len(self.packs)}

    def list_packs(self) -> List[Dict]:
        return list(self.packs)
