from __future__ import annotations

"""
Performance toolkit for ComfyVN.

This package exposes the shared ``budget_manager`` and ``perf_profiler`` singletons
so both the FastAPI server and background workers can coordinate queue throttling,
resource budgeting, and profiler instrumentation without having to duplicate
plumbing or rely on global module state in unrelated packages.
"""

from .budgets import BudgetManager, budget_manager
from .profiler import PerfProfiler, perf_profiler

__all__ = [
    "BudgetManager",
    "PerfProfiler",
    "budget_manager",
    "perf_profiler",
]
