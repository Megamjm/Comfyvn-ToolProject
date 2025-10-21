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

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from comfyvn import __version__

try:  # normalise the application version for compatibility checks
    _APP_VERSION = Version(__version__)
except InvalidVersion:
    _APP_VERSION = Version("0")


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
    entrypoint: Optional[Path] = None
    compatible: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    required_spec: Optional[str] = None
    api_version: Optional[str] = None


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
    entrypoint: Optional[Path] = None
    errors: List[str] = []
    warnings: List[str] = []
    compatible = True
    api_version = None

    if not manifest_file.exists():
        warnings.append("Missing extension.json manifest; using best-effort defaults.")

    entrypoint_decl = data.get("entrypoint")
    if isinstance(entrypoint_decl, str) and entrypoint_decl:
        candidate = ext_dir / entrypoint_decl
        if candidate.is_file():
            entrypoint = candidate
        else:
            errors.append(f"entrypoint '{entrypoint_decl}' not found")
            compatible = False
    if entrypoint is None:
        for fallback in ("extension.py", "main.py", "__init__.py"):
            candidate = ext_dir / fallback
            if candidate.is_file():
                entrypoint = candidate
                break
    if entrypoint is None:
        warnings.append("No Python entrypoint discovered; extension will not be loaded.")
        compatible = False

    requires = data.get("requires")
    required_spec = None
    if isinstance(requires, dict):
        required_spec = requires.get("comfyvn") or requires.get("app")
    elif isinstance(requires, str):
        required_spec = requires

    min_app = data.get("min_app_version")
    max_app = data.get("max_app_version")
    spec_tokens: List[str] = []
    if required_spec:
        spec_tokens.append(str(required_spec))
    if isinstance(min_app, str) and min_app:
        spec_tokens.append(f">={min_app}")
    if isinstance(max_app, str) and max_app:
        spec_tokens.append(f"<={max_app}")

    resolved_spec = None
    if spec_tokens:
        spec_expr = ",".join(spec_tokens)
        try:
            spec = SpecifierSet(spec_expr)
            resolved_spec = str(spec)
            if _APP_VERSION not in spec:
                compatible = False
                errors.append(
                    f"Requires ComfyVN {resolved_spec}; current version is {_APP_VERSION}"
                )
        except (InvalidSpecifier, InvalidVersion) as exc:
            compatible = False
            errors.append(f"Invalid version specifier '{spec_expr}': {exc}")

    api_version = data.get("api_version") or data.get("studio_api")
    if api_version is not None and not isinstance(api_version, (int, str)):
        warnings.append("api_version should be a string or integer; ignoring value")
        api_version = None

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
        entrypoint=entrypoint,
        compatible=compatible,
        errors=errors,
        warnings=warnings,
        required_spec=resolved_spec,
        api_version=str(api_version) if api_version is not None else None,
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
        entrypoint=py_file,
        warnings=["Single-file extensions are loaded without manifest metadata."],
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
