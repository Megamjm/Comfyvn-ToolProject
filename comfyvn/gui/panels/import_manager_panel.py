from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtWidgets import QWidget

from .json_endpoint_panel import JsonEndpointPanel, PanelAction


class ImportManagerPanel(JsonEndpointPanel):
    """Live Fix Stub — Interactive importer panel with bridge presets."""

    def __init__(self, base_url: str, *, parent: Optional[QWidget] = None) -> None:
        description = """
        Use the presets to probe SillyTavern bridges or submit importer payloads.
        Adjust the JSON payloads to match the export you wish to ingest.
        """
        actions: Iterable[PanelAction] = [
            PanelAction(
                "SillyTavern → Health Probe",
                "GET",
                "/st/health",
                "Confirm the SillyTavern bridge responds before importing assets.",
            ),
            PanelAction(
                "SillyTavern → Sync Extension",
                "POST",
                "/st/extension/sync",
                "Dry-run the comfyvn-data-exporter sync before distributing to SillyTavern.",
                payload={"dry_run": True},
            ),
            PanelAction(
                "Import Persona Bundle",
                "POST",
                "/st/import",
                "Send a persona bundle exported from SillyTavern.",
                payload={"type": "personas", "data": []},
            ),
            PanelAction(
                "Import Lore Library",
                "POST",
                "/st/import",
                "Import world lore JSON to populate story references.",
                payload={"type": "worlds", "data": []},
            ),
            PanelAction(
                "Import Chat Transcript",
                "POST",
                "/st/import",
                "Convert SillyTavern chat history into ComfyVN scenes.",
                payload={"type": "chats", "data": []},
            ),
            PanelAction(
                "Activate World Snapshot",
                "POST",
                "/st/import",
                "Flag a world snapshot as the active reference world.",
                payload={"type": "active", "data": {"active_world": ""}},
            ),
            PanelAction(
                "Import FurAffinity Gallery",
                "POST",
                "/api/imports/furaffinity",
                "Upload a FurAffinity export payload for ingestion.",
                payload={"collection": []},
            ),
            PanelAction(
                "Import Roleplay Archive",
                "POST",
                "/api/imports/roleplay",
                "Import roleplay transcripts exported as JSON or text blocks.",
                payload={"entries": []},
            ),
        ]
        super().__init__(
            base_url,
            title="Import Assets & Bridges",
            description=description,
            actions=actions,
            parent=parent,
        )
