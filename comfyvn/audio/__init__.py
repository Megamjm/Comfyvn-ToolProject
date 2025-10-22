from __future__ import annotations

"""
Audio utilities supporting alignment metadata and lightweight mixing helpers.

The modules in this package intentionally ship deterministic behaviours so the
rest of the system can exercise audio workflows without requiring heavyweight
DSP dependencies.
"""

from .alignment import (  # noqa: F401
    align_text,
    alignment_to_lipsync_payload,
    write_alignment,
)
from .mixer import mix_tracks  # noqa: F401

__all__ = [
    "align_text",
    "alignment_to_lipsync_payload",
    "write_alignment",
    "mix_tracks",
]
