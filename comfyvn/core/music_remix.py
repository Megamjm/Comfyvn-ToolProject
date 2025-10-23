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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from comfyvn.config.runtime_paths import music_cache_file
from comfyvn.core.comfyui_audio import (
    ComfyUIAudioRunner,
    ComfyUIWorkflowConfig,
    ComfyUIWorkflowError,
)
from comfyvn.core.settings_manager import SettingsManager

LOGGER = logging.getLogger("comfyvn.audio.music")

DEFAULT_SAMPLE_RATE = 32000
DEFAULT_DURATION = 24.0  # seconds
CACHE_PATH = music_cache_file()


@dataclass
class MusicCacheEntry:
    key: str
    artifact: str
    sidecar: str
    metadata: Dict[str, object]
    created_at: float
    last_access: float

    def touch(self) -> None:
        self.last_access = time.time()


class MusicCacheManager:
    def __init__(self, path: Path = CACHE_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: Dict[str, MusicCacheEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._persist()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Failed to load music cache, starting fresh: %s", exc)
            data = {}
        for key, entry in data.items():
            self._entries[key] = MusicCacheEntry(
                key=key,
                artifact=entry.get("artifact", ""),
                sidecar=entry.get("sidecar", ""),
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
        scene_id: str,
        target_style: str,
        source_track: Optional[str],
        seed: Optional[int],
        mood_tags: Optional[List[str]],
    ) -> str:
        digest_src = "|".join(
            [
                scene_id,
                target_style,
                source_track or "",
                ",".join(sorted(mood_tags or [])),
                str(seed or 0),
            ]
        )
        return hashlib.sha1(digest_src.encode("utf-8")).hexdigest()

    def lookup(self, key: str) -> Optional[MusicCacheEntry]:
        entry = self._entries.get(key)
        if not entry:
            return None
        artifact = Path(entry.artifact)
        sidecar = Path(entry.sidecar)
        if not artifact.exists() or not sidecar.exists():
            LOGGER.debug("Music cache entry missing files key=%s", key)
            return None
        entry.touch()
        self._persist()
        LOGGER.info("Music cache hit key=%s artifact=%s", key, artifact.name)
        return entry

    def store(self, entry: MusicCacheEntry) -> MusicCacheEntry:
        entry.touch()
        self._entries[entry.key] = entry
        self._persist()
        LOGGER.debug("Music cache stored key=%s", entry.key)
        return entry


music_cache = MusicCacheManager()


def _style_profile(
    style: str, mood_tags: Optional[List[str]], rand: random.Random
) -> Dict[str, float]:
    lowered = style.lower()
    tempo = 96.0
    root_freq = 180.0
    harmony_spread = 0.18

    if "lofi" in lowered or "chill" in lowered:
        tempo = 76.0
        root_freq = 160.0
    elif "battle" in lowered or "action" in lowered:
        tempo = 128.0
        root_freq = 220.0
        harmony_spread = 0.32
    elif "romance" in lowered or "emotion" in lowered:
        tempo = 90.0
        root_freq = 196.0
        harmony_spread = 0.22
    elif "tension" in lowered or "mystery" in lowered:
        tempo = 84.0
        root_freq = 210.0
        harmony_spread = 0.26

    if mood_tags:
        lowered_tags = {tag.lower() for tag in mood_tags}
        if {"sad", "melancholy", "blue"} & lowered_tags:
            tempo *= 0.85
            root_freq -= 12.0
        if {"happy", "uplifting", "bright"} & lowered_tags:
            tempo *= 1.1
            root_freq += 8.0
        if {"dramatic", "intense"} & lowered_tags:
            harmony_spread *= 1.25

    return {
        "tempo": tempo,
        "root_freq": root_freq,
        "harmony_spread": harmony_spread,
        "layer_count": rand.randint(3, 5),
    }


def _generate_music_samples(
    *,
    duration: float,
    sample_rate: int,
    style_profile: Dict[str, float],
    seed: int,
) -> Tuple[array, Dict[str, object]]:
    rand = random.Random(seed)
    total_frames = int(duration * sample_rate)
    samples = array("h")
    max_amplitude = 0.32 * 32767

    tempo = style_profile["tempo"]
    beat_period = 60.0 / max(tempo, 1.0)
    layer_count = int(style_profile["layer_count"])
    layers: List[Dict[str, float]] = []

    for idx in range(layer_count):
        freq_multiplier = 1 + rand.uniform(
            -style_profile["harmony_spread"], style_profile["harmony_spread"]
        )
        layer = {
            "freq": style_profile["root_freq"] * freq_multiplier * (1 + idx * 0.05),
            "phase": rand.random() * 2 * math.pi,
            "swing": rand.uniform(0.1, 0.25),
            "lfo_freq": rand.uniform(0.2, 0.5),
            "lfo_depth": rand.uniform(0.02, 0.08),
            "volume": 0.6 + rand.random() * 0.4,
        }
        layers.append(layer)

    for frame in range(total_frames):
        t = frame / sample_rate
        beat_position = (t % beat_period) / beat_period
        beat_env = math.sin(math.pi * beat_position)
        envelope = min(1.0, beat_env + 0.25)
        value = 0.0
        for layer in layers:
            lfo = math.sin(2 * math.pi * layer["lfo_freq"] * t) * layer["lfo_depth"]
            swing = math.sin(2 * math.pi * (layer["freq"] / 4) * t) * layer["swing"]
            sample_value = math.sin(
                2 * math.pi * (layer["freq"] + layer["freq"] * (lfo + swing)) * t
                + layer["phase"]
            )
            value += sample_value * layer["volume"]

        value /= max(layer_count, 1)
        value *= envelope
        samples.append(int(max(-32767, min(32767, value * max_amplitude))))

    fade_frames = int(sample_rate * 0.25)
    for i in range(min(fade_frames, len(samples))):
        fade_in = (i / fade_frames) if fade_frames else 1.0
        fade_out = ((len(samples) - i) / fade_frames) if fade_frames else 1.0
        fade = min(1.0, fade_in, fade_out)
        samples[i] = int(samples[i] * fade)
        samples[-i - 1] = int(samples[-i - 1] * fade)

    metadata = {
        "tempo": tempo,
        "duration_seconds": duration,
        "sample_rate": sample_rate,
        "layers": [
            {
                "freq": round(layer["freq"], 3),
                "volume": round(layer["volume"], 3),
                "lfo_freq": round(layer["lfo_freq"], 3),
                "lfo_depth": round(layer["lfo_depth"], 3),
            }
            for layer in layers
        ],
    }
    return samples, metadata


def _resolve_provider() -> Tuple[Optional[dict], dict]:
    settings = SettingsManager()
    cfg = settings.load()
    audio = cfg.get("audio", {})
    section = audio.get("music", {})
    providers = section.get("providers") or []
    active_id = section.get("active_provider")
    for provider in providers:
        if provider.get("id") == active_id:
            return provider, section
    return None, section


def _run_comfyui_music(
    *,
    provider: dict,
    cache_key: str,
    artifact: Path,
    payload: Dict[str, Any],
) -> Tuple[Path, Path, Dict[str, Any]]:
    config = ComfyUIWorkflowConfig.from_dict(provider)
    runner = ComfyUIAudioRunner(config)

    context = {
        "scene_id": payload["scene_id"],
        "target_style": payload["target_style"],
        "source_track": payload.get("source_track") or "",
        "mood_tags": payload.get("mood_tags") or [],
        "seed": payload.get("seed"),
    }
    files, record = runner.run(context=context, output_types=("audio", "music"))
    source = files[0]
    suffix = source.suffix or ".wav"
    if artifact.suffix.lower() != suffix.lower():
        artifact = artifact.with_suffix(suffix)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, artifact)

    duration_seconds: Optional[float] = payload.get("duration_seconds")
    sample_rate: Optional[int] = payload.get("sample_rate")
    if artifact.suffix.lower() == ".wav":
        try:
            with wave.open(str(artifact), "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                frames = wav_file.getnframes()
                if sample_rate:
                    duration_seconds = frames / float(sample_rate)
        except wave.Error as exc:
            LOGGER.debug(
                "ComfyUI music unable to read WAV metadata %s: %s", artifact, exc
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug(
                "ComfyUI music unexpected metadata read failure %s: %s", artifact, exc
            )

    created_at = time.time()
    payload.update(
        {
            "provider": provider.get("id"),
            "created_at": created_at,
            "cache_key": cache_key,
            "source_file": str(source),
            "workflow": str(config.workflow_path),
            "comfyui": {
                "prompt_id": record.get("prompt_id"),
                "base_url": config.base_url,
            },
        }
    )
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds
    if sample_rate is not None:
        payload["sample_rate"] = sample_rate
    sidecar = artifact.with_suffix(".json")
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    music_cache.store(
        MusicCacheEntry(
            key=cache_key,
            artifact=str(artifact),
            sidecar=str(sidecar),
            metadata=payload,
            created_at=created_at,
            last_access=created_at,
        )
    )
    LOGGER.info(
        "Music comfyui scene=%s style=%s provider=%s artifact=%s",
        payload["scene_id"],
        payload["target_style"],
        provider.get("id"),
        artifact.name,
    )
    return artifact, sidecar, payload


def remix_track(
    *,
    scene_id: str,
    target_style: str,
    source_track: Optional[str] = None,
    seed: Optional[int] = None,
    mood_tags: Optional[list[str]] = None,
) -> Tuple[str, str, bool, Dict[str, Any]]:
    """Generate a deterministic synthetic remix with metadata+cache.

    Returns a tuple of (artifact_path, sidecar_path, cached, metadata).
    """

    target = target_style.strip() or "default"
    scene = scene_id.strip() or "scene-unknown"
    mood_tags = list(sorted(filter(None, mood_tags or [])))

    cache_key = music_cache.make_key(
        scene_id=scene,
        target_style=target,
        source_track=source_track,
        seed=seed,
        mood_tags=mood_tags,
    )

    cached = music_cache.lookup(cache_key)
    if cached:
        cached_meta = dict(cached.metadata or {})
        return cached.artifact, cached.sidecar, True, cached_meta

    outdir = Path(os.getenv("COMFYVN_MUSIC_EXPORT_DIR", "exports/music"))
    outdir.mkdir(parents=True, exist_ok=True)

    digest = cache_key[:12]
    artifact = outdir / f"{scene}_{target}_{digest}.wav"

    derived_seed = seed if seed is not None else int(cache_key[:8], 16)
    style_profile = _style_profile(target, mood_tags, random.Random(derived_seed))
    duration = DEFAULT_DURATION + len(mood_tags) * 1.5

    samples, music_meta = _generate_music_samples(
        duration=duration,
        sample_rate=DEFAULT_SAMPLE_RATE,
        style_profile=style_profile,
        seed=derived_seed,
    )

    provider, section_cfg = _resolve_provider()
    payload = {
        "scene_id": scene,
        "target_style": target,
        "source_track": source_track,
        "mood_tags": mood_tags,
        "seed": derived_seed,
        **music_meta,
    }

    if provider and str(provider.get("id", "")).startswith("comfyui"):
        try:
            artifact_path, sidecar_path, meta_payload = _run_comfyui_music(
                provider=provider,
                cache_key=cache_key,
                artifact=artifact,
                payload=payload,
            )
            return str(artifact_path), str(sidecar_path), False, dict(meta_payload)
        except ComfyUIWorkflowError as exc:
            LOGGER.warning("ComfyUI music unavailable, falling back: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Unexpected ComfyUI music failure: %s", exc)

    with wave.open(str(artifact), "wb") as wav_file:
        wav_file.setnchannels(2 if len(music_meta["layers"]) > 3 else 1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(DEFAULT_SAMPLE_RATE)

        if wav_file.getnchannels() == 1:
            wav_file.writeframes(samples.tobytes())
        else:
            # rudimentary stereo: alternate samples between L/R with slight phase offset
            stereo = array("h")
            phase_offset = int(DEFAULT_SAMPLE_RATE * 0.002)
            for idx, value in enumerate(samples):
                paired_idx = (idx + phase_offset) % len(samples)
                stereo.append(value)
                stereo.append(samples[paired_idx])
            wav_file.writeframes(stereo.tobytes())

    created_at = time.time()
    payload.update(
        {"created_at": created_at, "cache_key": cache_key, "provider": "synthetic"}
    )
    sidecar = artifact.with_suffix(".json")
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    music_cache.store(
        MusicCacheEntry(
            key=cache_key,
            artifact=str(artifact),
            sidecar=str(sidecar),
            metadata=payload,
            created_at=created_at,
            last_access=created_at,
        )
    )

    LOGGER.info(
        "Music remix fallback scene=%s style=%s tempo=%.1f duration=%.1fs artifact=%s",
        scene,
        target,
        payload["tempo"],
        payload["duration_seconds"],
        artifact.name,
    )
    return str(artifact), str(sidecar), False, dict(payload)
