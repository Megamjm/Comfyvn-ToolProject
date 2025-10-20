"""
Utilities for discovering GUI extensions and their metadata.

Each extension may optionally provide an ``extension.json`` manifest in its
root folder. The manifest is expected to be a JSON object with keys such as:

    {
        "id": "demo_tool",
        "name": "Demo Tool",
        "version": "0.1.0",
        "official": true,
        "description": "Shows how to register a simple toolbar",
        "author": "ComfyVN Team",
        "homepage": "https://example.com"
    }

The legacy ``manifest.json`` file that describes menu hooks is still honoured
and its contents are exposed via the ``hooks`` field for informational
purposes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExtensionMetadata:
    """Lightweight record describing a discovered GUI extension."""

    id: str
    name: str
    path: Path
    official: bool = False
    version: Optional[str] = None
    description: str = ""
    author: Optional[str] = None
    homepage: Optional[str] = None
    manifest_path: Optional[Path] = None
    hooks: List[Dict[str, Any]] = field(default_factory=list)


def _safe_read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _title_from_name(name: str) -> str:
    pretty = name.replace("_", " ").strip().title()
    return pretty or name


def _hooks_from_manifest(path: Path) -> List[Dict[str, Any]]:
    payload = _safe_read_json(path)
    hooks: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        if payload.get("type") == "menu_hook":
            hooks.append(payload)
    elif isinstance(payload, list):
        hooks.extend([item for item in payload if isinstance(item, dict) and item.get("type") == "menu_hook"])
    return hooks


def _build_metadata_from_folder(ext_dir: Path) -> ExtensionMetadata:
    manifest_file = ext_dir / "extension.json"
    data = _safe_read_json(manifest_file) if manifest_file.exists() else {}
    if not isinstance(data, dict):
        data = {}

    ext_id = str(data.get("id") or ext_dir.name)
    name = str(data.get("name") or _title_from_name(ext_id))
    version = data.get("version")
    description = data.get("description") or ""
    author = data.get("author")
    homepage = data.get("homepage")
    official = bool(data.get("official", False))

    hooks_manifest = ext_dir / "manifest.json"
    hooks = _hooks_from_manifest(hooks_manifest) if hooks_manifest.exists() else []

    return ExtensionMetadata(
        id=ext_id,
        name=name,
        path=ext_dir,
        official=official,
        version=version,
        description=description,
        author=author,
        homepage=homepage,
        manifest_path=manifest_file if manifest_file.exists() else None,
        hooks=hooks,
    )


def _build_metadata_from_file(py_file: Path) -> ExtensionMetadata:
    ext_id = py_file.stem
    name = _title_from_name(ext_id)
    return ExtensionMetadata(
        id=ext_id,
        name=name,
        path=py_file,
        official=False,
        description="Imported single-file extension.",
    )


def load_extension_metadata(base_folder: Path) -> List[ExtensionMetadata]:
    """
    Discover extension metadata under ``base_folder``.

    Directories with ``extension.json`` manifests are treated as managed
    extensions. Plain ``.py`` files are treated as imported, single-file
    extensions. Hidden files and internal state files are ignored.
    """
    if not base_folder.exists():
        return []

    metadata: List[ExtensionMetadata] = []
    for entry in sorted(base_folder.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith("."):
            continue
        if entry.suffix == ".json":
            # state/config files inside extensions directory (e.g., state.json)
            continue
        if entry.is_dir():
            metadata.append(_build_metadata_from_folder(entry))
        elif entry.suffix == ".py":
            metadata.append(_build_metadata_from_file(entry))

    return metadata
