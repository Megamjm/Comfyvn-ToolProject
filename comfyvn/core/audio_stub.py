from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

LOGGER = logging.getLogger("comfyvn.audio.pipeline")


def synth_voice(
    text: str,
    voice: str = "neutral",
    *,
    scene_id: Optional[str] = None,
    character_id: Optional[str] = None,
    lang: Optional[str] = None,
) -> Tuple[str, Optional[str], bool]:
    """Stub TTS synthesizer.

    Returns a tuple of (artifact_path, sidecar_path, cached_flag). The stub writes a
    small text artifact alongside a JSON sidecar to mimic metadata output. Downstream
    callers can replace this implementation with a real TTS backend without changing
    the contract.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text must not be empty")

    outdir = Path("exports/tts")
    outdir.mkdir(parents=True, exist_ok=True)

    digest_input = "|".join(
        filter(
            None,
            [
                voice,
                cleaned,
                lang or "",
                scene_id or "",
                character_id or "",
            ],
        )
    )
    file_hash = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:12]
    name = f"{voice}_{file_hash}.txt"
    artifact_path = outdir / name
    cached = artifact_path.exists()

    if not cached:
        artifact_path.write_text(
            f"VOICE={voice}\nLANG={lang or 'default'}\nTEXT={cleaned}",
            encoding="utf-8",
        )

    metadata = {
        "voice": voice,
        "lang": lang or "default",
        "scene_id": scene_id,
        "character_id": character_id,
        "text_length": len(cleaned),
        "cached": cached,
    }
    sidecar_path = artifact_path.with_suffix(".json")
    sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    LOGGER.info(
        "TTS synth %s voice='%s' cached=%s len=%s",
        artifact_path.name,
        voice,
        cached,
        metadata["text_length"],
    )

    return str(artifact_path), str(sidecar_path), cached
