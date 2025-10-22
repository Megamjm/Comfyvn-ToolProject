from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtWidgets import QWidget

from .json_endpoint_panel import JsonEndpointPanel, PanelAction


class ToolsInstallerPanel(JsonEndpointPanel):
    """Live Fix Stub — Remote installer orchestration."""

    def __init__(self, base_url: str, *, parent: Optional[QWidget] = None) -> None:
        description = """
        Discover remote installer modules, run dry-run plans, and inspect status logs.
        Toggle `dry_run` to capture execution plans before applying them to hosts.
        """
        actions: Iterable[PanelAction] = [
            PanelAction(
                "List Installer Modules",
                "GET",
                "/api/remote/modules",
                "Retrieve the registry of available installer modules.",
            ),
            PanelAction(
                "Plan Install (Dry Run)",
                "POST",
                "/api/remote/install",
                "Record an installation plan without applying changes.",
                payload={
                    "host": "127.0.0.1",
                    "modules": ["base_tools"],
                    "dry_run": True,
                },
            ),
            PanelAction(
                "Apply Install Plan",
                "POST",
                "/api/remote/install",
                "Apply installer modules to the target host.",
                payload={
                    "host": "127.0.0.1",
                    "modules": ["base_tools"],
                    "dry_run": False,
                },
            ),
            PanelAction(
                "Read Host Status",
                "GET",
                "/api/remote/status?host=127.0.0.1",
                "Inspect the latest execution status and logs for a host.",
            ),
            PanelAction(
                "List All Status Entries",
                "GET",
                "/api/remote/status",
                "Enumerate hosts with recorded installer runs.",
            ),
        ]
        super().__init__(
            base_url,
            title="External Tools Installer",
            description=description,
            actions=actions,
            parent=parent,
        )
