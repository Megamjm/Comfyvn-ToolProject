"""SillyTavern Bridge sample extension stub."""

from __future__ import annotations

from comfyvn.core.menu_runtime_bridge import MenuRegistry
from comfyvn.core.notifier import notifier


def register(registry: MenuRegistry) -> None:
    registry.add(
        label="Open SillyTavern Bridge",
        section="View",
        callback=_open_bridge,
    )


def _open_bridge(window) -> None:
    notifier.toast("warn", "SillyTavern Bridge integration is not yet implemented.")
