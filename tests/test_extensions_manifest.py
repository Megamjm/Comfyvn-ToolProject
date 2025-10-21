from __future__ import annotations

import json
from pathlib import Path

from comfyvn.core.extensions_discovery import load_extension_metadata


def test_demo_extension_metadata_includes_entrypoint():
    base = Path("extensions")
    metadata = load_extension_metadata(base)
    demo = next(meta for meta in metadata if meta.id == "demo_tool")
    assert demo.entrypoint is not None
    assert demo.entrypoint.exists()
    assert demo.compatible
    assert demo.required_spec is not None


def test_incompatible_manifest_is_flagged(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    manifest = {
        "id": "bad_ext",
        "name": "Bad Extension",
        "version": "0.0.1",
        "entrypoint": "extension.py",
        "requires": {"comfyvn": ">=999.0"},
    }
    (ext_dir / "extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    (ext_dir / "extension.py").write_text("""
from comfyvn.core.menu_runtime_bridge import MenuRegistry


def register(registry: MenuRegistry) -> None:
    registry.add("Placeholder", handler="noop")
""", encoding="utf-8")

    metadata = load_extension_metadata(ext_dir.parent)
    bad = next(meta for meta in metadata if meta.id == "bad_ext")
    assert not bad.compatible
    assert bad.errors, "Expected incompatibility errors to be recorded"
