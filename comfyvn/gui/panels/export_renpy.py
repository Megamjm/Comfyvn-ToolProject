from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtWidgets import QWidget

from .json_endpoint_panel import JsonEndpointPanel, PanelAction


class RenPyExportPanel(JsonEndpointPanel):
    """Live Fix Stub — Ren'Py export controls wired to REST endpoints."""

    def __init__(self, base_url: str, *, parent: Optional[QWidget] = None) -> None:
        description = """
        Preview and execute Ren'Py exports using the backend API. Adjust project
        identifiers before triggering a full publish.
        """
        actions: Iterable[PanelAction] = [
            PanelAction(
                "Preview Export (Dry Run)",
                "GET",
                "/api/export/renpy/preview?project=demo_project&per_scene=true",
                "Run a diff-only preview to view missing assets and rating gates.",
            ),
            PanelAction(
                "Download Latest Preview Manifest",
                "GET",
                "/api/export/renpy/preview?project=demo_project&per_scene=false",
                "Preview without per-scene modules for quick diff checks.",
            ),
            PanelAction(
                "Publish Build (Steam & Itch)",
                "POST",
                "/api/export/publish",
                "Launch a full Ren'Py export and package builds for Steam & Itch.",
                payload={
                    "project": "demo_project",
                    "timeline": None,
                    "world": None,
                    "world_mode": "auto",
                    "per_scene": True,
                    "targets": ["steam", "itch"],
                    "platforms": ["windows", "linux"],
                },
            ),
            PanelAction(
                "Publish Build (Windows Only)",
                "POST",
                "/api/export/publish",
                "Export a Windows-only build with default packaging.",
                payload={
                    "project": "demo_project",
                    "per_scene": True,
                    "targets": ["itch"],
                    "platforms": ["windows"],
                },
            ),
        ]
        super().__init__(
            base_url,
            title="Ren'Py Exporter",
            description=description,
            actions=actions,
            parent=parent,
        )
