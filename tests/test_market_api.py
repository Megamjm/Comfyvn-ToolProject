from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from comfyvn.market import ExtensionMarket, build_extension_package
from comfyvn.server.modules import market_api


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
    return {"ok": True}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_market_api_install_list_uninstall(tmp_path, monkeypatch):
    src = tmp_path / "ext"
    _write_extension(src)
    package = build_extension_package(src, output=tmp_path)

    market = ExtensionMarket(
        extensions_root=tmp_path / "extensions",
        state_path=tmp_path / "state.json",
    )
    monkeypatch.setattr(market_api, "_market", market)
    monkeypatch.setattr(market_api.feature_flags, "is_enabled", lambda *_, **__: True)

    app = FastAPI()
    app.include_router(market_api.router)
    client = TestClient(app)

    resp = client.post(
        "/api/market/install", json={"package": str(package.package_path)}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["installed"]["id"] == "sample.toolkit"

    resp = client.get("/api/market/installed")
    assert resp.status_code == 200
    assert any(item["id"] == "sample.toolkit" for item in resp.json()["items"])

    resp = client.post("/api/market/uninstall", json={"id": "sample.toolkit"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = client.get("/api/market/installed")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
