"""
Collaboration primitives for ComfyVN.

The CRDT document model and room management logic live here so both the
FastAPI backend and GUI clients can share consistent data contracts.
"""

from __future__ import annotations

from .crdt import CRDTDocument, CRDTOperation, OperationResult
from .room import CollabClientState, CollabHub, CollabPresence, CollabRoom

__all__ = [
    "CRDTDocument",
    "CRDTOperation",
    "OperationResult",
    "CollabClientState",
    "CollabPresence",
    "CollabRoom",
    "CollabHub",
]
