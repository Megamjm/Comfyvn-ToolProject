from __future__ import annotations

from fastapi.testclient import TestClient

from comfyvn.server.app import create_app
from comfyvn.themes import available_templates, plan


def _sample_scene():
    return {
        "scene_id": "scene-001",
        "world": {"id": "world-42"},
        "theme": {
            "assets": {"backdrop": "city/old"},
            "luts": ["neutral"],
            "music": {"set": "silence"},
            "prompt": {"style": "plain"},
        },
        "characters": [
            {"id": "alex", "roles": ["protagonist"], "theme": {"palette": "cool"}},
            {"id": "blair", "roles": ["antagonist"], "theme": {"palette": "cool"}},
        ],
    }


def test_theme_plan_is_deterministic_with_overrides():
    overrides = {"characters": {"alex": {"accent": "bright"}}}
    scene = _sample_scene()

    first = plan("Modern", scene, overrides=overrides)
    second = plan("Modern", scene, overrides=overrides)

    assert first == second
    assert first["checksum"] == second["checksum"]

    char_delta = next(
        item for item in first["mutations"]["characters"] if item["id"] == "alex"
    )
    assert char_delta["after"]["accent"] == "bright"
    assert char_delta["changed"] is True


def test_theme_apply_route_returns_plan_delta():
    app = create_app()
    payload = {
        "theme": "Fantasy",
        "scene": _sample_scene(),
        "overrides": {"characters": {"blair": {"accent": "violet"}}},
    }

    with TestClient(app) as client:
        response = client.post("/api/themes/apply", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["plan_delta"]["theme"] == "Fantasy"
        assert (
            data["plan_delta"]["mutations"]["assets"]["after"]["backdrop"]
            == "fantasy/forest_grove"
        )
        assert data["plan_delta"]["checksum"]
        templates = data["templates"]
        assert "Fantasy" in templates
        assert set(templates) == set(available_templates())

        response_again = client.post("/api/themes/apply", json=payload)
        assert (
            response_again.json()["data"]["plan_delta"]["checksum"]
            == data["plan_delta"]["checksum"]
        )


def test_theme_apply_route_handles_unknown_theme():
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/api/themes/apply", json={"theme": "Unknown"})
        assert response.status_code == 404
