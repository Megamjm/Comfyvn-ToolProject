from __future__ import annotations

"""
Lightweight TTS cache adapter for stubbed audio synthesis workflows.

This module provides a deterministic cache keyed by (character, text,
style, model) combinations. The resulting directory contains a placeholder
WAV file alongside a JSON sidecar with provenance metadata so downstream
pipelines can resolve assets without invoking real synthesis.
"""

import hashlib
import json
import logging
import os
import wave
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

_CACHE_ROOT = Path("data/audio/tts")
_WAV_NAME = "out.wav"
_SIDECAR_NAME = "sidecar.json"


def _cache_key(character: str, text: str, style: str, model: str) -> str:
    payload = f"{character}|{text}|{style}|{model}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _ensure_placeholder_wav(target: Path) -> None:
    """
    Create a short silent WAV file if none exists yet at the target path.

    We use the standard library ``wave`` module to emit a valid PCM file so
    audio tooling can ingest it without additional safeguards.
    """
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with wave.open(str(target), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 2205)  # ~0.1s of silence
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to create placeholder WAV: %s", exc)
        target.write_bytes(b"RIFF....WAVE")


def _write_sidecar(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2))


def synthesize(
    character: str,
    text: str,
    style: str,
    model: str,
    *,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate (or reuse) a cached TTS artifact for orchestrating audio previews.

    Returns a mapping containing the cached path, sidecar metadata path, and the
    cache key used to identify the entry.
    """
    normalized_character = character or "narrator"
    normalized_text = text or ""
    normalized_style = style or "neutral"
    normalized_model = model or "xtts"

    cache_key = _cache_key(
        normalized_character,
        normalized_text,
        normalized_style,
        normalized_model,
    )
    root = _CACHE_ROOT / cache_key
    root.mkdir(parents=True, exist_ok=True)

    wav_path = root / _WAV_NAME
    sidecar_path = root / _SIDECAR_NAME

    _ensure_placeholder_wav(wav_path)

    metadata = {
        "tool": "ComfyVN",
        "version": os.getenv("COMFYVN_VERSION", "0.8.0"),
        "cache_key": cache_key,
        "character": normalized_character,
        "style": normalized_style,
        "model": normalized_model,
        "text_chars": len(normalized_text),
        "seed": seed,
        "path": str(wav_path),
    }
    _write_sidecar(sidecar_path, metadata)

    LOGGER.info(
        "TTS cache hit for %s model=%s style=%s seed=%s",
        normalized_character,
        normalized_model,
        normalized_style,
        seed,
    )

    return {
        "path": str(wav_path),
        "sidecar": str(sidecar_path),
        "cache_key": cache_key,
    }
