"""
Theme planning utilities for scene and world previews.

Provides template lookup helpers plus ``plan`` which composes a deterministic
presentation delta for the requested theme and scene context.
"""

from .templates import TEMPLATES, available_templates, plan  # noqa: F401

__all__ = ["TEMPLATES", "available_templates", "plan"]
