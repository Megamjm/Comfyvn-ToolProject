from __future__ import annotations

# comfyvn/core/extension_store.py
from dataclasses import dataclass

from PySide6.QtGui import QAction


@dataclass
class CatalogItem:
    name: str
    desc: str
    repo: str


CATALOG = [
    CatalogItem(
        "Render Manager",
        "Advanced render pipeline controls",
        "local://extensions/render_manager",
    ),
    CatalogItem(
        "SillyTavern Bridge",
        "Chat + VN sync bridge",
        "local://extensions/sillytavern_bridge",
    ),
    CatalogItem(
        "Ren'Py Exporter",
        "Export projects to Ren'Py .rpy",
        "local://extensions/renpy_exporter",
    ),
]
