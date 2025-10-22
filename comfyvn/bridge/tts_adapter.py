from __future__ import annotations

"""
Lightweight TTS cache adapter for stubbed audio synthesis workflows.

This module provides a deterministic cache keyed by (character, text,
style, model) combinations. The resulting directory contains a placeholder
WAV file alongside a JSON sidecar with provenance metadata so downstream
pipelines can resolve assets without invoking real synthesis.
"""

import copy
import hashlib
import json
import logging
import os
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

_CACHE_ROOT = Path("data/audio/tts")
_WAV_NAME = "out.wav"
_SIDECAR_NAME = "sidecar.json"

try:  # Optional import; the adapter is usable without the hook bus.
    from comfyvn.core import modder_hooks  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    modder_hooks = None  # type: ignore
_VOICE_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "stub-narrator-neutral",
        "name": "Narrator Neutral",
        "character": "Narrator",
        "lang": "en",
        "gender": "neutral",
        "styles": ["neutral", "calm"],
        "default_model": "xtts",
        "tags": ["stub", "default", "deterministic"],
        "description": "Baseline narrator voice used for offline previews and cache priming.",
        "sample_text": "Welcome back to the studio preview.",
    },
    {
        "id": "stub-protagonist-warm",
        "name": "Protagonist Warm",
        "character": "Lead",
        "lang": "en",
        "gender": "male",
        "styles": ["heroic", "warm"],
        "default_model": "xtts",
        "tags": ["stub", "hero", "v1"],
        "description": "Gentle leading voice with light heroic emphasis for dialogue prototypes.",
        "sample_text": "I'll handle the next scene—keep the cameras rolling.",
    },
    {
        "id": "stub-ally-energetic",
        "name": "Ally Energetic",
        "character": "Support",
        "lang": "en",
        "gender": "female",
        "styles": ["energetic", "friendly"],
        "default_model": "xtts",
        "tags": ["stub", "supporting"],
        "description": "Bright, energetic delivery for upbeat supporting characters.",
        "sample_text": "That was amazing! Let's try the alt take before lunch.",
    },
    {
        "id": "stub-antagonist-gravel",
        "name": "Antagonist Gravel",
        "character": "Adversary",
        "lang": "en",
        "gender": "male",
        "styles": ["low", "dramatic"],
        "default_model": "xtts",
        "tags": ["stub", "villain"],
        "description": "Gravelly antagonist voice tuned for dramatic monologues.",
        "sample_text": "Do you really think the mix will save your production?",
    },
]


def list_voices() -> List[Dict[str, Any]]:
    """
    Return the static catalog of stubbed voices exposed by the audio lab.

    Each entry includes lightweight metadata so UI callers can populate
    dropdowns without reaching for external services.
    """
    return [copy.deepcopy(voice) for voice in _VOICE_PRESETS]


def _match_voice_id(character: str, style: str) -> Optional[str]:
    character_lower = character.strip().lower()
    style_lower = style.strip().lower()

    fallback: Optional[str] = None
    for voice in _VOICE_PRESETS:
        voice_character = voice.get("character", "")
        if not isinstance(voice_character, str):
            continue
        if voice_character.strip().lower() == character_lower:
            fallback = voice.get("id") or fallback
            styles = voice.get("styles") or []
            for style_name in styles:
                if (
                    isinstance(style_name, str)
                    and style_name.strip().lower() == style_lower
                ):
                    return voice.get("id") or fallback
    return fallback


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    normalized_character = str(character or "narrator")
    normalized_text = str(text or "")
    normalized_style = str(style or "neutral")
    normalized_model = str(model or "xtts")

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
    cache_hit = wav_path.exists() and sidecar_path.exists()

    _ensure_placeholder_wav(wav_path)

    wav_size = None
    wav_checksum = None
    try:
        wav_bytes = wav_path.read_bytes()
        wav_size = len(wav_bytes)
        wav_checksum = hashlib.sha1(wav_bytes).hexdigest()
    except Exception:  # pragma: no cover - defensive
        LOGGER.debug("Failed to collect wav checksum for cache_key=%s", cache_key)

    timestamp = datetime.now(timezone.utc).isoformat()
    text_checksum = hashlib.sha1(normalized_text.encode("utf-8")).hexdigest()
    character_label = normalized_character.strip() or "narrator"
    style_label = normalized_style.strip() or "neutral"
    voice_id = _match_voice_id(character_label, style_label)

    generated_at = timestamp
    if cache_hit:
        try:
            existing = json.loads(sidecar_path.read_text(encoding="utf-8"))
            generated_at = (
                existing.get("generated_at")
                or existing.get("created_at")
                or existing.get("timestamp")
                or generated_at
            )
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug("Unable to reuse previous generated_at for %s", cache_key)

    metadata = {
        "sidecar_version": 1,
        "tool": "ComfyVN",
        "version": os.getenv("COMFYVN_VERSION", "0.8.0"),
        "cache_key": cache_key,
        "path": str(wav_path),
        "checksum_sha1": wav_checksum,
        "bytes": wav_size,
        "cached": cache_hit,
        "generated_at": generated_at,
        "updated_at": timestamp,
        "inputs": {
            "character": character_label,
            "text": normalized_text,
            "style": style_label,
            "model": normalized_model,
            "seed": seed,
        },
        "text_sha1": text_checksum,
        "text_length": len(normalized_text),
        "voice_id": voice_id,
        "provenance": {
            "voice_id": voice_id,
            "model": normalized_model,
            "style": style_label,
            "character": character_label,
            "text_sha1": text_checksum,
        },
    }
    _write_sidecar(sidecar_path, metadata)

    LOGGER.info(
        "TTS cache %s for %s model=%s style=%s seed=%s",
        "hit" if cache_hit else "write",
        character_label,
        normalized_model,
        style_label,
        seed,
    )

    hook_payload = {
        "cache_key": cache_key,
        "path": str(wav_path),
        "sidecar": str(sidecar_path),
        "character": character_label,
        "style": style_label,
        "model": normalized_model,
        "seed": seed,
        "voice_id": voice_id,
        "text_sha1": text_checksum,
        "cached": cache_hit,
        "bytes": wav_size,
        "checksum_sha1": wav_checksum,
        "text_length": len(normalized_text),
        "provenance": metadata["provenance"],
    }
    if modder_hooks:
        try:
            modder_hooks.emit("on_audio_tts_cached", hook_payload)
        except Exception:  # pragma: no cover - defensive
            LOGGER.warning("Failed to emit on_audio_tts_cached", exc_info=True)
        try:
            modder_hooks.emit("on_audio_tts_cached", hook_payload)
        except Exception:  # pragma: no cover - defensive
            LOGGER.warning("Failed to emit on_audio_tts_cached", exc_info=True)

    return {
        **hook_payload,
        "generated_at": generated_at,
        "updated_at": timestamp,
    }
