from __future__ import annotations

import json
import os
import shutil
import wave
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("COMFYVN_ACCESSIBILITY_DISABLED", "1")
os.environ.setdefault("COMFYVN_GPU_MANAGER_DISABLED", "1")
os.environ.setdefault("COMFYVN_SKIP_APP_AUTOLOAD", "1")

from comfyvn.config import feature_flags
from comfyvn.core import audio_stub, music_remix
from comfyvn.core.audio_cache import AudioCacheManager
from comfyvn.server.modules import music_api
from comfyvn.studio.core import AssetRegistry


def test_synth_voice_generates_wav_and_hits_cache(tmp_path, monkeypatch):
    export_dir = tmp_path / "tts"
    cache_path = tmp_path / "audio_cache.json"

    manager = AudioCacheManager(path=cache_path)
    monkeypatch.setattr(audio_stub, "audio_cache", manager)
    monkeypatch.setenv("COMFYVN_TTS_EXPORT_DIR", str(export_dir))

    artifact1, sidecar1, cached1 = audio_stub.synth_voice(
        "Testing the phase six pipeline.",
        "narrator",
        scene_id="scene-demo",
        character_id="char-a",
        lang="en",
        style="warm",
    )

    assert cached1 is False
    artifact_path = Path(artifact1)
    sidecar_path = Path(sidecar1)
    assert artifact_path.suffix == ".wav"
    assert artifact_path.exists()
    assert sidecar_path.exists()

    with wave.open(str(artifact_path), "rb") as wav_file:
        assert wav_file.getframerate() == audio_stub.DEFAULT_SAMPLE_RATE
        assert wav_file.getnchannels() == 1
        assert wav_file.getnframes() > 0

    meta = json.loads(sidecar_path.read_text())
    assert meta["voice"] == "narrator"
    assert meta["lang"] == "en"
    assert meta["style"] == "warm"
    assert meta["format"] == "wav"
    assert meta["duration_seconds"] > 0
    assert meta["seed"] is not None
    assert meta["workflow"]
    assert meta["model"]

    artifact2, sidecar2, cached2 = audio_stub.synth_voice(
        "Testing the phase six pipeline.",
        "narrator",
        scene_id="scene-demo",
        character_id="char-a",
        lang="en",
        style="warm",
    )

    assert cached2 is True
    assert artifact2 == artifact1
    assert sidecar2 == sidecar1
    assert len(manager._entries) == 1


def test_music_remix_generates_wav_and_reuses_cache(tmp_path, monkeypatch):
    export_dir = tmp_path / "music"
    cache_path = tmp_path / "music_cache.json"

    cache = music_remix.MusicCacheManager(path=cache_path)
    monkeypatch.setattr(music_remix, "music_cache", cache)
    monkeypatch.setenv("COMFYVN_MUSIC_EXPORT_DIR", str(export_dir))

    artifact1, sidecar1, cached1, meta1 = music_remix.remix_track(
        scene_id="scene.demo",
        target_style="lofi",
        seed=1234,
        mood_tags=["calm", "night"],
    )

    assert cached1 is False
    artifact_path = Path(artifact1)
    sidecar_path = Path(sidecar1)
    assert artifact_path.suffix == ".wav"
    assert artifact_path.exists()
    assert sidecar_path.exists()

    with wave.open(str(artifact_path), "rb") as wav_file:
        assert wav_file.getframerate() == music_remix.DEFAULT_SAMPLE_RATE
        assert wav_file.getnframes() > 0
        assert wav_file.getnchannels() in {1, 2}

    payload = json.loads(sidecar_path.read_text())
    assert payload["scene_id"] == "scene.demo"
    assert payload["target_style"] == "lofi"
    assert payload["duration_seconds"] > 0
    assert "tempo" in payload
    assert meta1["cache_key"]
    assert meta1["duration_seconds"] == payload["duration_seconds"]

    artifact2, sidecar2, cached2, meta2 = music_remix.remix_track(
        scene_id="scene.demo",
        target_style="lofi",
        seed=1234,
        mood_tags=["calm", "night"],
    )

    assert artifact2 == artifact1
    assert sidecar2 == sidecar1
    assert cached2 is True
    assert meta2["cache_key"] == meta1["cache_key"]
    assert len(cache._entries) == 1


def test_music_api_returns_asset_and_style(tmp_path, monkeypatch):
    export_dir = tmp_path / "music_api"
    cache_path = tmp_path / "music_cache_api.json"
    assets_root = tmp_path / "assets"
    meta_root = assets_root / "_meta"
    thumbs_root = tmp_path / "thumbs"
    db_path = tmp_path / "studio_music.db"

    export_dir.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)
    meta_root.mkdir(parents=True, exist_ok=True)
    thumbs_root.mkdir(parents=True, exist_ok=True)

    cache = music_remix.MusicCacheManager(path=cache_path)
    monkeypatch.setattr(music_remix, "music_cache", cache)
    monkeypatch.setenv("COMFYVN_MUSIC_EXPORT_DIR", str(export_dir))

    registry = AssetRegistry(db_path=db_path)
    registry.ASSETS_ROOT = assets_root
    registry.META_ROOT = meta_root
    registry.THUMB_ROOT = thumbs_root
    monkeypatch.setattr(music_api, "_ASSET_REGISTRY", registry, raising=False)

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
            "uid": f"music-{dest_rel.stem}",
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
    app.include_router(music_api.router)
    with TestClient(app) as client:
        resp = client.post(
            "/api/music/remix",
            json={"scene_id": "scene.demo", "target_style": "lofi", "seed": 123},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["asset_id"]
        assert data["style"] == "lofi"
        assert data["cached"] is False
        assert data["artifact"]
        assert data["duration_ms"] and data["duration_ms"] > 0
        assert Path(data["artifact"]).exists()
        info = data["info"]
        assert info["scene_id"] == "scene.demo"
        assert info["target_style"] == "lofi"
        assert info["cache_key"]
        asset_entry = registered_assets[-1]
        assert asset_entry["uid"] == data["asset_id"]
        assert asset_entry["meta"]["cache_key"] == info["cache_key"]
        asset_path = assets_root / asset_entry["path"]
        assert asset_path.exists()
        resp_cached = client.post(
            "/api/music/remix",
            json={"scene_id": "scene.demo", "target_style": "lofi", "seed": 123},
        )
        assert resp_cached.status_code == 200
        data_cached = resp_cached.json()
        assert data_cached["cached"] is True
        assert data_cached["asset_id"] == data["asset_id"]
        assert data_cached["artifact"] == data["artifact"]
        assert data_cached["duration_ms"] == data["duration_ms"]
