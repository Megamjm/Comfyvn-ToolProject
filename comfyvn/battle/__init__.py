"""
Battle engine helpers exposed for REST routes, GUI panels, and automation tooling.
"""

from .engine import BattleSimulationResult, resolve, simulate

__all__ = ["BattleSimulationResult", "resolve", "simulate"]
