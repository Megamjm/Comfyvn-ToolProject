from __future__ import annotations

"""
Deterministic audio mixing helpers with lightweight ducking support.

This module intentionally keeps DSP minimal so the wider application can render
preview mixes without pulling in heavyweight audio dependencies.
"""

import audioop
import json
import math
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

__all__ = ["TrackSpec", "DuckingConfig", "mix_tracks"]


@dataclass
class TrackSpec:
    """
    Declarative description of an input track for mixing.

    ``path`` refers to a WAV file on disk. ``gain`` is a linear multiplier and
    ``offset`` is expressed in seconds.
    """

    path: Path
    role: str = "bgm"
    name: Optional[str] = None
    gain: float = 1.0
    gain_db: float = 0.0
    offset: float = 0.0

    def resolved_gain(self) -> float:
        gain = self.gain
        if self.gain_db:
            gain *= 10 ** (self.gain_db / 20.0)
        return gain


@dataclass
class DuckingConfig:
    """
    Simple envelope ducking parameters.

    ``amount_db`` determines how much the target tracks are reduced when the
    trigger tracks are active. ``threshold`` is a normalized amplitude gate.
    """

    trigger_roles: Sequence[str] = ("voice",)
    target_roles: Sequence[str] = ("bgm",)
    amount_db: float = 9.0
    threshold: float = 0.02
    attack_ms: float = 45.0
    release_ms: float = 160.0


def _read_wav(path: Path) -> tuple[int, array]:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        frames = audioop.lin2lin(frames, sample_width, 2)
    if channels > 1:
        frames = audioop.tomono(frames, 2, 0.5, 0.5)

    return sample_rate, array("h", frames)


def _resample_if_needed(
    samples: array,
    src_rate: int,
    dst_rate: int,
) -> array:
    if src_rate == dst_rate:
        return samples
    converted, _ = audioop.ratecv(samples.tobytes(), 2, 1, src_rate, dst_rate, None)
    return array("h", converted)


def _normalize_tracks(
    tracks: Iterable[TrackSpec],
    *,
    target_rate: Optional[int],
) -> tuple[int, List[dict]]:
    normalized: List[dict] = []
    resolved_rate: Optional[int] = target_rate

    for spec in tracks:
        if not spec.path.exists():
            raise FileNotFoundError(f"missing track: {spec.path}")
        sample_rate, samples = _read_wav(spec.path)
        if resolved_rate is None:
            resolved_rate = sample_rate
        samples = _resample_if_needed(samples, sample_rate, resolved_rate)
        gain = spec.resolved_gain()
        offset_samples = max(0, int(round(spec.offset * resolved_rate)))
        normalized.append(
            {
                "spec": spec,
                "samples": samples,
                "gain": gain,
                "offset_samples": offset_samples,
            }
        )

    if resolved_rate is None:
        resolved_rate = 22050

    return resolved_rate, normalized


def _compute_mix_length(tracks: Sequence[dict]) -> int:
    max_len = 0
    for track in tracks:
        samples: array = track["samples"]
        offset = track["offset_samples"]
        max_len = max(max_len, offset + len(samples))
    return max_len or 1


def _build_trigger_envelope(
    tracks: Sequence[dict],
    *,
    mix_length: int,
    config: DuckingConfig,
    sample_rate: int,
) -> List[float]:
    trigger_roles = set(config.trigger_roles)
    amplitude = [0.0] * mix_length
    for track in tracks:
        role = (track["spec"].role or "bgm").lower()
        if role not in trigger_roles:
            continue
        samples: array = track["samples"]
        offset = track["offset_samples"]
        gain = track["gain"]
        for idx, sample in enumerate(samples):
            pos = offset + idx
            if pos >= mix_length:
                break
            level = abs(sample / 32768.0) * gain
            if level > amplitude[pos]:
                amplitude[pos] = level

    reduce_gain = 10 ** (-abs(config.amount_db) / 20.0)
    threshold = max(0.0, float(config.threshold))
    attack_samples = max(1, int(sample_rate * (config.attack_ms / 1000.0)))
    release_samples = max(1, int(sample_rate * (config.release_ms / 1000.0)))

    envelope = [1.0] * mix_length
    current = 1.0
    for idx, level in enumerate(amplitude):
        target = reduce_gain if level >= threshold else 1.0
        if target < current:
            coeff = math.exp(-1.0 / attack_samples)
        else:
            coeff = math.exp(-1.0 / release_samples)
        current = target + (current - target) * coeff
        envelope[idx] = current

    return envelope


def _apply_tracks(
    tracks: Sequence[dict],
    *,
    mix_length: int,
    sample_rate: int,
    ducking: Optional[DuckingConfig],
) -> List[float]:
    buffer = [0.0] * mix_length
    duck_roles = set()
    envelope: Optional[List[float]] = None

    if ducking:
        duck_roles = {role.lower() for role in ducking.target_roles}
        envelope = _build_trigger_envelope(
            tracks,
            mix_length=mix_length,
            config=ducking,
            sample_rate=sample_rate,
        )

    for track in tracks:
        role = (track["spec"].role or "bgm").lower()
        samples: array = track["samples"]
        offset = track["offset_samples"]
        gain = track["gain"]

        for idx, sample in enumerate(samples):
            pos = offset + idx
            if pos >= mix_length:
                break
            value = (sample / 32768.0) * gain
            if envelope is not None and role in duck_roles:
                value *= envelope[pos]
            buffer[pos] += value

    return buffer


def _write_wav(path: Path, sample_rate: int, samples: Sequence[float]) -> None:
    clipped = array("h")
    for sample in samples:
        value = max(-1.0, min(1.0, sample))
        clipped.append(int(round(value * 32767)))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(clipped.tobytes())


def mix_tracks(
    tracks: Sequence[TrackSpec],
    *,
    output_path: Path,
    sidecar_path: Optional[Path] = None,
    ducking: Optional[DuckingConfig] = None,
    sample_rate: Optional[int] = None,
) -> Dict[str, object]:
    """
    Mix the provided tracks, applying ducking when configured, and write a WAV.

    Returns metadata describing the rendered mix along with the sidecar path
    when requested.
    """

    if not tracks:
        raise ValueError("at least one track required")

    mix_rate, normalized_tracks = _normalize_tracks(tracks, target_rate=sample_rate)
    mix_length = _compute_mix_length(normalized_tracks)
    buffer = _apply_tracks(
        normalized_tracks,
        mix_length=mix_length,
        sample_rate=mix_rate,
        ducking=ducking,
    )

    _write_wav(output_path, mix_rate, buffer)

    duration = mix_length / mix_rate
    metadata = {
        "path": str(output_path),
        "duration": duration,
        "sample_rate": mix_rate,
        "tracks": [
            {
                "path": str(track["spec"].path),
                "role": track["spec"].role,
                "gain": track["gain"],
                "offset": track["offset_samples"] / mix_rate,
            }
            for track in normalized_tracks
        ],
    }

    if ducking:
        metadata["ducking"] = {
            "trigger_roles": list(ducking.trigger_roles),
            "target_roles": list(ducking.target_roles),
            "amount_db": ducking.amount_db,
            "threshold": ducking.threshold,
            "attack_ms": ducking.attack_ms,
            "release_ms": ducking.release_ms,
        }

    if sidecar_path is not None:
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        metadata["sidecar"] = str(sidecar_path)

    return metadata
