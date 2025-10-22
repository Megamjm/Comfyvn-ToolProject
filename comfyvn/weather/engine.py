from __future__ import annotations

"""
Weather plan compiler used by GUI previews and export pipelines.

`compile_plan(state)` consumes a light-weight world state payload and produces
deterministic scene lighting, overlay, and transition directives.  A tiny
in-memory store (`WeatherPlanStore`) keeps track of the latest compiled plan so
API routes can update state without blocking downstream readers.
"""

import copy
import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, MutableMapping, Optional, Tuple

DEFAULT_STATE = {
    "time_of_day": "day",
    "weather": "clear",
    "ambience": "calm",
}

_TIME_ALIASES: Dict[str, str] = {
    "sunrise": "dawn",
    "sunset": "dusk",
    "evening": "dusk",
    "twilight": "dusk",
    "midday": "day",
    "noon": "day",
    "morning": "day",
    "midnight": "night",
    "late_night": "night",
}

_WEATHER_ALIASES: Dict[str, str] = {
    "rainy": "rain",
    "heavy_rain": "storm",
    "stormy": "storm",
    "thunderstorm": "storm",
    "snowy": "snow",
    "blizzard": "snow",
    "cloudy": "overcast",
    "mist": "fog",
    "haze": "fog",
}

_AMBIENCE_ALIASES: Dict[str, str] = {
    "relaxed": "calm",
    "serene": "calm",
    "anxious": "tense",
    "dramatic": "tense",
    "mysterious": "mystic",
    "arcane": "mystic",
    "sad": "melancholic",
    "somber": "melancholic",
    "upbeat": "energetic",
    "lively": "energetic",
}

_TIME_PRESETS: Dict[str, Dict[str, Any]] = {
    "dawn": {
        "key": 0.55,
        "fill": 0.35,
        "rim": 0.4,
        "temperature": 4300,
        "exposure": -0.15,
        "sky_tint": "#fbd4a5",
        "base_background": "backgrounds/dawn_default.png",
    },
    "day": {
        "key": 0.85,
        "fill": 0.55,
        "rim": 0.3,
        "temperature": 5600,
        "exposure": 0.05,
        "sky_tint": "#ffffff",
        "base_background": "backgrounds/day_default.png",
    },
    "dusk": {
        "key": 0.6,
        "fill": 0.4,
        "rim": 0.45,
        "temperature": 3800,
        "exposure": -0.1,
        "sky_tint": "#ffa97a",
        "base_background": "backgrounds/dusk_default.png",
    },
    "night": {
        "key": 0.3,
        "fill": 0.2,
        "rim": 0.6,
        "temperature": 3100,
        "exposure": -0.6,
        "sky_tint": "#6aa2ff",
        "base_background": "backgrounds/night_default.png",
    },
}

_WEATHER_PRESETS: Dict[str, Dict[str, Any]] = {
    "clear": {
        "overlay_id": "clear_sky",
        "overlay_intensity": 0.35,
        "contrast_delta": 0.1,
        "exposure_delta": 0.0,
        "tint": "#ffffff",
        "blend_mode": "screen",
        "sfx": "ambience/wind_soft.ogg",
        "sfx_gain": -8.0,
    },
    "overcast": {
        "overlay_id": "overcast",
        "overlay_intensity": 0.55,
        "contrast_delta": -0.15,
        "exposure_delta": -0.2,
        "tint": "#c9d2e3",
        "blend_mode": "overlay",
        "sfx": "ambience/drizzle_loop.ogg",
        "sfx_gain": -6.5,
    },
    "rain": {
        "overlay_id": "rain",
        "overlay_intensity": 0.65,
        "contrast_delta": -0.25,
        "exposure_delta": -0.35,
        "tint": "#9db2c8",
        "blend_mode": "soft_light",
        "particle": {"type": "rain", "spawn_rate": 240, "size": [0.6, 1.0]},
        "sfx": "ambience/rain_loop.ogg",
        "sfx_gain": -4.0,
    },
    "storm": {
        "overlay_id": "storm",
        "overlay_intensity": 0.8,
        "contrast_delta": -0.35,
        "exposure_delta": -0.45,
        "tint": "#8996b6",
        "blend_mode": "overlay",
        "particle": {
            "type": "rain",
            "spawn_rate": 340,
            "size": [0.8, 1.2],
            "noise": 0.4,
        },
        "sfx": "ambience/thunderstorm_loop.ogg",
        "sfx_gain": -3.0,
        "one_shots": ["ambience/thunder_roll.ogg"],
    },
    "snow": {
        "overlay_id": "snow",
        "overlay_intensity": 0.6,
        "contrast_delta": -0.1,
        "exposure_delta": -0.15,
        "tint": "#e2eef3",
        "blend_mode": "screen",
        "particle": {"type": "snow", "spawn_rate": 160, "size": [0.5, 1.4]},
        "sfx": "ambience/snow_wind.ogg",
        "sfx_gain": -5.5,
    },
    "fog": {
        "overlay_id": "fog",
        "overlay_intensity": 0.58,
        "contrast_delta": -0.3,
        "exposure_delta": -0.25,
        "tint": "#d7dce0",
        "blend_mode": "screen",
        "particle": {"type": "fog", "spawn_rate": 80, "density": 0.5},
        "sfx": "ambience/fog_wind.ogg",
        "sfx_gain": -7.0,
    },
}

_AMBIENCE_PRESETS: Dict[str, Dict[str, Any]] = {
    "calm": {
        "transition_duration": 1.25,
        "sfx_fade": 1.6,
        "overlay_gain": 0.0,
        "exposure_bias": 0.0,
        "particle_gain": 0.0,
    },
    "tense": {
        "transition_duration": 0.9,
        "sfx_fade": 1.0,
        "overlay_gain": 0.08,
        "exposure_bias": -0.05,
        "particle_gain": 0.12,
    },
    "mystic": {
        "transition_duration": 1.45,
        "sfx_fade": 1.9,
        "overlay_gain": 0.05,
        "exposure_bias": -0.02,
        "particle_gain": 0.05,
        "tint": "#bca6ff",
    },
    "energetic": {
        "transition_duration": 0.75,
        "sfx_fade": 0.85,
        "overlay_gain": -0.05,
        "exposure_bias": 0.08,
        "particle_gain": -0.05,
    },
    "melancholic": {
        "transition_duration": 1.6,
        "sfx_fade": 2.1,
        "overlay_gain": 0.03,
        "exposure_bias": -0.08,
        "particle_gain": 0.04,
    },
}


def _canonical_value(
    value: Any,
    *,
    table: Mapping[str, Mapping[str, Any]],
    aliases: Mapping[str, str],
    default: str,
) -> Tuple[str, Optional[str]]:
    original = value
    if isinstance(value, str):
        cleaned = value.strip().lower().replace(" ", "_")
    elif value is None:
        cleaned = ""
    else:
        cleaned = str(value).strip().lower().replace(" ", "_")

    resolved = aliases.get(cleaned, cleaned) if cleaned else default
    warning: Optional[str] = None
    if not resolved or resolved not in table:
        resolved = default
        warning = f"unrecognized value '{original}' (fell back to '{default}')"
    return resolved, warning


def _normalize_state(state: Mapping[str, Any] | None) -> Tuple[dict, list[str]]:
    canonical = dict(DEFAULT_STATE)
    warnings: list[str] = []
    payload = state if isinstance(state, Mapping) else {}

    tod_value = payload.get("time_of_day")
    tod, warn = _canonical_value(
        tod_value, table=_TIME_PRESETS, aliases=_TIME_ALIASES, default="day"
    )
    if warn:
        warnings.append(f"time_of_day: {warn}")
    canonical["time_of_day"] = tod

    weather_value = payload.get("weather")
    weather, warn = _canonical_value(
        weather_value,
        table=_WEATHER_PRESETS,
        aliases=_WEATHER_ALIASES,
        default="clear",
    )
    if warn:
        warnings.append(f"weather: {warn}")
    canonical["weather"] = weather

    ambience_value = payload.get("ambience")
    ambience, warn = _canonical_value(
        ambience_value,
        table=_AMBIENCE_PRESETS,
        aliases=_AMBIENCE_ALIASES,
        default="calm",
    )
    if warn:
        warnings.append(f"ambience: {warn}")
    canonical["ambience"] = ambience

    return canonical, warnings


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _combine_tints(*values: Optional[str]) -> Optional[str]:
    # Keep the first non-empty tint so intentionally supplied overrides win.
    for value in values:
        if value:
            return value
    return None


def _build_light_rig(
    time_cfg: Mapping[str, Any],
    weather_cfg: Mapping[str, Any],
    ambience_cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    rig = {
        "key": _clamp(
            time_cfg["key"] + weather_cfg.get("contrast_delta", 0.0) * 0.25, 0.05, 1.0
        ),
        "fill": _clamp(
            time_cfg["fill"] - weather_cfg.get("contrast_delta", 0.0) * 0.2, 0.05, 1.0
        ),
        "rim": _clamp(
            time_cfg["rim"] + weather_cfg.get("contrast_delta", 0.0) * -0.3, 0.05, 1.0
        ),
        "temperature": int(
            _clamp(
                time_cfg["temperature"] + weather_cfg.get("exposure_delta", 0.0) * -400,
                2500,
                6500,
            )
        ),
    }
    exposure = (
        time_cfg["exposure"]
        + weather_cfg.get("exposure_delta", 0.0)
        + ambience_cfg.get("exposure_bias", 0.0)
    )
    rig["exposure"] = round(_clamp(exposure, -1.0, 0.4), 3)
    rig["contrast"] = round(
        _clamp(1.0 + weather_cfg.get("contrast_delta", 0.0), 0.5, 1.5), 3
    )
    rig["saturation"] = round(
        _clamp(1.0 + weather_cfg.get("contrast_delta", 0.0) * -0.6, 0.4, 1.2), 3
    )
    return rig


def _build_lut(
    state: Mapping[str, str],
    time_cfg: Mapping[str, Any],
    weather_cfg: Mapping[str, Any],
    ambience_cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    intensity = (
        weather_cfg.get("overlay_intensity", 0.5) * 0.6
        + ambience_cfg.get("overlay_gain", 0.0) * 0.3
    )
    intensity = _clamp(intensity, 0.0, 1.0)
    tint = (
        _combine_tints(
            ambience_cfg.get("tint"),
            weather_cfg.get("tint"),
            time_cfg.get("sky_tint"),
        )
        or "#ffffff"
    )
    lut_id = f"{state['time_of_day']}_{state['weather']}"
    return {
        "id": f"lut_{lut_id}",
        "path": f"luts/{lut_id}.cube",
        "tint": tint,
        "intensity": round(intensity, 3),
    }


def _build_overlays(
    state: Mapping[str, str],
    time_cfg: Mapping[str, Any],
    weather_cfg: Mapping[str, Any],
    ambience_cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    overlay_intensity = weather_cfg.get("overlay_intensity", 0.5) + ambience_cfg.get(
        "overlay_gain", 0.0
    )
    overlay = {
        "id": f"{weather_cfg['overlay_id']}_{state['time_of_day']}",
        "role": "weather",
        "texture": f"weather/{weather_cfg['overlay_id']}_{state['time_of_day']}.png",
        "intensity": round(_clamp(overlay_intensity, 0.0, 1.0), 3),
        "blend": weather_cfg.get("blend_mode", "overlay"),
    }
    tint = _combine_tints(
        weather_cfg.get("tint"),
        ambience_cfg.get("tint"),
        time_cfg.get("sky_tint"),
    )
    if tint:
        overlay["tint"] = tint

    base_layer = {
        "id": f"base_{state['time_of_day']}",
        "role": "base",
        "texture": time_cfg["base_background"],
        "intensity": 1.0,
        "tint": time_cfg.get("sky_tint"),
    }

    layers = [base_layer, overlay]

    if weather_cfg["overlay_id"] in {"fog", "storm"}:
        mask_texture = f"weather/{weather_cfg['overlay_id']}_depth.png"
        layers.append(
            {
                "id": f"{weather_cfg['overlay_id']}_depth",
                "role": "depth_mask",
                "texture": mask_texture,
                "intensity": round(_clamp(overlay["intensity"] * 0.6, 0.05, 0.9), 3),
                "blend": "multiply",
            }
        )

    return {
        "layers": layers,
        "summary": {
            "background": base_layer["texture"],
            "overlay": overlay["texture"],
        },
    }


def _build_transition(
    weather_cfg: Mapping[str, Any],
    ambience_cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    duration = _clamp(ambience_cfg.get("transition_duration", 1.2), 0.4, 2.5)
    exposure_shift = weather_cfg.get("exposure_delta", 0.0) + ambience_cfg.get(
        "exposure_bias", 0.0
    )
    return {
        "type": "crossfade",
        "duration": round(duration, 3),
        "ease": "easeInOutQuad",
        "exposure_shift": round(_clamp(exposure_shift, -1.0, 0.5), 3),
        "sfx_fade": round(_clamp(ambience_cfg.get("sfx_fade", 1.5), 0.3, 3.0), 3),
        "particle_fade": round(_clamp(duration * 0.6, 0.2, 1.8), 3),
    }


def _build_particles(
    weather_cfg: Mapping[str, Any],
    ambience_cfg: Mapping[str, Any],
    state: Mapping[str, str],
) -> Optional[Dict[str, Any]]:
    particle_cfg = weather_cfg.get("particle")
    if not particle_cfg:
        return None
    payload = dict(particle_cfg)
    intensity = particle_cfg.get("intensity", 0.6)
    intensity += ambience_cfg.get("particle_gain", 0.0)
    payload["intensity"] = round(_clamp(intensity, 0.0, 1.0), 3)
    payload["emitter"] = f"{state['weather']}_{state['time_of_day']}"
    return payload


def _build_sfx(
    weather_cfg: Mapping[str, Any],
    ambience_cfg: Mapping[str, Any],
    state: Mapping[str, str],
) -> Dict[str, Any]:
    gain = (
        weather_cfg.get("sfx_gain", -6.0) + ambience_cfg.get("overlay_gain", 0.0) * -4
    )
    fade_value = round(_clamp(ambience_cfg.get("sfx_fade", 1.5), 0.3, 3.0), 3)
    payload = {
        "loop": weather_cfg.get("sfx"),
        "gain_db": round(_clamp(gain, -18.0, 6.0), 3),
        "tags": [state["weather"], state["ambience"], state["time_of_day"]],
        "fade": fade_value,
        "fade_in": fade_value,
        "fade_out": round(_clamp(fade_value * 1.1, 0.4, 3.5), 3),
    }
    if weather_cfg.get("one_shots"):
        payload["one_shots"] = list(weather_cfg["one_shots"])
    return payload


def _plan_hash(state: Mapping[str, Any]) -> str:
    serialized = json.dumps(state, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(serialized.encode("utf-8")).hexdigest()
    return digest[:12]


def compile_plan(state: Mapping[str, Any] | None) -> Dict[str, Any]:
    """
    Compile the supplied weather state into deterministic presentation data.

    Returns a dictionary consumable by scene exporters and previews:

    {
        "state": {...},
        "scene": {"background_layers": [...], "light_rig": {...}},
        "transition": {...},
        "particles": {...}|None,
        "sfx": {...},
        "meta": {"hash": "...", "warnings": [...]}
    }
    """

    canonical, warnings = _normalize_state(state)
    time_cfg = _TIME_PRESETS[canonical["time_of_day"]]
    weather_cfg = _WEATHER_PRESETS[canonical["weather"]]
    ambience_cfg = _AMBIENCE_PRESETS[canonical["ambience"]]

    overlays = _build_overlays(canonical, time_cfg, weather_cfg, ambience_cfg)
    light_rig = _build_light_rig(time_cfg, weather_cfg, ambience_cfg)
    lut = _build_lut(canonical, time_cfg, weather_cfg, ambience_cfg)
    transition = _build_transition(weather_cfg, ambience_cfg)
    particles = _build_particles(weather_cfg, ambience_cfg, canonical)
    sfx = _build_sfx(weather_cfg, ambience_cfg, canonical)
    overlays["summary"]["lut"] = lut["path"]

    plan = {
        "state": canonical,
        "scene": {
            "background_layers": overlays["layers"],
            "light_rig": light_rig,
            "lut": lut,
            "bake_ready": True,
            "summary": overlays["summary"],
        },
        "transition": transition,
        "particles": particles,
        "sfx": sfx,
        "meta": {
            "hash": _plan_hash(canonical),
            "warnings": warnings,
            "flags": {"bake_background": True},
        },
    }
    return plan


@dataclass
class WeatherPlanStore:
    """Thread-safe store for the most recently compiled weather plan."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _plan: Dict[str, Any] = field(default=None)  # type: ignore[assignment]
    _version: int = 0

    def __post_init__(self) -> None:
        if self._plan is None:
            initial = compile_plan(DEFAULT_STATE)
            meta = dict(initial.get("meta", {}))
            meta["version"] = 0
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            initial["meta"] = meta
            self._plan = initial

    def update(self, state: Mapping[str, Any] | None) -> Dict[str, Any]:
        plan = compile_plan(state)
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._version += 1
            meta = dict(plan.get("meta", {}))
            meta["version"] = self._version
            meta["updated_at"] = timestamp
            plan["meta"] = meta
            self._plan = plan
            return copy.deepcopy(self._plan)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._plan)

    def clear(self) -> None:
        """Reset to defaults. Mainly used by tests."""
        with self._lock:
            baseline = compile_plan(DEFAULT_STATE)
            meta = dict(baseline.get("meta", {}))
            meta["version"] = 0
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            baseline["meta"] = meta
            self._plan = baseline
            self._version = 0


__all__ = [
    "DEFAULT_STATE",
    "WeatherPlanStore",
    "compile_plan",
]
