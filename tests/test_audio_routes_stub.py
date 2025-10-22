from __future__ import annotations

import json
import math
from array import array
from pathlib import Path

from fastapi.testclient import TestClient

from comfyvn.bridge import tts_adapter
from comfyvn.config import feature_flags
from comfyvn.server.app import create_app
from comfyvn.server.routes import audio as audio_routes


def _write_sine(
    path: Path,
    *,
    freq: float,
    duration: float = 0.5,
    amp: float = 0.4,
    rate: int = 22050,
) -> None:
    sample_count = int(duration * rate)
    samples = array("h")
    for index in range(sample_count):
        value = math.sin(2 * math.pi * freq * (index / rate)) * amp
        samples.append(int(value * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        import wave

        with wave.open(handle, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(samples.tobytes())


def _enable_audio_lab(monkeypatch) -> None:
    original_is_enabled = feature_flags.is_enabled

    def _fake_is_enabled(name: str, *, default=None, refresh: bool = False):
        if name == "enable_audio_lab":
            return True
        return original_is_enabled(name, default=default, refresh=refresh)

    monkeypatch.setattr(feature_flags, "is_enabled", _fake_is_enabled)


def test_stub_tts_alignment_and_lipsync(tmp_path, monkeypatch):
    cache_root = tmp_path / "tts_cache"
    monkeypatch.setattr(tts_adapter, "_CACHE_ROOT", cache_root)
    _enable_audio_lab(monkeypatch)

    app = create_app()
    with TestClient(app) as client:
        payload = {
            "character": "tester",
            "text": "Hello world preview",
            "style": "calm",
            "model": "stub",
            "lipsync": True,
        }
        resp = client.post("/api/tts/speak", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["alignment"]
        assert data["alignment_checksum"]
        assert data["text_sha1"]
        assert data["lipsync_fps"] == audio_routes._DEFAULT_LIPSYNC_FPS
        alignment_path = Path(data["alignment_path"])
        assert alignment_path.exists()
        lipsync_path = Path(data["lipsync_path"])
        assert lipsync_path.exists()
        assert data["lipsync"]["fps"] == audio_routes._DEFAULT_LIPSYNC_FPS
        sidecar_path = Path(data["sidecar"])
        sidecar_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar_payload["alignment"] == data["alignment"]
        assert sidecar_payload["lipsync"]["path"] == str(lipsync_path)
        assert sidecar_payload["alignment_checksum"] == data["alignment_checksum"]
        assert sidecar_payload["text_sha1"] == data["text_sha1"]


def test_audio_mix_caching(tmp_path, monkeypatch):
    mix_root = tmp_path / "mixes"
    monkeypatch.setattr(audio_routes, "_MIX_ROOT", mix_root)
    _enable_audio_lab(monkeypatch)

    voice_wav = tmp_path / "voice.wav"
    bgm_wav = tmp_path / "bgm.wav"
    _write_sine(voice_wav, freq=440.0, duration=0.6)
    _write_sine(bgm_wav, freq=120.0, duration=1.2, amp=0.5)

    app = create_app()
    with TestClient(app) as client:
        payload = {
            "tracks": [
                {"path": str(voice_wav), "role": "voice", "gain_db": 0.0},
                {"path": str(bgm_wav), "role": "bgm", "gain_db": -6.0},
            ],
            "ducking": {"amount_db": 12.0},
        }

        resp_first = client.post("/api/audio/mix", json=payload)
        assert resp_first.status_code == 200
        data_first = resp_first.json()["data"]
        assert data_first["cached"] is False
        mix_path = Path(data_first["path"])
        assert mix_path.exists()
        sidecar_path = Path(data_first["sidecar"])
        assert sidecar_path.exists()
        assert data_first["checksum_sha1"]
        assert data_first["bytes"]

        resp_second = client.post("/api/audio/mix", json=payload)
        assert resp_second.status_code == 200
        data_second = resp_second.json()["data"]
        assert data_second["cached"] is True
        assert data_second["path"] == data_first["path"]
        assert data_second["cache_key"] == data_first["cache_key"]
        assert data_second["checksum_sha1"] == data_first["checksum_sha1"]
        cached_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert cached_payload["cache_key"] == data_first["cache_key"]
        assert cached_payload["checksum_sha1"] == data_first["checksum_sha1"]


def test_voice_catalog_stub(monkeypatch):
    _enable_audio_lab(monkeypatch)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/tts/voices")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is True
        data = payload["data"]
        assert data["count"] == len(data["voices"])
        assert data["count"] >= 1
        first_voice = data["voices"][0]
        assert first_voice["id"]
        assert first_voice["name"]
        assert "styles" in first_voice
