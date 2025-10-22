from __future__ import annotations

"""
Asset ingest pipeline utilities.

The queue module exposes :func:`get_ingest_queue` which returns a process-wide
singleton that coordinates staging, deduplication, and registration of assets
submitted via the API layer or internal tooling.
"""

from .queue import AssetIngestQueue, get_ingest_queue

__all__ = ["AssetIngestQueue", "get_ingest_queue"]
