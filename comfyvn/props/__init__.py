from __future__ import annotations

"""Prop management utilities for anchor placement and deterministic tweens."""

from .manager import (
    ALPHA_MODES,
    ANCHORS,
    DEFAULT_TWEEN,
    TWEEN_KINDS,
    Z_ORDER_VALUES,
    PropManager,
)

PROP_MANAGER = PropManager()

__all__ = [
    "ALPHA_MODES",
    "ANCHORS",
    "DEFAULT_TWEEN",
    "TWEEN_KINDS",
    "Z_ORDER_VALUES",
    "PropManager",
    "PROP_MANAGER",
]
