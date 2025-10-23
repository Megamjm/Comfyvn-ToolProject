from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

pytest.importorskip("httpx")

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

from fastapi.testclient import TestClient

from comfyvn.server.app import create_app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer testtoken"}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("API_TOKEN", "testtoken")
    assets_root = tmp_path / "assets"
    thumbs_root = tmp_path / "thumbs"
    monkeypatch.setenv("COMFYVN_ASSETS_ROOT", str(assets_root))
    monkeypatch.setenv("COMFYVN_THUMBS_ROOT", str(thumbs_root))
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.mark.skipif(
    Image is None, reason="Pillow required for PNG provenance/thumbnail check"
)
def test_upload_png_writes_sidecar_thumbnail_and_provenance_marker(
    client: TestClient, tmp_path: Path
):
    buf = io.BytesIO()
    img = Image.new("RGB", (8, 8), color=(123, 45, 67))  # type: ignore[attr-defined]
    img.save(buf, format="PNG")  # type: ignore[attr-defined]
    payload = buf.getvalue()

    resp = client.post(
        "/assets/upload",
        headers=_auth_headers(),
        files={"file": ("tiny.png", payload, "image/png")},
        data={
            "asset_type": "images",
            "metadata": json.dumps({"license": "cc0", "user_id": "pytest"}),
        },
    )
    assert resp.status_code == 200, resp.text
    asset = resp.json()["asset"]

    # Sidecar exists and includes provenance + meta
    sidecar_path = Path("data/assets/_meta") / Path(asset["path"]).with_suffix(".json")
    assert sidecar_path.exists(), f"missing sidecar: {sidecar_path}"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar.get("meta", {}).get("license") == "cc0"
    assert sidecar.get("provenance") and sidecar["provenance"].get("id")

    # Thumbnail recorded and file present on disk (when Pillow available)
    thumb_rel = asset.get("thumb")
    assert thumb_rel is None or Path(thumb_rel).exists(), f"thumb missing: {thumb_rel}"

    # Embedded provenance marker present in PNG metadata
    saved_path = Path("data/assets") / asset["path"]
    with Image.open(saved_path) as stamped:  # type: ignore[attr-defined]
        text_items = getattr(stamped, "text", {}) or {}
        marker = text_items.get("comfyvn_provenance")
    assert marker, "expected comfyvn_provenance PNG text chunk"


@pytest.mark.xfail(reason="ID3 provenance embedding not implemented yet", strict=False)
def test_upload_audio_embeds_id3_provenance_marker(client: TestClient, tmp_path: Path):
    # Minimal fake MP3 payload; API should still accept and register
    fake_mp3 = b"ID3\x03\x00\x00\x00\x00\x00\x0fTESTAUDIO"
    resp = client.post(
        "/assets/upload",
        headers=_auth_headers(),
        files={"file": ("sample.mp3", fake_mp3, "audio/mpeg")},
        data={
            "asset_type": "audio",
            "metadata": json.dumps({"license": "cc0", "user_id": "pytest"}),
        },
    )
    assert resp.status_code == 200, resp.text
    asset = resp.json()["asset"]

    # Sidecar exists
    sidecar_path = Path("data/assets/_meta") / Path(asset["path"]).with_suffix(".json")
    assert sidecar_path.exists()

    # Placeholder assertion for future ID3 provenance marker
    # Once implemented, parse ID3 and verify marker frame presence.
    saved = Path("data/assets") / asset["path"]
    data = saved.read_bytes()
    assert b"comfyvn_provenance" in data  # expected to fail until implemented


def test_public_asset_register_and_fetch(client: TestClient, tmp_path: Path):
    source = tmp_path / "api_asset.txt"
    source.write_text("api-asset", encoding="utf-8")

    payload = {
        "path": str(source),
        "asset_type": "documents",
        "metadata": {"tags": ["api-test"], "license": "CC-BY-4.0"},
    }

    register_resp = client.post("/api/assets/register", json=payload)
    assert register_resp.status_code == 200, register_resp.text
    register_payload = register_resp.json()
    asset_id = register_payload["asset_id"]
    asset_body = register_payload["asset"]
    assert asset_body["id"] == asset_id
    assert asset_body["metadata"]["tags"] == ["api-test"]
    assert "links" in asset_body and "file" in asset_body["links"]

    fetch_resp = client.get(f"/api/assets/{asset_id}")
    assert fetch_resp.status_code == 200, fetch_resp.text
    fetched = fetch_resp.json()["asset"]
    assert fetched["id"] == asset_id
    assert fetched["metadata"]["license"] == "CC-BY-4.0"

    search_resp = client.get("/api/assets/search", params={"q": source.name})
    assert search_resp.status_code == 200, search_resp.text
    search_payload = search_resp.json()
    assert search_payload["filters"]["q"] == source.name
    assert search_payload["total"] >= 1
    assert any(item["id"] == asset_id for item in search_payload["items"])

    duplicate_resp = client.post("/api/assets/register", json=payload)
    assert duplicate_resp.status_code == 200, duplicate_resp.text
    assert duplicate_resp.json()["asset_id"] == asset_id


def test_asset_debug_endpoints_surface_modder_hooks(client: TestClient):
    payload = b"sample debug payload"
    resp = client.post(
        "/assets/upload",
        headers=_auth_headers(),
        files={"file": ("debug.txt", payload, "text/plain")},
        data={"asset_type": "documents"},
    )
    assert resp.status_code == 200, resp.text
    asset = resp.json()["asset"]
    uid = asset["uid"]

    hooks_resp = client.get("/assets/debug/hooks")
    assert hooks_resp.status_code == 200, hooks_resp.text
    hooks_payload = hooks_resp.json()
    hooks = hooks_payload.get("hooks") or {}
    assert isinstance(hooks, dict)
    if hooks:
        assert "asset_registered" in hooks
        assert isinstance(hooks["asset_registered"], list)

    specs_resp = client.get("/assets/debug/modder-hooks")
    assert specs_resp.status_code == 200, specs_resp.text
    specs_payload = specs_resp.json()
    spec_names = {item["name"] for item in specs_payload.get("hooks", [])}
    assert {
        "on_asset_saved",
        "on_asset_registered",
        "on_asset_meta_updated",
        "on_asset_removed",
        "on_asset_sidecar_written",
    }.issubset(spec_names)

    history_resp = client.get("/assets/debug/history", params={"limit": 5})
    assert history_resp.status_code == 200, history_resp.text
    history_payload = history_resp.json()
    items = history_payload.get("items") or []
    assert items, "expected at least one asset modder event"
    asset_events = [
        entry
        for entry in items
        if entry.get("event") in {"on_asset_saved", "on_asset_registered"}
    ]
    assert asset_events, "expected on_asset_saved/on_asset_registered events in history"
    matching_event = next(
        (entry for entry in asset_events if entry.get("data", {}).get("uid") == uid),
        None,
    )
    assert matching_event, f"expected history entry for uid {uid}"
    data = matching_event.get("data") or {}
    assert data.get("hook_event") == "asset_registered"
