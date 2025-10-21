"""
Core registries and shared data access for the ComfyVN Studio shell.

These classes provide a thin abstraction over the studio SQLite database.
They are intentionally lightweight so that both the GUI and the HTTP APIs
can share a common source of truth for project data.
"""

from .asset_registry import AssetRegistry
from .base_registry import BaseRegistry
from .character_registry import CharacterRegistry
from .import_registry import ImportRegistry
from .job_registry import JobRegistry
from .provenance_registry import ProvenanceRegistry
from .scene_registry import SceneRegistry
from .template_registry import TemplateRegistry
from .timeline_registry import TimelineRegistry
from .variable_registry import VariableRegistry
from .world_registry import WorldRegistry

__all__ = [
    "BaseRegistry",
    "AssetRegistry",
    "SceneRegistry",
    "CharacterRegistry",
    "WorldRegistry",
    "TemplateRegistry",
    "VariableRegistry",
    "JobRegistry",
    "ImportRegistry",
    "ProvenanceRegistry",
    "TimelineRegistry",
]
