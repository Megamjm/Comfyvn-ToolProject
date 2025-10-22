from __future__ import annotations

"""
Weather planning utilities.

Expose a shared ``WEATHER_PLANNER`` instance so both API routes and exporters
can access the most recent compiled plan without needing to manage locking or
state merging themselves.
"""

from .engine import WeatherPlanStore, compile_plan

WEATHER_PLANNER = WeatherPlanStore()

__all__ = ["compile_plan", "WEATHER_PLANNER", "WeatherPlanStore"]
