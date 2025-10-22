"""
Rigging helpers for 2.5D animation systems used by ComfyVN.

Exposes deterministic auto-rig generation and motion graph helpers that can
drive preview loops for layered puppet characters.
"""

from . import autorig, mograph

__all__ = ["autorig", "mograph"]
