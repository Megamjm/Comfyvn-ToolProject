from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping

# Theme templates describe LUTs, music, prompt styles and environment assets.
# Values are intentionally lightweight so server responses stay fast without
# requiring asset lookups or heavy joins.

TEMPLATES: dict[str, dict[str, Any]] = {
    "Modern": {
        "luts": ["neutral", "film-soft"],
        "music": {"set": "lofi", "mood": "calm", "intensity": 0.35},
        "prompt": {"style": "clean city", "lighting": "urban ambient"},
        "assets": {
            "backdrop": "city/skyline_evening",
            "ambient_sfx": ["city.traffic.soft", "city.cafe.murmur"],
            "weather": "clear",
        },
        "character": {
            "default": {"palette": "cool", "rim_light": "teal"},
            "roles": {
                "protagonist": {"palette": "neutral", "accent": "cyan"},
                "antagonist": {"palette": "cool", "accent": "violet"},
            },
        },
    },
    "Fantasy": {
        "luts": ["warm", "storybook"],
        "music": {"set": "orchestral", "mood": "adventurous", "intensity": 0.55},
        "prompt": {"style": "medieval tavern", "lighting": "fireplace glow"},
        "assets": {
            "backdrop": "fantasy/forest_grove",
            "ambient_sfx": ["forest.fireflies", "tavern.hub"],
            "weather": "gentle_fog",
        },
        "character": {
            "default": {"palette": "warm", "rim_light": "amber"},
            "roles": {
                "protagonist": {"accent": "gold"},
                "mystic": {"palette": "cool", "accent": "arcane_blue"},
            },
        },
    },
    "Romantic": {
        "luts": ["soft", "rose-blush"],
        "music": {"set": "acoustic", "mood": "intimate", "intensity": 0.42},
        "prompt": {"style": "evening lounge", "lighting": "golden hour"},
        "assets": {
            "backdrop": "romance/rooftop_twilight",
            "ambient_sfx": ["city.rain.soft", "chimes.wind"],
            "weather": "light_rain",
        },
        "character": {
            "default": {"palette": "warm", "rim_light": "rose"},
            "roles": {
                "protagonist": {"accent": "soft_gold"},
                "love-interest": {"accent": "rose_quartz"},
            },
        },
    },
    "Dark": {
        "luts": ["cool", "noir-high-contrast"],
        "music": {"set": "drone", "mood": "ominous", "intensity": 0.6},
        "prompt": {"style": "noir shadows", "lighting": "streetlamp stark"},
        "assets": {
            "backdrop": "noir/alley_midnight",
            "ambient_sfx": ["rain.gutter", "neon.buzz"],
            "weather": "downpour",
        },
        "character": {
            "default": {"palette": "cool", "rim_light": "white"},
            "roles": {
                "protagonist": {"accent": "silver"},
                "antagonist": {"accent": "scarlet"},
                "detective": {"accent": "steel_blue"},
            },
        },
    },
    "Action": {
        "luts": ["vibrant", "cinematic-pop"],
        "music": {"set": "hybrid", "mood": "driving", "intensity": 0.75},
        "prompt": {"style": "high stakes", "lighting": "contrast punch"},
        "assets": {
            "backdrop": "action/highway_chase",
            "ambient_sfx": ["helicopter.distant", "sirens.loop"],
            "weather": "clear",
        },
        "character": {
            "default": {"palette": "neutral", "rim_light": "white_hot"},
            "roles": {
                "protagonist": {"accent": "electric_blue"},
                "support": {"accent": "amber"},
                "antagonist": {"palette": "cool", "accent": "crimson"},
            },
        },
    },
}

_THEME_ALIASES: dict[str, str] = {
    "modern": "Modern",
    "fantasy": "Fantasy",
    "romance": "Romantic",
    "romantic": "Romantic",
    "dark": "Dark",
    "noir": "Dark",
    "action": "Action",
    "modern-a": "Modern",
    "modern_b": "Modern",
    "romantic-a": "Romantic",
    "romantic_b": "Romantic",
}


def available_templates() -> list[str]:
    """Return template names in lexical order."""
    return sorted(TEMPLATES.keys())


def plan(
    theme: str,
    scene: Mapping[str, Any] | None = None,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compose a deterministic plan delta for the requested theme.

    The payload merges template defaults with optional scene state plus explicit
    overrides. Lists and dictionaries are sorted for stable previews so the GUI
    can diff responses without rendering the world.
    """

    template_name = _canonical_theme(theme)
    template = deepcopy(TEMPLATES[template_name])
    scene_state = dict(scene or {})
    scene_theme_state = _to_dict(
        scene_state.get("theme") or scene_state.get("theme_state")
    )
    character_overrides = _extract_character_overrides(overrides, scene_state)
    characters = _normalise_characters(scene_state.get("characters"))

    assets_after = _sorted_dict(template.get("assets", {}))
    luts_after = list(template.get("luts", []))
    music_after = _sorted_dict(template.get("music", {}))
    prompt_after = _sorted_dict(template.get("prompt", {}))

    assets_before = _sorted_dict(_to_dict(scene_theme_state.get("assets")))
    luts_before = _normalise_list(scene_theme_state.get("luts"))
    music_before = _sorted_dict(_to_dict(scene_theme_state.get("music")))
    prompt_before = _sorted_dict(_to_dict(scene_theme_state.get("prompt")))

    delta_characters = _compose_character_deltas(
        characters,
        template.get("character", {}),
        character_overrides,
    )

    mutations = {
        "assets": _compose_delta(assets_before, assets_after),
        "luts": _compose_delta(luts_before, luts_after),
        "music": _compose_delta(music_before, music_after),
        "prompt": _compose_delta(prompt_before, prompt_after),
        "characters": delta_characters,
    }

    plan_payload = {
        "theme": template_name,
        "scene_id": _scene_identifier(scene_state),
        "world_id": _world_identifier(scene_state),
        "mutations": mutations,
    }

    plan_payload["checksum"] = _stable_checksum(plan_payload)
    return plan_payload


def _compose_delta(before: Any, after: Any) -> dict[str, Any]:
    changed = before != after
    delta = {"before": before, "after": after, "changed": changed}
    if isinstance(after, list):
        delta["after"] = list(after)
    if isinstance(before, list):
        delta["before"] = list(before)
    return delta


def _compose_character_deltas(
    characters: list[dict[str, Any]],
    template_character: Mapping[str, Any],
    overrides: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    default_payload = _sorted_dict(_to_dict(template_character.get("default")))
    role_payloads = {
        str(key): _sorted_dict(_to_dict(value))
        for key, value in _to_dict(template_character.get("roles")).items()
    }

    deltas: list[dict[str, Any]] = []
    for character in characters:
        character_id = character["id"]
        before = _sorted_dict(_to_dict(character.get("theme")))

        merged = dict(default_payload)
        for role in character.get("roles", []):
            role_payload = role_payloads.get(role)
            if role_payload:
                merged.update(role_payload)
        override_payload = overrides.get(character_id)
        if override_payload:
            merged.update(_sorted_dict(_to_dict(override_payload)))

        after = _sorted_dict(merged)
        deltas.append(
            {
                "id": character_id,
                "display_name": character.get("display_name"),
                "before": before,
                "after": after,
                "changed": before != after,
            }
        )
    return deltas


def _canonical_theme(theme: str) -> str:
    if not theme:
        raise KeyError("Theme name is required")
    key = str(theme).strip().lower()
    resolved = _THEME_ALIASES.get(key)
    if resolved:
        return resolved
    normalised = key.replace("-", " ").replace("_", " ").title().replace(" ", "")
    if normalised in TEMPLATES:
        return normalised
    key_title = key.title()
    if key_title in TEMPLATES:
        return key_title
    raise KeyError(f"Unknown theme '{theme}'")


def _scene_identifier(scene: Mapping[str, Any]) -> str:
    for key in ("scene_id", "id", "slug", "name"):
        value = scene.get(key)
        if value:
            return str(value)
    return "scene"


def _world_identifier(scene: Mapping[str, Any]) -> str:
    world = scene.get("world") or scene.get("world_state")
    if isinstance(world, Mapping):
        for key in ("id", "world_id", "slug", "name"):
            value = world.get(key)
            if value:
                return str(value)
    for key in ("world_id", "world"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "world"


def _normalise_characters(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    characters: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        value = value.values()
    if not isinstance(value, Iterable):
        return []
    for entry in value:
        if not isinstance(entry, Mapping):
            continue
        character_id = entry.get("id") or entry.get("character_id") or entry.get("name")
        if not character_id:
            continue
        character_id = str(character_id)
        display_name = entry.get("display_name") or entry.get("name") or character_id
        roles = _normalise_list(entry.get("roles") or entry.get("tags") or [])
        theme_state = _sorted_dict(_to_dict(entry.get("theme")))
        characters.append(
            {
                "id": character_id,
                "display_name": str(display_name),
                "roles": roles,
                "theme": theme_state,
            }
        )
    characters.sort(key=lambda item: item["id"])
    return characters


def _extract_character_overrides(
    overrides: Mapping[str, Any] | None,
    scene_state: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    source = overrides or scene_state.get("overrides") or {}
    candidates = source.get("characters") if isinstance(source, Mapping) else None
    if candidates is None and isinstance(source, Mapping):
        candidates = {
            key: value for key, value in source.items() if isinstance(value, Mapping)
        }
    result: dict[str, Mapping[str, Any]] = {}
    if isinstance(candidates, Mapping):
        for key, value in candidates.items():
            if not isinstance(value, Mapping):
                continue
            result[str(key)] = _sorted_dict(_to_dict(value))
    return result


def _normalise_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result = [item for item in value]
    else:
        result = [value]
    try:
        return sorted(result, key=lambda item: json.dumps(item, sort_keys=True))
    except TypeError:
        return result


def _to_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _sorted_dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {key: value[key] for key in sorted(value)}


def _stable_checksum(payload: Mapping[str, Any]) -> str:
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialised.encode("utf-8")).hexdigest()


__all__ = ["TEMPLATES", "available_templates", "plan"]
