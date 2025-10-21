"""
Translation utilities for ComfyVN.

Exposes a shared :class:`TranslationManager` instance and a lightweight
``t`` helper that routes lookups through the manager using the active
language with automatic fallback.
"""

from __future__ import annotations

from .manager import TranslationManager, get_manager, t

__all__ = ["TranslationManager", "get_manager", "t"]
