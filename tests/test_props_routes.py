from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.props import PROP_MANAGER
from comfyvn.server.routes.props import router


def _create_props_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture(autouse=True)
def _reset_props_manager():
    PROP_MANAGER.clear()
    yield
    PROP_MANAGER.clear()


@pytest.fixture(autouse=True)
def _enable_props_flag(monkeypatch):
    original_is_enabled = feature_flags.is_enabled

    def _patched(name: str, *, default=None, refresh: bool = False):
        if name == "enable_props":
            return True
        return original_is_enabled(name, default=default, refresh=refresh)

    monkeypatch.setattr(feature_flags, "is_enabled", _patched)
    feature_flags.refresh_cache()
    try:
        yield
    finally:
        feature_flags.refresh_cache()


@pytest.fixture
def _capture_prop_events():
    events: List[Tuple[str, Dict[str, Any]]] = []

    def _listener(event: str, payload: Dict[str, Any]) -> None:
        events.append((event, payload))

    modder_hooks.register_listener(
        _listener, events=["on_prop_applied", "on_prop_removed"]
    )
    try:
        yield events
    finally:
        modder_hooks.unregister_listener(
            _listener, events=["on_prop_applied", "on_prop_removed"]
        )


def test_ensure_prop_creates_sidecar_and_dedupes() -> None:
    with TestClient(_create_props_app()) as client:
        first = client.post(
            "/api/props/ensure",
            json={
                "prop_id": "torch",
                "asset": "props/torch.png",
                "style": "VISUAL_STYLE_MAPPER::torch",
                "tags": ["light", "ambient"],
                "alpha_mode": "sdf_outline",
            },
        )
        assert first.status_code == 200
        payload_first = first.json()
        assert payload_first["deduped"] is False
        assert payload_first["thumbnail"].startswith("thumbnails/props/")
        assert payload_first["sidecar"]["render"]["alpha_mode"] == "sdf_outline"
        assert payload_first["sidecar"]["render"]["generator"] == "visual_style_mapper"

        second = client.post(
            "/api/props/ensure",
            json={
                "prop_id": "torch",
                "asset": "props/torch.png",
                "style": "VISUAL_STYLE_MAPPER::torch",
                "tags": ["light", "ambient"],
                "alpha_mode": "sdf_outline",
            },
        )
        assert second.status_code == 200
        payload_second = second.json()
        assert payload_second["deduped"] is True
        assert payload_second["thumbnail"] == payload_first["thumbnail"]
        assert payload_second["sidecar"] == payload_first["sidecar"]

        list_resp = client.get("/api/props")
        assert list_resp.status_code == 200
        items = list_resp.json()["props"]
        assert any(item["prop"]["id"] == "torch" for item in items)


def test_apply_prop_evaluates_conditions_and_emits_hook(_capture_prop_events) -> None:
    events = _capture_prop_events
    with TestClient(_create_props_app()) as client:
        ensure_resp = client.post(
            "/api/props/ensure",
            json={"prop_id": "banner", "asset": "props/banner.png"},
        )
        assert ensure_resp.status_code == 200

        show_resp = client.post(
            "/api/props/apply",
            json={
                "prop_id": "banner",
                "anchor": "right_hand",
                "conditions": 'emotion == "amped"',
                "tween": {"duration": 0.6, "ease": "easeOutQuad", "kind": "drift"},
                "state": {"emotion": "amped"},
            },
        )
        assert show_resp.status_code == 200
        show_payload = show_resp.json()
        assert show_payload["visible"] is True
        assert show_payload["evaluations"]['emotion == "amped"'] is True
        assert show_payload["tween"]["stop_at_end"] is True
        assert show_payload["tween"]["kind"] == "drift"
        assert show_payload["thumbnail"]

        hide_resp = client.post(
            "/api/props/apply",
            json={
                "prop_id": "banner",
                "anchor": "right_hand",
                "conditions": ['emotion == "amped"'],
                "state": {"emotion": "calm"},
            },
        )
        assert hide_resp.status_code == 200
        hide_payload = hide_resp.json()
        assert hide_payload["visible"] is False
        assert hide_payload["evaluations"]['emotion == "amped"'] is False

    assert events, "Expected on_prop_applied hook"
    assert any(
        evt == "on_prop_applied"
        and payload["prop_id"] == "banner"
        and payload["sidecar"]["render"]["alpha_mode"] == "premultiplied"
        for evt, payload in events
    )


def test_apply_prop_rejects_invalid_anchor() -> None:
    with TestClient(_create_props_app()) as client:
        client.post(
            "/api/props/ensure", json={"prop_id": "lamp", "asset": "props/lamp.png"}
        )
        resp = client.post(
            "/api/props/apply",
            json={"prop_id": "lamp", "anchor": "invalid-anchor"},
        )
        assert resp.status_code == 400


def test_apply_prop_requires_feature_flag(monkeypatch) -> None:
    def _disabled(name: str, *, default=None, refresh: bool = False):
        return False

    monkeypatch.setattr(feature_flags, "is_enabled", _disabled)
    feature_flags.refresh_cache()
    try:
        with TestClient(_create_props_app()) as client:
            resp = client.post(
                "/api/props/apply",
                json={"prop_id": "shadow", "anchor": "center"},
            )
        assert resp.status_code == 403
    finally:
        feature_flags.refresh_cache()


def test_remove_prop_emits_hook(_capture_prop_events) -> None:
    events = _capture_prop_events
    with TestClient(_create_props_app()) as client:
        ensure_resp = client.post(
            "/api/props/ensure",
            json={"prop_id": "hood", "asset": "props/hood.png"},
        )
        assert ensure_resp.status_code == 200

        remove_resp = client.post("/api/props/remove", json={"id": "hood"})
        assert remove_resp.status_code == 200
        payload = remove_resp.json()
        assert payload["prop"]["id"] == "hood"
        assert payload["sidecar"]["render"]["alpha_mode"] == "premultiplied"

    assert any(
        evt == "on_prop_removed" and payload["prop_id"] == "hood"
        for evt, payload in events
    )
