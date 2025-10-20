"""
Core registries and shared data access for the ComfyVN Studio shell.

These classes provide a thin abstraction over the studio SQLite database.
They are intentionally lightweight so that both the GUI and the HTTP APIs
can share a common source of truth for project data.
"""

from .base_registry import BaseRegistry
from .asset_registry import AssetRegistry
from .scene_registry import SceneRegistry
from .character_registry import CharacterRegistry
from .world_registry import WorldRegistry

__all__ = [
    "BaseRegistry",
    "AssetRegistry",
    "SceneRegistry",
    "CharacterRegistry",
    "WorldRegistry",
]
