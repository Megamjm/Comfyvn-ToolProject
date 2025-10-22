from __future__ import annotations

import json
from pathlib import Path

import pytest

from comfyvn.market import ExtensionMarket, ManifestError, build_extension_package


def _write_extension(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": "sample.toolkit",
        "name": "Sample Toolkit",
        "version": "1.2.3",
        "summary": "Sample toolkit for marketplace tests",
        "description": "Provides helper routes for tests",
        "permissions": [{"scope": "assets.read"}],
        "routes": [
            {
                "path": "/",
                "entry": "handlers.py",
                "callable": "handlers.endpoint",
                "methods": ["GET"],
            }
        ],
        "hooks": ["on_scene_enter"],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (root / "handlers.py").write_text(
        """
def endpoint(payload, extension_id=None):
    return {"ok": True, "payload": payload}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_extension_market_install_and_uninstall(tmp_path):
    src = tmp_path / "ext"
    _write_extension(src)
    result = build_extension_package(src, output=tmp_path)
    market = ExtensionMarket(
        extensions_root=tmp_path / "extensions",
        state_path=tmp_path / "state.json",
    )

    install = market.install(result.package_path)
    installed = market.list_installed()

    assert install.extension_id == "sample.toolkit"
    assert install.trust.level == "unverified"
    assert install.target_path.exists()
    assert any(item["id"] == "sample.toolkit" for item in installed)

    with pytest.raises(ManifestError):
        market.install(result.package_path)

    assert market.uninstall("sample.toolkit") is True
    assert not install.target_path.exists()
    assert market.list_installed() == []


def test_packaging_rejects_unverified_global_routes(tmp_path):
    root = tmp_path / "ext-global"
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": "global.extension",
        "name": "Global Extension",
        "version": "0.1.0",
        "summary": "Attempts to expose global routes",
        "routes": [
            {
                "path": "/api/system/ping",
                "entry": "handlers.py",
                "callable": "handlers.endpoint",
                "expose": "global",
            }
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (root / "handlers.py").write_text(
        "def endpoint(payload, extension_id=None):\n    return {}\n", encoding="utf-8"
    )

    with pytest.raises(ManifestError):
        build_extension_package(root, output=tmp_path)
