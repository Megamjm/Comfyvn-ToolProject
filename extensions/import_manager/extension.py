"""Menu registration for the Import Manager sample extension."""

from __future__ import annotations

from comfyvn.core.menu_runtime_bridge import MenuRegistry
from comfyvn.core.notifier import notifier


def register(registry: MenuRegistry) -> None:
    registry.add(
        label="Import Assets…",
        section="Tools",
        callback=_not_implemented,
    )


def _not_implemented(window) -> None:
    notifier.toast("warn", "Import Manager placeholder invoked — no implementation available.")
