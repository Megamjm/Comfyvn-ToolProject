"""
Animation utilities for ComfyVN.

The 2.5D rig feature lives under ``comfyvn.anim.rig`` and is intentionally
kept isolated so other subsystems can import the rigging helpers without
pulling FastAPI server dependencies.
"""

__all__ = ["rig"]
