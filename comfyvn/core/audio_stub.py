from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import shutil
import time
import wave
from array import array
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from comfyvn.core.audio_cache import AudioCacheEntry, audio_cache
from comfyvn.core.comfyui_audio import (
    ComfyUIAudioRunner,
    ComfyUIWorkflowConfig,
    ComfyUIWorkflowError,
)
from comfyvn.core.settings_manager import SettingsManager

LOGGER = logging.getLogger("comfyvn.audio.pipeline")

DEFAULT_SAMPLE_RATE = 22050
MIN_DURATION_PER_CHAR = 0.055
MAX_DURATION_PER_CHAR = 0.11
PAUSE_DURATION = 0.035  # seconds between words for clarity
MAX_AMPLITUDE = 0.29  # scale relative to int16 max to avoid clipping


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _voice_profile(voice: str, style: Optional[str]) -> Dict[str, float]:
    """Derive pitch envelopes and pacing from the requested voice/style."""

    seed_input = f"{voice}|{style or 'default'}"
    rand = random.Random(seed_input)
    base_pitch = 150 + rand.randint(0, 160)  # Hz
    vibrato = 1.5 + rand.random() * 2.0
    tempo_variance = 0.9 + rand.random() * 0.3

    if style:
        lowered = style.lower()
        if "warm" in lowered:
            base_pitch -= 20
            vibrato *= 0.8
        elif "energetic" in lowered or "excited" in lowered:
            base_pitch += 25
            tempo_variance *= 0.85
        elif "serious" in lowered or "calm" in lowered:
            base_pitch -= 10
            tempo_variance *= 1.05

    return {
        "base_pitch": max(110, min(420, base_pitch)),
        "vibrato": vibrato,
        "tempo_variance": tempo_variance,
    }


def _sample_count(duration: float, sample_rate: int) -> int:
    return max(1, int(duration * sample_rate))


def _generate_samples(
    text: str,
    *,
    voice: str,
    lang: Optional[str],
    style: Optional[str],
    sample_rate: int,
    cache_seed: str,
) -> Tuple[array, float]:
    """Generate a synthetic waveform approximating speech cadences."""

    profile = _voice_profile(voice, style)
    rand = random.Random(cache_seed)
    samples = array("h")

    amplitude = int(MAX_AMPLITUDE * 32767)
    char_durations: Dict[str, float] = {}
    total_time = 0.0

    cleaned_text = text.replace("\r", " ")
    words = cleaned_text.split(" ")

    for word_index, word in enumerate(words):
        if not word:
            total_time += PAUSE_DURATION
            samples.extend([0] * _sample_count(PAUSE_DURATION, sample_rate))
            continue

        for char_index, char in enumerate(word):
            key = (lang or "default") + char.lower()
            duration = char_durations.get(key)
            if duration is None:
                duration = rand.uniform(MIN_DURATION_PER_CHAR, MAX_DURATION_PER_CHAR)
                duration *= profile["tempo_variance"]
                char_durations[key] = duration
            freq_variance = (rand.random() - 0.5) * 30
            char_code = ord(char)
            if char.isdigit():
                freq_variance += 15
            elif char in ",.;?!":
                duration *= 1.25
                freq_variance -= 25

            base_pitch = profile["base_pitch"] + ((char_code % 24) - 12) * 3
            freq = max(90.0, min(520.0, base_pitch + freq_variance))

            vibration = profile["vibrato"] + rand.random() * 0.8
            frame_count = _sample_count(duration, sample_rate)
            for frame in range(frame_count):
                t = frame / sample_rate
                env = math.sin(math.pi * frame / frame_count)  # simple attack/release envelope
                vibrato = math.sin(2 * math.pi * vibration * t) * 0.02
                sample_value = math.sin(2 * math.pi * (freq + freq * vibrato) * t)
                sample_value *= env
                samples.append(int(sample_value * amplitude))
            total_time += duration

        # word boundary pause (except last word)
        if word_index < len(words) - 1:
            pause = PAUSE_DURATION * (1.2 if word.endswith(",") else 1.0)
            samples.extend([0] * _sample_count(pause, sample_rate))
            total_time += pause

    if not samples:
        raise ValueError("text must contain audible characters")

    # Add gentle tail fade to avoid click
    tail_frames = min(len(samples), _sample_count(0.1, sample_rate))
    for i in range(1, tail_frames + 1):
        samples[-i] = int(samples[-i] * (i / tail_frames))

    duration_seconds = len(samples) / sample_rate
    return samples, duration_seconds


def _resolve_provider(section: str) -> Tuple[Optional[dict], dict]:
    settings = SettingsManager()
    cfg = settings.load()
    audio_cfg = cfg.get("audio", {})
    section_cfg = audio_cfg.get(section, {})
    providers = section_cfg.get("providers") or []
    active_id = section_cfg.get("active_provider")
    for provider in providers:
        if provider.get("id") == active_id:
            return provider, section_cfg
    return None, section_cfg


def _store_cache_entry(
    *,
    cache_key: str,
    artifact_path: Path,
    sidecar_path: Path,
    voice: str,
    text_hash: str,
    metadata: Dict[str, str],
    created_at: float,
) -> None:
    audio_cache.store(
        AudioCacheEntry(
            key=cache_key,
            artifact=str(artifact_path),
            sidecar=str(sidecar_path),
            voice=voice,
            text_hash=text_hash,
            metadata=metadata,
            created_at=created_at,
            last_access=created_at,
        )
    )


def _synth_via_comfyui(
    *,
    provider: dict,
    cache_key: str,
    text_hash: str,
    cleaned: str,
    voice: str,
    scene_id: Optional[str],
    character_id: Optional[str],
    lang: Optional[str],
    style: Optional[str],
    model_hash: Optional[str],
    artifact_path: Path,
    text_length: int,
) -> Tuple[Path, Path, Dict[str, Any]]:
    config = ComfyUIWorkflowConfig.from_dict(provider)
    runner = ComfyUIAudioRunner(config)

    context = {
        "text": cleaned,
        "voice": voice,
        "lang": lang or "default",
        "style": style or "default",
        "scene_id": scene_id or "",
        "character_id": character_id or "",
        "model_hash": model_hash or "",
        "text_hash": text_hash,
    }

    files, record = runner.run(context=context, output_types=("audio",))
    source = files[0]
    suffix = source.suffix or ".wav"
    if artifact_path.suffix.lower() != suffix.lower():
        artifact_path = artifact_path.with_suffix(suffix)

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, artifact_path)

    created_at = time.time()
    metadata = {
        "voice": voice,
        "lang": lang or "default",
        "style": style or "default",
        "scene_id": scene_id,
        "character_id": character_id,
        "model_hash": model_hash or provider.get("id") or "comfyui",
        "text_length": text_length,
        "text_hash": text_hash,
        "created_at": created_at,
        "provider": provider.get("id"),
        "source_file": str(source),
        "workflow": str(config.workflow_path),
        "comfyui": {
            "prompt_id": record.get("prompt_id"),
            "base_url": config.base_url,
        },
    }
    sidecar_path = artifact_path.with_suffix(".json")
    sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    cache_metadata = {
        "lang": metadata["lang"],
        "style": metadata["style"],
        "scene_id": scene_id or "",
        "character_id": character_id or "",
        "model_hash": metadata["model_hash"],
        "provider": provider.get("id", "comfyui"),
    }
    _store_cache_entry(
        cache_key=cache_key,
        artifact_path=artifact_path,
        sidecar_path=sidecar_path,
        voice=voice,
        text_hash=text_hash,
        metadata=cache_metadata,
        created_at=created_at,
    )

    LOGGER.info(
        "TTS comfyui voice='%s' provider=%s cached=False artifact=%s",
        voice,
        provider.get("id"),
        artifact_path.name,
    )
    return artifact_path, sidecar_path, metadata


def _synth_voice_fallback(
    *,
    cache_key: str,
    text_hash: str,
    cleaned: str,
    voice: str,
    scene_id: Optional[str],
    character_id: Optional[str],
    lang: Optional[str],
    style: Optional[str],
    model_hash: Optional[str],
    artifact_path: Path,
) -> Tuple[Path, Path, Dict[str, Any]]:
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

    sample_rate = DEFAULT_SAMPLE_RATE
    cache_seed = f"{cache_key}|{digest_input}"
    samples, duration_seconds = _generate_samples(
        cleaned,
        voice=voice,
        lang=lang,
        style=style,
        sample_rate=sample_rate,
        cache_seed=cache_seed,
    )

    with wave.open(str(artifact_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.tobytes())

    created_at = time.time()
    metadata = {
        "voice": voice,
        "lang": lang or "default",
        "style": style or "default",
        "scene_id": scene_id,
        "character_id": character_id,
        "model_hash": model_hash or "synthetic",
        "text_length": len(cleaned),
        "text_hash": text_hash,
        "created_at": created_at,
        "duration_seconds": duration_seconds,
        "sample_rate": sample_rate,
        "format": artifact_path.suffix.lstrip(".") or "wav",
        "provider": "synthetic",
    }
    sidecar_path = artifact_path.with_suffix(".json")
    sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    cache_metadata = {
        "lang": metadata["lang"],
        "style": metadata["style"],
        "scene_id": scene_id or "",
        "character_id": character_id or "",
        "model_hash": metadata["model_hash"],
        "duration_seconds": f"{metadata.get('duration_seconds', 0.0):.3f}",
        "provider": "synthetic",
    }
    _store_cache_entry(
        cache_key=cache_key,
        artifact_path=artifact_path,
        sidecar_path=sidecar_path,
        voice=voice,
        text_hash=text_hash,
        metadata=cache_metadata,
        created_at=created_at,
    )
    LOGGER.info(
        "TTS synth fallback voice='%s' style='%s' cached=False len=%s artifact=%s duration=%.2fs",
        voice,
        metadata["style"],
        metadata["text_length"],
        artifact_path.name,
        metadata.get("duration_seconds", 0.0),
    )
    return artifact_path, sidecar_path, metadata


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
    """Generate speech audio, preferring ComfyUI when available with cache dedupe."""

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text must not be empty")

    outdir = Path(os.getenv("COMFYVN_TTS_EXPORT_DIR", "exports/tts")).expanduser()
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
            LOGGER.info("TTS cache hit key=%s artifact=%s", cache_key, artifact.name)
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
    artifact_path = outdir / f"{voice}_{file_hash}.wav"

    provider, section_cfg = _resolve_provider("tts")
    if provider and str(provider.get("id", "")).startswith("comfyui"):
        try:
            artifact, sidecar, _meta = _synth_via_comfyui(
                provider=provider,
                cache_key=cache_key,
                text_hash=text_hash,
                cleaned=cleaned,
                voice=voice,
                scene_id=scene_id,
                character_id=character_id,
                lang=lang,
                style=style,
                model_hash=model_hash,
                artifact_path=artifact_path,
                text_length=len(cleaned),
            )
            return str(artifact), str(sidecar), False
        except ComfyUIWorkflowError as exc:
            LOGGER.warning("ComfyUI TTS unavailable, falling back: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Unexpected ComfyUI TTS failure: %s", exc)

    artifact, sidecar, _ = _synth_voice_fallback(
        cache_key=cache_key,
        text_hash=text_hash,
        cleaned=cleaned,
        voice=voice,
        scene_id=scene_id,
        character_id=character_id,
        lang=lang,
        style=style,
        model_hash=model_hash,
        artifact_path=artifact_path,
    )
    return str(artifact), str(sidecar), False
