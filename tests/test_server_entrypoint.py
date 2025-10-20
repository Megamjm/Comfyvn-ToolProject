from __future__ import annotations

import asyncio

import sys
import types

from fastapi.routing import APIRoute

# Provide a minimal PySide6 stub so server modules can import without Qt runtime.
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui

from comfyvn.app import create_app


def test_health_routes_available():
    app = create_app()
    def _find(name: str) -> APIRoute:
        for route in app.routes:
            if isinstance(route, APIRoute) and route.endpoint.__name__ == name:
                return route
        raise AssertionError(f"Route {name} not found")

    health_route = _find("core_health")
    assert health_route.path == "/health"
    health_result = health_route.endpoint()  # type: ignore[call-arg]
    if asyncio.iscoroutine(health_result):
        health_result = asyncio.run(health_result)
    assert health_result == {"status": "ok"}

    legacy_route = _find("_healthz")
    assert legacy_route.path == "/healthz"
    legacy_result = legacy_route.endpoint()  # type: ignore[call-arg]
    if asyncio.iscoroutine(legacy_result):
        legacy_result = asyncio.run(legacy_result)
    assert legacy_result == {"ok": True}

    status_route = _find("core_status")
    assert status_route.path == "/status"
    status_result = status_route.endpoint()  # type: ignore[call-arg]
    if asyncio.iscoroutine(status_result):
        status_result = asyncio.run(status_result)
    assert status_result["ok"] is True
    assert isinstance(status_result.get("routes"), list)
