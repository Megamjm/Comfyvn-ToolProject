"""Render Manager sample extension integration."""

from __future__ import annotations

from comfyvn.core.menu_runtime_bridge import MenuRegistry
from comfyvn.core.notifier import notifier


def register(registry: MenuRegistry) -> None:
    registry.add(
        label="Submit Dummy Render",
        section="Tools",
        callback=_submit_placeholder_render,
    )


def _submit_placeholder_render(window) -> None:
    notifier.toast("info", "Render Manager placeholder submitted a dummy render.")
