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
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TOKEN", "testtoken")
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
