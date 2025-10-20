from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

from comfyvn.core.audio_cache import AudioCacheEntry, audio_cache

LOGGER = logging.getLogger("comfyvn.audio.pipeline")


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def synth_voice(
    text: str,
    voice: str = "neutral",
    *,
    scene_id: Optional[str] = None,
    character_id: Optional[str] = None,
    lang: Optional[str] = None,
    style: Optional[str] = None,
    model_hash: Optional[str] = None,
) -> Tuple[str, Optional[str], bool]:
    """Stub TTS synthesizer with cache + sidecar support."""

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text must not be empty")

    outdir = Path("exports/tts")
    outdir.mkdir(parents=True, exist_ok=True)

    text_hash = _hash_text(cleaned)
    cache_key = audio_cache.make_key(
        voice=voice,
        text_hash=text_hash,
        lang=lang,
        character_id=character_id,
        style=style,
        model_hash=model_hash,
    )

    cached_entry = audio_cache.lookup(cache_key)
    if cached_entry:
        artifact = Path(cached_entry.artifact)
        sidecar = Path(cached_entry.sidecar) if cached_entry.sidecar else None
        if artifact.exists():
            LOGGER.info(
                "TTS cache hit key=%s artifact=%s",
                cache_key,
                artifact.name,
            )
            return str(artifact), str(sidecar) if sidecar else None, True

    digest_input = "|".join(
        filter(
            None,
            [
                voice,
                cleaned,
                lang or "",
                scene_id or "",
                character_id or "",
                style or "",
                model_hash or "",
            ],
        )
    )
    file_hash = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:12]
    artifact_path = outdir / f"{voice}_{file_hash}.txt"

    artifact_path.write_text(
        "\n".join(
            [
                f"VOICE={voice}",
                f"LANG={lang or 'default'}",
                f"STYLE={style or 'default'}",
                f"MODEL_HASH={model_hash or 'stub'}",
                f"TEXT={cleaned}",
            ]
        ),
        encoding="utf-8",
    )

    created_at = time.time()
    metadata = {
        "voice": voice,
        "lang": lang or "default",
        "style": style or "default",
        "scene_id": scene_id,
        "character_id": character_id,
        "model_hash": model_hash,
        "text_length": len(cleaned),
        "text_hash": text_hash,
        "created_at": created_at,
    }
    sidecar_path = artifact_path.with_suffix(".json")
    sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    audio_cache.store(
        AudioCacheEntry(
            key=cache_key,
            artifact=str(artifact_path),
            sidecar=str(sidecar_path),
            voice=voice,
            text_hash=text_hash,
            metadata={
                "lang": metadata["lang"],
                "style": metadata["style"],
                "scene_id": scene_id or "",
                "character_id": character_id or "",
                "model_hash": model_hash or "",
            },
            created_at=created_at,
            last_access=created_at,
        )
    )

    LOGGER.info(
        "TTS synth voice='%s' style='%s' cached=False len=%s artifact=%s",
        voice,
        metadata["style"],
        metadata["text_length"],
        artifact_path.name,
    )

    return str(artifact_path), str(sidecar_path), False
