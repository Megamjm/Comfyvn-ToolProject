from __future__ import annotations

import json
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from comfyvn.core import audio_stub, music_remix
from comfyvn.core.audio_cache import AudioCacheManager
from comfyvn.core.task_registry import task_registry
from comfyvn.server.app import create_app


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

    artifact1, sidecar1 = music_remix.remix_track(
        scene_id="scene.demo",
        target_style="lofi",
        seed=1234,
        mood_tags=["calm", "night"],
    )

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

    artifact2, sidecar2 = music_remix.remix_track(
        scene_id="scene.demo",
        target_style="lofi",
        seed=1234,
        mood_tags=["calm", "night"],
    )

    assert artifact2 == artifact1
    assert sidecar2 == sidecar1
    assert len(cache._entries) == 1


def test_music_api_returns_job_id_and_artifact(tmp_path, monkeypatch):
    export_dir = tmp_path / "music_api"
    cache_path = tmp_path / "music_cache_api.json"
    export_dir.mkdir(parents=True, exist_ok=True)

    cache = music_remix.MusicCacheManager(path=cache_path)
    monkeypatch.setattr(music_remix, "music_cache", cache)
    monkeypatch.setenv("COMFYVN_MUSIC_EXPORT_DIR", str(export_dir))

    app = create_app()
    with TestClient(app) as client:
        resp = client.post(
            "/api/music/remix",
            json={"scene_id": "scene.demo", "target_style": "lofi", "seed": 123},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"]
        assert data["status"] == "done"
        assert data["artifact"]
        assert Path(data["artifact"]).exists()
        job = task_registry.get(data["job_id"])
        assert job is not None
        assert job.status == "done"
        assert job.meta.get("result", {}).get("artifact") == data["artifact"]
