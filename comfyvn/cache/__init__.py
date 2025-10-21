"""
Cache utilities for ComfyVN.

This package currently exposes the hash-based deduplication cache manager used
to track unique asset blobs shared across on-disk paths.
"""

from __future__ import annotations

from .cache_manager import CacheManager

__all__ = ["CacheManager"]
