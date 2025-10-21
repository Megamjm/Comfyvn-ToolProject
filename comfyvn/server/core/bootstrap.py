from __future__ import annotations

"""Backwards-compatible import shim for the FastAPI application factory."""

from comfyvn.server.app import create_app

__all__ = ["create_app"]
