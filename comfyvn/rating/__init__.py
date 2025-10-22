from __future__ import annotations

"""
Lightweight rating services exposed across the application.

The default implementation uses a heuristic classifier stub backed by a
JSON override store so reviewers can pin ratings and supply rationale.
"""

from pathlib import Path
from typing import Optional

from comfyvn.rating.classifier_stub import RatingService, RatingStore

_store: Optional[RatingStore] = None
_service: Optional[RatingService] = None


def rating_store() -> RatingStore:
    global _store
    if _store is None:
        _store = RatingStore()
    return _store


def rating_service() -> RatingService:
    global _service
    if _service is None:
        _service = RatingService(store=rating_store())
    return _service


__all__ = ["rating_store", "rating_service", "RatingService", "RatingStore"]
