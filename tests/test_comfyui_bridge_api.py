from __future__ import annotations

from fastapi.testclient import TestClient

from comfyvn.server.app import create_app
from comfyvn.server.modules import comfyui_bridge_api as comfy_module


def test_comfyui_submit_unavailable_returns_503(monkeypatch) -> None:
    monkeypatch.setattr(
        comfy_module._bridge,
        "submit",
        lambda payload: {"ok": False, "error": "offline"},
    )
    comfy_module._hardened._feature_enabled = False

    app = create_app(enable_cors=False)

    with TestClient(app) as client:
        response = client.post(
            "/comfyui/submit", json={"workflow": {"graph": {"nodes": []}}}
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "offline"
