"""
Backward-compatible shim for the POV manager module.

External scripts may still import :mod:`comfyvn.pov.perspective`; re-export the
renamed manager objects to keep that contract intact.
"""

from __future__ import annotations

from .manager import POV, POVManager, POVState

__all__ = ["POV", "POVManager", "POVState"]
