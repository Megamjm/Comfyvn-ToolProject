from __future__ import annotations

# comfyvn/core/settings_manager.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import copy
import json
from pathlib import Path

from comfyvn.config.baseurl_authority import default_base_url
from comfyvn.config.runtime_paths import settings_file

try:
    from PySide6.QtGui import QAction  # type: ignore  # pragma: no cover
except Exception:  # pragma: no cover - optional dependency
    QAction = None  # type: ignore

DEFAULTS = {
    "developer": {"verbose": True, "toasts": True, "file_only": False},
    "ui": {"menu_sort_mode": "load_order"},
    "server": {"local_port": 8001},
    "features": {
        "silly_compat_offload": False,
    },
    "integrations": {
        "sillytavern": {
            "host": "127.0.0.1",
            "port": 8000,
            "base_url": "http://127.0.0.1:8000",
            "plugin_base": "/api/plugins/comfyvn-data-exporter",
            "endpoint": f"{default_base_url().rstrip('/')}/st/import",
            "token": None,
            "user_id": None,
        }
    },
    "policy": {
        "ack_legal_v1": False,
        "ack_timestamp": None,
        "warn_override_enabled": True,
        "ack_user": None,
    },
    "accessibility": {
        "font_scale": 1.0,
        "color_filter": "none",
        "high_contrast": False,
        "subtitles_enabled": True,
        "ui_scale": 1.0,
        "view_overrides": {},
    },
    "input_map": {
        "bindings": {
            "viewer.advance": {
                "label": "Advance / Continue",
                "primary": "Space",
                "secondary": "Right",
                "gamepad": "button_a",
                "category": "viewer",
            },
            "viewer.back": {
                "label": "Backlog / Previous",
                "primary": "Backspace",
                "secondary": "Left",
                "gamepad": "button_b",
                "category": "viewer",
            },
            "viewer.skip": {
                "label": "Toggle Skip",
                "primary": "Ctrl+F",
                "secondary": None,
                "gamepad": "button_x",
                "category": "viewer",
            },
            "viewer.menu": {
                "label": "Viewer Menu",
                "primary": "Escape",
                "secondary": None,
                "gamepad": "button_start",
                "category": "viewer",
            },
            "viewer.overlays_toggle": {
                "label": "Toggle Overlays",
                "primary": "V",
                "secondary": None,
                "gamepad": "button_y",
                "category": "viewer",
            },
            "viewer.narrator_toggle": {
                "label": "Narrator Toggle",
                "primary": "N",
                "secondary": None,
                "gamepad": "button_select",
                "category": "viewer",
            },
            "editor.pick_winner": {
                "label": "Pick Winner (Editor)",
                "primary": "P",
                "secondary": None,
                "gamepad": "button_r1",
                "category": "editor",
            },
            "viewer.choice_1": {
                "label": "Choice 1",
                "primary": "1",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_2": {
                "label": "Choice 2",
                "primary": "2",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_3": {
                "label": "Choice 3",
                "primary": "3",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_4": {
                "label": "Choice 4",
                "primary": "4",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_5": {
                "label": "Choice 5",
                "primary": "5",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_6": {
                "label": "Choice 6",
                "primary": "6",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_7": {
                "label": "Choice 7",
                "primary": "7",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_8": {
                "label": "Choice 8",
                "primary": "8",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
            "viewer.choice_9": {
                "label": "Choice 9",
                "primary": "9",
                "secondary": None,
                "gamepad": None,
                "category": "viewer",
            },
        }
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
