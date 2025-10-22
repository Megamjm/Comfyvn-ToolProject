"""
Dungeon runtime façade exposing grid and DOOM-lite backends.

The module exports a shared :class:`DungeonAPI` instance that the FastAPI
routes can reuse so in-memory session state stays consistent for the process.
"""

from __future__ import annotations

from .api import API, DungeonAPI

__all__ = ["DungeonAPI", "API"]
