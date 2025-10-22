"""
Character emulation package.

Provides a singleton engine that can be used by FastAPI routes or other
runtime modules to emulate persona responses when the SillyCompatOffload
feature flag is enabled.
"""

from __future__ import annotations

from .engine import CharacterEmulationEngine, engine

__all__ = ["CharacterEmulationEngine", "engine"]
