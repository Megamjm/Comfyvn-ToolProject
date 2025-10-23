"""
Lightweight orchestration stubs used by legacy roleplay/render APIs.

The original implementation lived outside this repo.  These shims keep the
endpoints importable and return informative 501 responses when invoked.
"""

from __future__ import annotations

from .pipeline_manager import PipelineContext, PipelineManager

__all__ = ["PipelineContext", "PipelineManager"]
