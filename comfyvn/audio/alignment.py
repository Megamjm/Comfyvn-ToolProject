from __future__ import annotations

"""
Utility helpers for emitting lightweight phoneme alignment metadata.

The implementation favours determinism over linguistic fidelity so tests and
preview tooling can rely on stable timestamps without heavyweight phonetic
libraries.  The generated alignment is a best-effort approximation intended for
stubbed audio pipelines.
"""

import json
import re
from dataclasses import dataclass
from hashlib import blake2s
from pathlib import Path
from typing import Iterator, List, Sequence

__all__ = [
    "AlignmentEntry",
    "align_text",
    "alignment_to_lipsync_payload",
    "write_alignment",
]

DEFAULT_BASE_DURATION = 0.065  # seconds per phoneme
DEFAULT_PAUSE_DURATION = 0.045
DEFAULT_CONSONANT_SCALE = 0.92
DEFAULT_VOWEL_SCALE = 1.18

_DIGRAPH_MAP = {
    "ch": "CH",
    "sh": "SH",
    "th": "TH",
    "ph": "F",
    "wh": "W",
    "qu": "KW",
    "ng": "NG",
    "ck": "K",
}

_LETTER_PHONEMES = {
    "a": "AA",
    "b": "B",
    "c": "K",
    "d": "D",
    "e": "EH",
    "f": "F",
    "g": "G",
    "h": "HH",
    "i": "IH",
    "j": "JH",
    "k": "K",
    "l": "L",
    "m": "M",
    "n": "N",
    "o": "AO",
    "p": "P",
    "q": "K",
    "r": "R",
    "s": "S",
    "t": "T",
    "u": "UH",
    "v": "V",
    "w": "W",
    "x": "KS",
    "y": "Y",
    "z": "Z",
}

_DIGIT_PHONEMES = {
    "0": "ZIH-RO",
    "1": "W AH N",
    "2": "T UW",
    "3": "TH R IY",
    "4": "F AO R",
    "5": "F AY V",
    "6": "S IH K S",
    "7": "S EH V AH N",
    "8": "EY T",
    "9": "N AY N",
}

_PAUSE_PATTERN = re.compile(r"[,\.\?!;:]+")


@dataclass(frozen=True)
class AlignmentEntry:
    phoneme: str
    t_start: float
    t_end: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "phoneme": self.phoneme,
            "t_start": round(self.t_start, 4),
            "t_end": round(self.t_end, 4),
        }


def _iter_phoneme_tokens(text: str) -> Iterator[str | None]:
    lowered = text.lower()
    index = 0
    length = len(lowered)

    while index < length:
        char = lowered[index]

        if char.isspace():
            yield None
            index += 1
            continue

        if _PAUSE_PATTERN.match(char):
            yield None
            index += 1
            continue

        digraph = None
        if index + 1 < length:
            pair = lowered[index : index + 2]
            digraph = _DIGRAPH_MAP.get(pair)
        if digraph:
            yield digraph
            index += 2
            continue

        phoneme = _LETTER_PHONEMES.get(char)
        if phoneme:
            yield phoneme
            index += 1
            continue

        if char.isdigit():
            spoken = _DIGIT_PHONEMES[char]
            for token in spoken.split():
                yield token
            index += 1
            continue

        if char in ("'", "-"):
            index += 1
            continue

        # Unknown symbol – treat as a brief silence marker
        yield None
        index += 1


def _duration_variation(seed: bytes, index: int) -> float:
    digest = blake2s(seed + index.to_bytes(4, "big"), digest_size=2).digest()
    value = int.from_bytes(digest, "big")
    return 0.88 + (value / 65535.0) * 0.34  # ~0.88 - 1.22


def _is_vowel_phoneme(phoneme: str) -> bool:
    return phoneme[:2] in {
        "AA",
        "AE",
        "AH",
        "AO",
        "AW",
        "AY",
        "EH",
        "ER",
        "EY",
        "IH",
        "IY",
        "OW",
        "OY",
        "UH",
        "UW",
    }


def align_text(
    text: str,
    *,
    base_duration: float = DEFAULT_BASE_DURATION,
    pause_duration: float = DEFAULT_PAUSE_DURATION,
) -> List[dict[str, float | str]]:
    """
    Produce a deterministic phoneme alignment for the provided utterance.

    Returns a list of dictionaries with ``t_start``, ``t_end``, and ``phoneme``
    keys, rounded to 4 decimal places to keep payloads compact.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    seed = cleaned.encode("utf-8")
    time_cursor = 0.0
    alignment: List[AlignmentEntry] = []

    for idx, token in enumerate(_iter_phoneme_tokens(cleaned)):
        if token is None:
            time_cursor += pause_duration
            continue

        scale = (
            DEFAULT_VOWEL_SCALE if _is_vowel_phoneme(token) else DEFAULT_CONSONANT_SCALE
        )
        variation = _duration_variation(seed, idx)
        duration = max(0.03, base_duration * scale * variation)

        start = time_cursor
        end = start + duration
        alignment.append(AlignmentEntry(phoneme=token, t_start=start, t_end=end))
        time_cursor = end

    return [entry.as_dict() for entry in alignment]


def alignment_to_lipsync_payload(
    alignment: Sequence[dict[str, float | str] | AlignmentEntry],
    *,
    fps: int = 60,
) -> dict[str, List[dict[str, float | str]]]:
    """
    Convert an alignment list into a coarse lipsync payload grouped by frame.

    The output contains ``frames`` entries where each item maps to the frame
    index and the phoneme active for that frame.  This is intentionally
    simplistic but sufficient for stubbed preview tooling.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")

    frames: List[dict[str, float | str]] = []
    for item in alignment:
        if isinstance(item, AlignmentEntry):
            data = item.as_dict()
        else:
            data = item
        start = float(data["t_start"])
        end = float(data["t_end"])
        phoneme = str(data["phoneme"])

        start_frame = int(start * fps)
        end_frame = max(start_frame, int(end * fps))
        for frame in range(start_frame, end_frame + 1):
            frames.append({"frame": frame, "phoneme": phoneme})

    return {"frames": frames, "fps": fps}


def write_alignment(
    alignment: Sequence[dict[str, float | str] | AlignmentEntry],
    path: Path,
) -> Path:
    """
    Persist alignment data as JSON and return the provided path.
    """
    payload: List[dict[str, float | str]] = []
    for item in alignment:
        if isinstance(item, AlignmentEntry):
            payload.append(item.as_dict())
        else:
            payload.append(
                {
                    "phoneme": str(item["phoneme"]),
                    "t_start": round(float(item["t_start"]), 4),
                    "t_end": round(float(item["t_end"]), 4),
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
