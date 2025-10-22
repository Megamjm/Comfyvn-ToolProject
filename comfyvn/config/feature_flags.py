from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

FEATURE_DEFAULTS: Dict[str, bool] = {
    "enable_comfy_bridge_hardening": False,
    "enable_comfy_preview_stream": False,
    "enable_sillytavern_bridge": False,
    "enable_st_importer": False,
    "enable_narrator_mode": False,
    "enable_narrator": False,
    "enable_llm_role_mapping": False,
    "enable_playtest_harness": False,
    "enable_remote_installer": False,
    "enable_extension_market": False,
    "enable_extension_market_uploads": False,
    "enable_policy_enforcer": True,
    "enable_blocking_assistant": False,
    "enable_public_gpu": False,
    "enable_public_image_video": False,
    "enable_public_image_providers": False,
    "enable_public_video_providers": False,
    "enable_public_translate": False,
    "enable_public_llm": False,
    "enable_observability": False,
    "debug_health_checks": False,
    "enable_privacy_telemetry": False,  # legacy alias kept for backward compatibility
    "enable_audio_lab": False,
    "enable_crash_uploader": False,
    "enable_cloud_sync": False,
    "enable_cloud_sync_s3": False,
    "enable_cloud_sync_gdrive": False,
    "enable_export_publish": False,
    "enable_export_publish_steam": False,
    "enable_export_publish_itch": False,
    "enable_weather_planner": True,
    "enable_weather_overlays": False,
    "enable_weather": True,
    "enable_battle": True,
    "enable_battle_sim": False,
    "enable_props": False,
    "enable_themes": False,
    "enable_anim_25d": False,
    "enable_security_api": False,
    "enable_security_sandbox_guard": True,
    "enable_collaboration": True,
    "enable_accessibility": False,
    "enable_accessibility_controls": True,
    "enable_accessibility_api": True,
    "enable_controller_profiles": True,
    "enable_snapshot_sheets": False,
    "enable_perf": False,  # umbrella flag for budgets/profiler
    "enable_perf_budgets": False,
    "enable_perf_profiler_dashboard": False,
    "enable_quick_toolbar": False,
    "enable_rating_api": True,
    "enable_rating_modder_stream": False,
    "enable_diffmerge_tools": False,
}

_CACHE: Dict[str, bool] | None = None
_CACHE_SIGNATURE: tuple[float, float] | None = None


def _candidate_paths() -> tuple[Path, Path]:
    return (Path("comfyvn.json"), Path("config/comfyvn.json"))


def _signature() -> tuple[float, float]:
    values: list[float] = []
    for path in _candidate_paths():
        try:
            values.append(path.stat().st_mtime)
        except FileNotFoundError:
            values.append(0.0)
    return (values[0], values[1])


def _read_features(path: Path) -> Dict[str, bool]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    data = raw.get("features")
    if not isinstance(data, dict):
        return {}
    result: Dict[str, bool] = {}
    for key, value in data.items():
        if isinstance(value, bool):
            result[key] = value
    return result


def load_feature_flags(*, refresh: bool = False) -> Dict[str, bool]:
    global _CACHE, _CACHE_SIGNATURE
    signature = _signature()
    if not refresh and _CACHE is not None and signature == _CACHE_SIGNATURE:
        return dict(_CACHE)

    flags: Dict[str, bool] = dict(FEATURE_DEFAULTS)
    for path in _candidate_paths():
        if not path.exists():
            continue
        flags.update(_read_features(path))

    _CACHE = flags
    _CACHE_SIGNATURE = signature
    return dict(flags)


def is_enabled(
    name: str, *, default: bool | None = None, refresh: bool = False
) -> bool:
    flags = load_feature_flags(refresh=refresh)
    if name in flags:
        return bool(flags[name])
    if default is not None:
        return bool(default)
    return False


def refresh_cache() -> Dict[str, bool]:
    return load_feature_flags(refresh=True)


__all__ = ["FEATURE_DEFAULTS", "is_enabled", "load_feature_flags", "refresh_cache"]
