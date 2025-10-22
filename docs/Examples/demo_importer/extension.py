"""GUI integration for the Demo Importer extension."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from comfyvn.core.menu_runtime_bridge import MenuRegistry
from comfyvn.core.notifier import notifier
from comfyvn.extensions.demo_importer.entry import open_dialog


def register(registry: MenuRegistry) -> None:
    registry.add(
        label="Demo Importer",
        section="File",
        callback=_trigger_importer,
    )


def _trigger_importer(window) -> None:
    result = QFileDialog.getOpenFileName(
        window,
        "Demo Importer",
        str(Path.home()),
        "Transcript files (*.txt *.json);;All files (*.*)",
    )
    path = result[0]
    if not path:
        return
    open_dialog()
    notifier.toast("info", f"Demo importer invoked for {Path(path).name}")
