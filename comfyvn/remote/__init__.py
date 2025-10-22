"""
Remote orchestration helpers.

This package groups utilities that coordinate remote hosts, such as the
installer orchestrator used by the server API.  Modules inside deliberately
avoid importing heavyweight GUI dependencies so they can be reused by CLI
tools and FastAPI routes.
"""

from __future__ import annotations

__all__ = ["installer"]
