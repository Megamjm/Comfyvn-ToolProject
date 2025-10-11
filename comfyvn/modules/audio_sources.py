# comfyvn/modules/audio_sources.py
# 🎼 Audio schema, licenses, helpers
# [⚙️ 3. Server Core Production Chat]

from __future__ import annotations
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, asdict

# Common licenses we’ll surface in the UI
License = Literal["CC0", "CC-BY", "CC-BY-3.0", "CC-BY-4.0", "Public-Domain", "Pixabay", "OGA-Mixed", "Unknown"]

# Categories used in VN projects
Category = Literal["ui", "sfx", "foley", "ambience", "music", "voice", "stinger", "footsteps", "weather", "ui-click"]

@dataclass
class AudioAsset:
    id: str
    title: str
    provider: str
    category: Category
    license: License
    tags: List[str]
    format: str           # "wav","mp3","ogg","flac"
    duration_sec: float
    preview_url: Optional[str]  # remote preview or will be local after caching
    download_url: Optional[str] # direct file url or zip file url
    pack_name: Optional[str] = None
    checksum: Optional[str] = None  # optional integrity check
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)
