from __future__ import annotations

# comfyvn/core/settings_manager.py
# [COMFYVN Architect | v0.8.3s2 | this chat]
import copy
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from pydantic import BaseModel, Field

try:  # Pydantic v2
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - compatibility with pydantic<2
    ConfigDict = None  # type: ignore[assignment]

from comfyvn.config.baseurl_authority import default_base_url
from comfyvn.config.runtime_paths import settings_file
from comfyvn.core.db_manager import DEFAULT_DB_PATH, DBManager

try:
    from PySide6.QtGui import QAction  # type: ignore  # pragma: no cover
except Exception:  # pragma: no cover - optional dependency
    QAction = None  # type: ignore

DEFAULTS = {
    "ack_disclaimer_v1": False,
    "advisory_ack": {
        "user": None,
        "timestamp": None,
        "notes": [],
        "version": "v1",
    },
    "developer": {"verbose": True, "toasts": True, "file_only": False},
    "ui": {"menu_sort_mode": "load_order"},
    "server": {"local_port": 8001},
    "features": {
        "silly_compat_offload": False,
    },
    "compute": {
        "gpu_policy": {
            "mode": "auto",
            "preferred_id": None,
            "manual_device": "cpu",
            "sticky_device": None,
            "last_selected": None,
        }
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
            "default_lang": "en",
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


def _default_section(key: str) -> dict[str, Any]:
    return copy.deepcopy(DEFAULTS.get(key, {}))


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="python", deep=True)  # type: ignore[call-arg]
    return model.dict()  # type: ignore[call-arg]


def _model_validate(payload: Mapping[str, Any] | BaseModel) -> "SettingsModel":
    if isinstance(payload, SettingsModel):
        return payload
    if hasattr(SettingsModel, "model_validate"):
        return SettingsModel.model_validate(payload)  # type: ignore[call-arg]
    return SettingsModel.parse_obj(payload)  # type: ignore[call-arg]


def _model_schema() -> dict[str, Any]:
    if hasattr(SettingsModel, "model_json_schema"):
        return SettingsModel.model_json_schema()  # type: ignore[call-arg]
    return SettingsModel.schema()  # type: ignore[call-arg]


def _deep_merge(
    base: MutableMapping[str, Any], updates: Mapping[str, Any]
) -> MutableMapping[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            base[key] = _deep_merge(base[key], value)  # type: ignore[index]
        else:
            base[key] = copy.deepcopy(value)
    return base


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class SettingsModel(BaseModel):
    ack_disclaimer_v1: bool = Field(
        default_factory=lambda: bool(DEFAULTS.get("ack_disclaimer_v1", False))
    )
    advisory_ack: dict[str, Any] = Field(
        default_factory=lambda: _default_section("advisory_ack")
    )
    developer: dict[str, Any] = Field(
        default_factory=lambda: _default_section("developer")
    )
    ui: dict[str, Any] = Field(default_factory=lambda: _default_section("ui"))
    server: dict[str, Any] = Field(default_factory=lambda: _default_section("server"))
    features: dict[str, Any] = Field(
        default_factory=lambda: _default_section("features")
    )
    compute: dict[str, Any] = Field(default_factory=lambda: _default_section("compute"))
    integrations: dict[str, Any] = Field(
        default_factory=lambda: _default_section("integrations")
    )
    policy: dict[str, Any] = Field(default_factory=lambda: _default_section("policy"))
    accessibility: dict[str, Any] = Field(
        default_factory=lambda: _default_section("accessibility")
    )
    input_map: dict[str, Any] = Field(
        default_factory=lambda: _default_section("input_map")
    )
    filters: dict[str, Any] = Field(default_factory=lambda: _default_section("filters"))
    audio: dict[str, Any] = Field(default_factory=lambda: _default_section("audio"))

    if ConfigDict is not None:  # pragma: no branch - depends on pydantic version
        model_config = ConfigDict(extra="allow")  # type: ignore[assignment]
    else:  # pragma: no cover - pydantic v1 fallback

        class Config:
            extra = "allow"


class SettingsManager:
    def __init__(
        self,
        path: str | Path | None = None,
        db_path: str | Path | None = None,
    ):
        self.path = (
            Path(path) if path is not None else Path(settings_file("config.json"))
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path is not None else Path(DEFAULT_DB_PATH)
        self._db_manager = DBManager(self.db_path)
        self._db_manager.ensure_schema()
        self._cached_payload: dict[str, Any] | None = None
        model = self._merge_sources()
        self._persist(model)

    def _merge_sources(self) -> SettingsModel:
        base = _model_dump(SettingsModel())
        file_payload = _load_json(self.path)
        db_payload = self._load_db()
        merged = _deep_merge(copy.deepcopy(base), file_payload)
        merged = _deep_merge(merged, db_payload)
        return SettingsModel(**merged)

    def _load_db(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
            for key, raw in rows:
                if raw is None:
                    continue
                try:
                    result[str(key)] = json.loads(raw)
                except Exception:
                    continue
        return result

    def _write_db(self, payload: Mapping[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM settings")
            for key, value in payload.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO settings (key, value_json)
                    VALUES (?, ?)
                    """,
                    (key, json.dumps(value)),
                )
            conn.commit()

    def _write_file(self, payload: Mapping[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _persist(self, model: SettingsModel) -> None:
        payload = _model_dump(model)
        if self._cached_payload == payload:
            return
        self._write_file(payload)
        self._write_db(payload)
        self._cached_payload = copy.deepcopy(payload)

    def load_model(self) -> SettingsModel:
        model = self._merge_sources()
        self._persist(model)
        return model

    def load(self) -> dict[str, Any]:
        return _model_dump(self.load_model())

    def save(self, data: Mapping[str, Any] | BaseModel) -> dict[str, Any]:
        model = _model_validate(data)
        self._persist(model)  # type: ignore[arg-type]
        return _model_dump(model)  # type: ignore[arg-type]

    def get(self, key: str, default: Any | None = None) -> Any:
        return self.load().get(key, default)

    def patch(self, key: str, value: Any) -> dict[str, Any]:
        current = self.load()
        current[key] = value
        return self.save(current)

    def merge(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        current = self.load()
        merged = _deep_merge(copy.deepcopy(current), updates)
        return self.save(merged)

    def defaults(self) -> dict[str, Any]:
        return _model_dump(SettingsModel())

    def schema(self) -> dict[str, Any]:
        return _model_schema()
