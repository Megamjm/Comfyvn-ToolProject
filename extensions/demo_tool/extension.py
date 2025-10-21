"""GUI menu registration for the Demo Tool extension."""

from __future__ import annotations

from comfyvn.core.menu_runtime_bridge import MenuRegistry
from comfyvn.extensions.demo_tool.entry import run_tool


def register(registry: MenuRegistry) -> None:
    registry.add(
        label="Demo Tool Action",
        section="Tools",
        callback=_launch_demo_tool,
    )


def _launch_demo_tool(window) -> None:
    run_tool()
