from __future__ import annotations
from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/modules/audio_manager.py
# 🔊 Audio & Effects Production Chat — Harmonized Full Version
# [ComfyVN Chat 6 Integration Build | Phase 3.8]
# Compatible with: SceneManager, UIManager, SystemCore, ScriptParser
# Last sync: 2025-10-12

import os, json
from pathlib import Path
from typing import Optional, Dict, Literal, Tuple

AudioKey = Literal["sound", "music", "voice", "ambience", "fx"]
Category = Literal["music", "ambience", "voice", "fx"]


class AudioManager:
    """Handles playback, toggles, and persistence for ComfyVN audio layers."""

    def __init__(self, data_root: str | Path = "data", autosave: bool = True):
        self.autosave = autosave
        self.data_root = Path(data_root)
        self.audio_root = self.data_root / "audio"
        self.config_path = self.data_root / "config" / "audio_settings.json"
        self.log_callback = None  # linked by SystemCore
        self.notify_callback = None  # linked by UI

        # Toggles and defaults
        self.media_settings: Dict[AudioKey, bool] = {
            "sound": True,
            "music": True,
            "voice": False,
            "ambience": True,
            "fx": True,
        }

        self.volumes: Dict[Category, float] = {
            "music": 1.0,
            "ambience": 1.0,
            "voice": 1.0,
            "fx": 1.0,
        }
        self.master_volume: float = 1.0

        # Track current states
        self.current_tracks = {
            "music": None,
            "ambience": None,
            "voice": None,
            "fx": None,
        }

        # Directories
        (self.data_root / "config").mkdir(parents=True, exist_ok=True)
        for sub in ("music", "ambience", "voice", "fx"):
            (self.audio_root / sub).mkdir(parents=True, exist_ok=True)

        # Load persisted settings
        self.load_settings()

        # Detect playback backend
        self.backend, self.backend_info = self._detect_backend()
        self.log(f"Audio backend: {self.backend_info}")

        # Initialize backend
        self._pygame = None
        self._pygame_channels = {"ambience": None, "voice": None, "fx": None}
        self._init_backend()

    # ------------------------------------------------------------
    # Core Utility Wrappers
    # ------------------------------------------------------------
    def log(self, message: str):
        """Unified log handler; forwards to SystemCore if linked."""
        if self.log_callback:
            self.log_callback(f"[Audio] {message}")
        else:
            print(f"[Audio] {message}")

    def _notify(self, message: str, fx: Optional[str] = None):
        """UI callback notifier (e.g., sound cues or popup triggers)."""
        if self.notify_callback:
            self.notify_callback(message)
        if fx:
            self.play_fx(fx)

    # ------------------------------------------------------------
    # Backend Setup
    # ------------------------------------------------------------
    def _detect_backend(self) -> Tuple[str, str]:
        try:
            import pygame  # type: ignore

            return "pygame", "PyGame mixer backend"
        except Exception:
            pass
        try:
            import renpy  # type: ignore

            return "renpy", "Ren'Py runtime backend"
        except Exception:
            pass
        return "noop", "No-op (logging only)"

    def _init_backend(self):
        if self.backend == "pygame":
            import pygame

            self._pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            total = max(pygame.mixer.get_num_channels(), 16)
            pygame.mixer.set_num_channels(total)
            self._pygame_channels["ambience"] = pygame.mixer.Channel(1)
            self._pygame_channels["voice"] = pygame.mixer.Channel(2)
            self._pygame_channels["fx"] = pygame.mixer.Channel(3)
        # No-op or Ren'Py need no manual init

    # ------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------
    def save_settings(self):
        payload = {
            "media_settings": self.media_settings,
            "volumes": self.volumes,
            "master_volume": self.master_volume,
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self.log("Settings saved.")
        except Exception as e:
            self.log(f"[WARN] Failed to save settings: {e}")

    def load_settings(self):
        if not self.config_path.exists():
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self.media_settings.update(payload.get("media_settings", {}))
            self.volumes.update(payload.get("volumes", {}))
            self.master_volume = float(payload.get("master_volume", 1.0))
            self.log("Settings loaded.")
        except Exception as e:
            self.log(f"[WARN] Failed to load settings: {e}")

    def get_settings(self):
        return {
            "media_settings": self.media_settings,
            "volumes": self.volumes,
            "master_volume": self.master_volume,
            "backend": self.backend,
        }

    # ------------------------------------------------------------
    # Toggles & Volume
    # ------------------------------------------------------------
    def toggle(self, key: AudioKey, state: bool):
        if key in self.media_settings:
            if self.media_settings.get(key) == state:
                return
            self.media_settings[key] = state
            self.log(f"{key} set to {state}")
            if self.autosave:
                self.save_settings()
            self._notify(
                f"Audio toggled: {key} {'ON' if state else 'OFF'}", fx="toggle"
            )

    def is_enabled(self, key: AudioKey) -> bool:
        """Return the current toggle state for a media channel."""
        return bool(self.media_settings.get(key, False))

    def set_music_enabled(self, enabled: bool):
        """Explicit toggle helper for music with optional fade-out."""
        was_enabled = self.is_enabled("music")
        self.toggle("music", enabled)
        if was_enabled and not enabled:
            self.stop_music()

    def set_voice_enabled(self, enabled: bool):
        """Enable or disable voice playback; stops active voice when turning off."""
        was_enabled = self.is_enabled("voice")
        self.toggle("voice", enabled)
        if was_enabled and not enabled:
            if self.backend == "pygame":
                try:
                    channel = self._pygame_channels.get("voice")
                    if channel:
                        channel.stop()
                except Exception as e:
                    self.log(f"[ERR] Stop voice: {e}")
            self.current_tracks["voice"] = None

    def set_sfx_enabled(self, enabled: bool):
        """Toggle SFX (fx + ui sound cues) as a single control."""
        was_fx = self.is_enabled("fx")
        was_sound = self.is_enabled("sound")
        self.toggle("fx", enabled)
        self.toggle("sound", enabled)
        if (was_fx or was_sound) and not enabled and self.backend == "pygame":
            try:
                channel = self._pygame_channels.get("fx")
                if channel:
                    channel.stop()
            except Exception as e:
                self.log(f"[ERR] Stop sfx: {e}")

    def set_volume(self, category: Category, value: float):
        value = max(0.0, min(1.0, float(value)))
        self.volumes[category] = value
        self.log(f"Volume[{category}] = {value:.2f}")
        if self.autosave:
            self.save_settings()

    # ------------------------------------------------------------
    # Playback utilities
    # ------------------------------------------------------------
    def _path_for(self, category: Category, name: str) -> Path:
        base = self.audio_root / category
        p = Path(name)
        if p.exists():
            return p
        for ext in (".ogg", ".wav", ".mp3", ".flac"):
            c = base / f"{name}{ext}"
            if c.exists():
                return c
        return base / name

    # ------------------------------------------------------------
    # Playback (stubs or pygame)
    # ------------------------------------------------------------
    def play_music(self, track: str, loop: bool = True):
        if not self.media_settings["music"]:
            self.log("Music disabled.")
            return
        path = self._path_for("music", track)
        self.current_tracks["music"] = str(path)
        if self.backend == "pygame":
            try:
                pg = self._pygame
                pg.mixer.music.load(str(path))
                pg.mixer.music.play(-1 if loop else 0)
                pg.mixer.music.set_volume(self.volumes["music"])
                self.log(f"Music playing: {path.name}")
            except Exception as e:
                self.log(f"[ERR] Music: {e}")
        else:
            self.log(f"[noop] play_music({path})")

    def stop_music(self):
        if self.backend == "pygame":
            try:
                self._pygame.mixer.music.fadeout(500)
                self.current_tracks["music"] = None
            except Exception as e:
                self.log(f"[ERR] Stop music: {e}")
        else:
            self.log("[noop] stop_music()")

    def play_fx(self, effect: str):
        """Play short UI or action effects (always allowed)."""
        path = self._path_for("fx", effect)
        self.current_tracks["fx"] = str(path)
        if self.backend == "pygame":
            try:
                snd = self._pygame.mixer.Sound(str(path))
                snd.set_volume(self.volumes["fx"])
                snd.play()
            except Exception as e:
                self.log(f"[ERR] FX: {e}")
        else:
            self.log(f"[noop] play_fx({path})")

    def play_ambience(self, track: str, loop: bool = True):
        if not self.media_settings["ambience"]:
            self.log("Ambience disabled.")
            return
        path = self._path_for("ambience", track)
        self.current_tracks["ambience"] = str(path)
        if self.backend == "pygame":
            try:
                snd = self._pygame.mixer.Sound(str(path))
                ch = self._pygame_channels.get("ambience")
                ch.set_volume(self.volumes["ambience"])
                ch.play(snd, loops=-1 if loop else 0, fade_ms=300)
                self.log(f"Ambience: {path.name}")
            except Exception as e:
                self.log(f"[ERR] Ambience: {e}")
        else:
            self.log(f"[noop] play_ambience({path})")

    def play_voice(self, file_or_id: str, character: Optional[str] = None):
        if not self.media_settings["voice"]:
            self.log("Voice disabled.")
            return
        root = self.audio_root / "voice"
        if character:
            root = root / character
        path = self._path_for("voice", file_or_id)
        if not path.exists() and character:
            path = root / file_or_id
        self.current_tracks["voice"] = str(path)
        if self.backend == "pygame":
            try:
                snd = self._pygame.mixer.Sound(str(path))
                ch = self._pygame_channels.get("voice")
                ch.set_volume(self.volumes["voice"])
                ch.play(snd)
                self.log(f"Voice: {path.name}")
            except Exception as e:
                self.log(f"[ERR] Voice: {e}")
        else:
            self.log(f"[noop] play_voice({path})")

    def stop_all(self):
        if self.backend == "pygame":
            self._pygame.mixer.stop()
        self.log("All audio stopped.")
