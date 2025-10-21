from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional
from comfyvn.config.runtime_paths import audio_cache_file

LOGGER = logging.getLogger("comfyvn.audio.cache")
CACHE_PATH = audio_cache_file()


@dataclass
class AudioCacheEntry:
    key: str
    artifact: str
    sidecar: Optional[str]
    voice: str
    text_hash: str
    metadata: Dict[str, str]
    created_at: float
    last_access: float

    def touch(self) -> None:
        self.last_access = time.time()


class AudioCacheManager:
    """Simple JSON-backed cache for synthesized audio artifacts."""

    def __init__(self, path: Path = CACHE_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._entries: Dict[str, AudioCacheEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._persist()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Failed to load audio cache, starting fresh: %s", exc)
            data = {}
        for key, entry in data.items():
            self._entries[key] = AudioCacheEntry(
                key=key,
                artifact=entry.get("artifact", ""),
                sidecar=entry.get("sidecar"),
                voice=entry.get("voice", ""),
                text_hash=entry.get("text_hash", ""),
                metadata=entry.get("metadata", {}),
                created_at=entry.get("created_at", time.time()),
                last_access=entry.get("last_access", time.time()),
            )

    def _persist(self) -> None:
        serialisable = {k: asdict(v) for k, v in self._entries.items()}
        self.path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")

    @staticmethod
    def make_key(
        *,
        character_id: Optional[str],
        text_hash: str,
        voice: str,
        style: Optional[str] = None,
        lang: Optional[str] = None,
        model_hash: Optional[str] = None,
    ) -> str:
        voice_label = voice or "default"
        voice_style_parts = [voice_label, style or "default"]
        if lang:
            voice_style_parts.append(lang)
        voice_style = ":".join(voice_style_parts)

        parts = [
            character_id or "global",
            text_hash,
            voice_style,
            model_hash or "default",
        ]
        return "|".join(parts)

    def lookup(self, key: str) -> Optional[AudioCacheEntry]:
        with self._lock:
            entry = self._entries.get(key)
            if entry:
                entry.touch()
                self._persist()
            return entry

    def store(
        self,
        entry: AudioCacheEntry,
    ) -> AudioCacheEntry:
        with self._lock:
            entry.touch()
            self._entries[entry.key] = entry
            self._persist()
        LOGGER.debug("Audio cache stored key=%s artifact=%s", entry.key, entry.artifact)
        return entry


audio_cache = AudioCacheManager()
