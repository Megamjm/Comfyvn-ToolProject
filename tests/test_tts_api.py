from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("COMFYVN_ACCESSIBILITY_DISABLED", "1")
os.environ.setdefault("COMFYVN_GPU_MANAGER_DISABLED", "1")
os.environ.setdefault("COMFYVN_SKIP_APP_AUTOLOAD", "1")

from comfyvn.config import feature_flags
from comfyvn.core import audio_stub
from comfyvn.core.audio_cache import AudioCacheManager
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

    registered_assets: list[dict[str, object]] = []

    def _fake_register_file(
        source_path: Path,
        asset_type: str,
        dest_relative: Path | str,
        *,
        metadata: dict,
        copy: bool = True,
        provenance: dict | None = None,
        license_tag: str | None = None,
    ) -> dict[str, object]:
        dest_rel = Path(dest_relative)
        dest_full = assets_root / dest_rel
        dest_full.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copy2(source_path, dest_full)
        sidecar_src = metadata.get("sidecar")
        if sidecar_src:
            sidecar_src_path = Path(sidecar_src)
            sidecar_dest = (meta_root / dest_rel).with_suffix(".json")
            sidecar_dest.parent.mkdir(parents=True, exist_ok=True)
            if sidecar_src_path.exists():
                shutil.copy2(sidecar_src_path, sidecar_dest)
        asset_info = {
            "uid": f"asset-{dest_rel.stem}",
            "path": str(dest_rel),
            "meta": metadata,
            "provenance": provenance or {},
        }
        registered_assets.append(asset_info)
        return dict(asset_info)

    monkeypatch.setattr(registry, "register_file", _fake_register_file, raising=False)

    original_is_enabled = feature_flags.is_enabled

    def _mock_is_enabled(name: str, *, default=None, refresh: bool = False) -> bool:
        if name == "enable_audio_lab":
            return True
        return original_is_enabled(name, default=default, refresh=refresh)

    monkeypatch.setattr(feature_flags, "is_enabled", _mock_is_enabled, raising=False)

    app = FastAPI()
    app.include_router(tts_api.router)
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
        payload["seed"] = 4242
        resp = client.post("/api/tts/synthesize", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["cached"] is False
        assert data["asset"] is not None
        asset = data["asset"]
        assert data["asset_id"] == asset["uid"]
        assert data["duration_ms"] and data["duration_ms"] > 0
        voice_meta = data["voice_meta"]
        assert voice_meta["voice"] == "narrator"
        assert voice_meta["lang"] == "en"
        assert voice_meta["style"] == "calm"
        assert voice_meta["cached"] is False
        assert asset["meta"]["scene_id"] == "scene.demo"
        assert asset["meta"]["line_id"] == "line-01"
        assert asset["meta"]["cache_key"] == data["info"]["cache_key"]
        assert asset["meta"]["device_hint"] == "cpu"
        assert asset["meta"]["seed"] == 4242
        assert data["info"]["asset_uid"] == asset["uid"]
        assert data["info"]["seed"] == 4242
        assert data["info"]["route"] == "api.tts.synthesize"
        assert data["info"]["duration_ms"] == data["duration_ms"]

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
        assert data_cached["info"]["seed"] == 4242
        assert data_cached["info"]["route"] == "api.tts.synthesize"
        assert data_cached["asset_id"] == data["asset_id"]
        assert data_cached["duration_ms"] == data["duration_ms"]
        voice_meta_cached = data_cached["voice_meta"]
        assert voice_meta_cached["cached"] is True
        assert voice_meta_cached["voice"] == "narrator"
        assert voice_meta_cached["lang"] == "en"

        cache_contents = json.loads(cache_path.read_text(encoding="utf-8"))
        assert len(cache_contents) == 1
