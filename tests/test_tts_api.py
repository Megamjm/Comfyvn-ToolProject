from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from comfyvn.core.audio_cache import AudioCacheManager
from comfyvn.core import audio_stub
from comfyvn.server.app import create_app
from comfyvn.server.modules import tts_api
from comfyvn.studio.core import AssetRegistry


def test_tts_synthesize_registers_asset_and_hits_cache(tmp_path, monkeypatch):
    export_dir = tmp_path / "tts"
    cache_path = tmp_path / "audio_cache.json"
    assets_root = tmp_path / "assets"
    meta_root = assets_root / "_meta"
    thumbs_root = tmp_path / "thumbs"
    db_path = tmp_path / "studio.db"

    export_dir.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)
    meta_root.mkdir(parents=True, exist_ok=True)
    thumbs_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("COMFYVN_TTS_EXPORT_DIR", str(export_dir))

    cache_manager = AudioCacheManager(path=cache_path)
    monkeypatch.setattr(audio_stub, "audio_cache", cache_manager, raising=False)

    registry = AssetRegistry(db_path=db_path)
    registry.ASSETS_ROOT = assets_root
    registry.META_ROOT = meta_root
    registry.THUMB_ROOT = thumbs_root
    monkeypatch.setattr(tts_api, "_ASSET_REGISTRY", registry, raising=False)

    app = create_app()
    with TestClient(app) as client:
        payload = {
            "text": "Testing the cache aware pipeline.",
            "voice": "narrator",
            "scene_id": "scene.demo",
            "line_id": "line-01",
            "character_id": "char-a",
            "lang": "en",
            "style": "calm",
            "device_hint": "cpu",
        }
        resp = client.post("/api/tts/synthesize", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["cached"] is False
        assert data["asset"] is not None
        asset = data["asset"]
        assert asset["meta"]["scene_id"] == "scene.demo"
        assert asset["meta"]["line_id"] == "line-01"
        assert asset["meta"]["cache_key"] == data["info"]["cache_key"]
        assert asset["meta"]["device_hint"] == "cpu"
        assert data["info"]["asset_uid"] == asset["uid"]

        asset_path = assets_root / asset["path"]
        assert asset_path.exists()
        sidecar_path = (meta_root / Path(asset["path"])).with_suffix(".json")
        assert sidecar_path.exists()
        provenance = asset.get("provenance")
        assert provenance is not None
        assert provenance["source"] == "api.tts.synthesize"

        payload_again = payload | {"metadata": {"user_id": "tester"}}
        resp_cached = client.post("/api/tts/synthesize", json=payload_again)
        assert resp_cached.status_code == 200
        data_cached = resp_cached.json()
        assert data_cached["cached"] is True
        assert data_cached["artifact"] == data["artifact"]
        assert data_cached["info"]["cache_key"] == data["info"]["cache_key"]

        cache_contents = json.loads(cache_path.read_text(encoding="utf-8"))
        assert len(cache_contents) == 1
