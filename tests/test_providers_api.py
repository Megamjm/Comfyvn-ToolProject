from __future__ import annotations

import sys
import types
from typing import Any, Dict, List

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

# Provide PySide6 stub to satisfy optional imports during app initialization.
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui

from comfyvn.server.app import create_app


class _RegistryStub:
    def __init__(self) -> None:
        self._providers: List[Dict[str, Any]] = [
            {
                "id": "local",
                "name": "Local GPU",
                "kind": "local",
                "service": "comfyui",
                "base_url": "http://127.0.0.1:8188",
                "active": True,
                "priority": 0,
                "config": {},
                "meta": {},
                "last_health": {"ok": True},
            }
        ]

    def templates_public(self) -> list[dict[str, Any]]:
        return []

    def list(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self._providers]

    def register(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider_id = payload.get("id") or payload.get("name") or "provider"
        entry = {
            "id": provider_id,
            "name": payload.get("name", provider_id),
            "kind": payload.get("kind", "remote"),
            "service": payload.get("service", payload.get("kind", "remote")),
            "base_url": payload.get("base_url", ""),
            "active": payload.get("active", True),
            "priority": payload.get("priority", 10),
            "config": payload.get("config") or {},
            "meta": payload.get("meta") or {},
        }
        self._providers = [p for p in self._providers if p["id"] != provider_id]
        self._providers.append(entry)
        return dict(entry)

    def get(self, provider_id: str) -> dict[str, Any] | None:
        for entry in self._providers:
            if entry["id"] == provider_id:
                return dict(entry)
        return None

    def active_providers(self) -> list[dict[str, Any]]:
        return [dict(p) for p in self._providers if p.get("active", True)]

    def record_health(
        self, provider_id: str, status: dict[str, Any]
    ) -> dict[str, Any] | None:
        for entry in self._providers:
            if entry["id"] == provider_id:
                entry["last_health"] = dict(status)
                return dict(status)
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    from comfyvn.server.modules import providers_api

    registry = _RegistryStub()
    providers_api.REGISTRY = registry  # type: ignore[assignment]
    monkeypatch.setattr(
        providers_api,
        "provider_health",
        lambda entry: {"ok": True, "echo": entry["id"]},
    )

    app = create_app()
    with TestClient(app) as c:
        yield c, registry


def test_get_providers_root(client: tuple[TestClient, _RegistryStub]):
    http, registry = client
    resp = http.get("/api/providers")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert any(row["id"] == "local" for row in payload["providers"])
    assert payload["templates"] == []


def test_register_and_health(client: tuple[TestClient, _RegistryStub]):
    http, registry = client
    body = {
        "id": "runpod",
        "name": "RunPod",
        "kind": "remote",
        "service": "runpod",
        "base_url": "https://api.runpod.io/v2/",
    }
    resp = http.post("/api/providers/register", json=body)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["provider"]["id"] == "runpod"

    resp = http.get("/api/providers")
    assert any(row["id"] == "runpod" for row in resp.json()["providers"])

    health = http.get("/api/providers/health", params={"id": "runpod"})
    assert health.status_code == 200, health.text
    status = health.json()
    assert status["ok"] is True
    assert status["status"]["provider_id"] == "runpod"
    assert status["status"]["ok"] is True
