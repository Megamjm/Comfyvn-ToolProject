from __future__ import annotations
# comfyvn/core/settings_manager.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import copy
import json
from pathlib import Path
from comfyvn.config.runtime_paths import settings_file

try:
    from PySide6.QtGui import QAction  # type: ignore  # pragma: no cover
except Exception:  # pragma: no cover - optional dependency
    QAction = None  # type: ignore

DEFAULTS = {
    "developer": {"verbose": True, "toasts": True, "file_only": False},
    "ui": {"menu_sort_mode": "load_order"},
    "server": {"local_port": 8001},
    "policy": {
        "ack_legal_v1": False,
        "ack_timestamp": None,
        "warn_override_enabled": True,
    },
    "filters": {
        "content_mode": "sfw",  # sfw | warn | unrestricted
    },
    "audio": {
        "tts": {
            "active_provider": "comfyui_local",
            "providers": [
                {
                    "id": "comfyui_local",
                    "label": "ComfyUI (Local Workflow)",
                    "kind": "open_source",
                    "base_url": "http://127.0.0.1:8188",
                    "workflow": "workflows/tts_comfy.json",
                    "output_dir": "~/ComfyUI/output/audio",
                },
                {
                    "id": "bark_open",
                    "label": "Bark (Open Source)",
                    "kind": "open_source",
                    "portal": "https://github.com/suno-ai/bark",
                    "notes": "Run locally via the Bark Python package and feed results through custom adapters.",
                },
                {
                    "id": "coqui_xtts",
                    "label": "Coqui XTTS (Freemium)",
                    "kind": "freemium",
                    "portal": "https://coqui.ai",
                    "notes": "Cloud-hosted XTTS voices with a free tier; requires API token.",
                },
                {
                    "id": "elevenlabs",
                    "label": "ElevenLabs",
                    "kind": "paid",
                    "portal": "https://elevenlabs.io",
                    "notes": "Commercial TTS with per-character billing and high quality neural voices.",
                },
                {
                    "id": "azure_speech",
                    "label": "Azure Speech",
                    "kind": "paid",
                    "portal": "https://azure.microsoft.com/products/cognitive-services/speech-services/",
                    "notes": "Microsoft Azure Speech service; priced pay-as-you-go, requires subscription key.",
                },
            ],
            "fallback_mode": "synthetic",
        },
        "music": {
            "active_provider": "comfyui_local",
            "providers": [
                {
                    "id": "comfyui_local",
                    "label": "ComfyUI MusicGen Workflow",
                    "kind": "open_source",
                    "base_url": "http://127.0.0.1:8188",
                    "workflow": "workflows/musicgen_remix.json",
                    "output_dir": "~/ComfyUI/output/audio",
                },
                {
                    "id": "audiocraft",
                    "label": "Meta AudioCraft / MusicGen",
                    "kind": "open_source",
                    "portal": "https://github.com/facebookresearch/audiocraft",
                    "notes": "Self-host MusicGen models for deterministic remixing.",
                },
                {
                    "id": "suno_ai",
                    "label": "Suno AI (Bark/Chirp)",
                    "kind": "paid",
                    "portal": "https://suno.ai",
                    "notes": "Commercial music generation API with subscription tiers.",
                },
                {
                    "id": "soundraw",
                    "label": "Soundraw",
                    "kind": "paid",
                    "portal": "https://soundraw.io",
                    "notes": "Browser-based AI music studio with licensing for creators.",
                },
                {
                    "id": "aiva",
                    "label": "AIVA",
                    "kind": "freemium",
                    "portal": "https://www.aiva.ai",
                    "notes": "Classical and cinematic music assistant; offers free previews and paid licensing.",
                },
            ],
            "fallback_mode": "synthetic",
        },
    },
}

class SettingsManager:
    def __init__(self, path: str | Path = settings_file("config.json")):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(DEFAULTS)

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        # backfill defaults
        for k, v in DEFAULTS.items():
            if k not in data:
                data[k] = copy.deepcopy(v)
        return data

    def save(self, data: dict):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, key: str, default=None):
        return self.load().get(key, default)

    def patch(self, key: str, value):
        cfg = self.load()
        cfg[key] = value
        self.save(cfg)
        return cfg
