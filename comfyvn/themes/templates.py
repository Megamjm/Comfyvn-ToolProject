from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence


def _unique_list(items: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _merge_lists(base: Sequence[Any], extension: Sequence[Any]) -> list[Any]:
    base_list = [item for item in base]
    ext_list = [item for item in extension]
    return _unique_list(base_list + ext_list)


def _merge_nested(
    base: Mapping[str, Any], overlay: Mapping[str, Any]
) -> dict[str, Any]:
    result = {key: deepcopy(value) for key, value in base.items()}
    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(value, Mapping) and isinstance(existing, Mapping):
            result[key] = _merge_nested(existing, value)
        elif isinstance(value, (list, tuple, set)) and not isinstance(
            value, (str, bytes)
        ):
            updates = [item for item in value]
            if isinstance(existing, list):
                result[key] = _merge_lists(existing, updates)
            else:
                result[key] = _unique_list(updates)
        else:
            result[key] = deepcopy(value)
    return result


def _make_accessibility_variants(
    *,
    highlight_overlay: str | None = None,
    color_blind_palette: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = {
        "base": {
            "name": "base",
            "label": "Studio Default",
            "description": "Original grading, palette, and props.",
            "overrides": {},
        },
        "high_contrast": {
            "name": "high_contrast",
            "label": "High Contrast",
            "description": "Boosted contrast with highlight-safe grading and anchor halos.",
            "overrides": {
                "luts": ["accessibility/high_contrast"],
                "camera": {
                    "exposure": "protect_highlights",
                    "tone_mapping": "filmic_hc",
                },
                "props": {
                    "ui": ["ui/anchors/highlight_glow"],
                },
                "style_tags": ["accessibility_high_contrast"],
            },
        },
        "color_blind": {
            "name": "color_blind",
            "label": "Color Blind Safe",
            "description": "Daltonize overlay and palette nudges that avoid red/green collisions.",
            "overrides": {
                "luts": ["accessibility/daltonize"],
                "palette": {
                    "accent": "#FFD166",
                    "neutral": "#073B4C",
                },
                "style_tags": ["accessibility_color_blind"],
            },
        },
    }

    if highlight_overlay:
        base["high_contrast"]["overrides"] = _merge_nested(
            base["high_contrast"]["overrides"],
            {"props": {"ui": [highlight_overlay]}},
        )
    if color_blind_palette:
        base["color_blind"]["overrides"] = _merge_nested(
            base["color_blind"]["overrides"],
            {"palette": dict(color_blind_palette)},
        )
    return base


def _theme_payload(
    *,
    label: str,
    summary: str,
    style_tags: Iterable[str],
    tag_remaps: Mapping[str, str],
    kit: Mapping[str, Any],
    subtypes: Mapping[str, Mapping[str, Any]],
    default_subtype: str,
    highlight_overlay: str,
    color_blind_palette: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "label": label,
        "summary": summary,
        "style_tags": list(style_tags),
        "tag_remaps": dict(tag_remaps),
        "kit": deepcopy(kit),
        "subtypes": deepcopy(subtypes),
        "accessibility": _make_accessibility_variants(
            highlight_overlay=highlight_overlay,
            color_blind_palette=color_blind_palette,
        ),
        "default_subtype": default_subtype,
    }


TEMPLATES: dict[str, dict[str, Any]] = {
    "ModernSchool": _theme_payload(
        label="Modern School",
        summary="Bright classrooms and festival nights for slice-of-life arcs.",
        style_tags=["slice_of_life", "campus", "youth"],
        tag_remaps={
            "environment.classroom": "environment.school.classroom_day",
            "props.poster": "props.school.poster_set",
            "ambient.crowd": "sfx.students.hallway_soft",
        },
        kit={
            "luts": ["neutral", "daylight_soft", "chalk_pastel"],
            "music": {"set": "acoustic", "mood": "uplifting", "intensity": 0.28},
            "prompt": {
                "style": "campus slice-of-life",
                "lighting": "window glow",
                "flavor": "homeroom chatter and club plans",
                "keywords": ["school", "friends", "club", "festival"],
            },
            "palette": {
                "primary": "#F7F8FB",
                "secondary": "#1E6FFF",
                "accent": "#FDB515",
                "neutral": "#3B3F4C",
            },
            "camera": {
                "lens": "35mm",
                "framing": "waist_up",
                "movement": "tripod_locked",
                "grade": "soft_diffuse",
            },
            "assets": {
                "backdrop": "campus/classroom_day",
                "ambient_sfx": ["students.murmur.light", "school.bell.distant"],
                "weather": "clear",
                "overlays": ["ui/notes/chalk_particles"],
            },
            "props": {
                "foreground": ["props.school.desk_scatter"],
                "midground": ["props.school.banner_blank"],
                "ui": ["ui/notebook_scribbles"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "soft_white"},
                "roles": {
                    "protagonist": {"accent": "sky_blue"},
                    "mentor": {"accent": "sage"},
                    "rival": {"accent": "crimson"},
                },
            },
        },
        subtypes={
            "day": {
                "label": "Homeroom Day",
                "description": "Window-lit classroom at midday.",
                "overrides": {},
            },
            "festival": {
                "label": "School Festival",
                "description": "Lantern glow booths and evening excitement.",
                "overrides": {
                    "assets": {
                        "backdrop": "campus/festival_evening",
                        "ambient_sfx": ["festival.crowd.mellow", "lanterns.swing"],
                        "overlays": ["lights/festival_strings"],
                    },
                    "music": {"mood": "festive", "intensity": 0.45},
                    "prompt": {
                        "lighting": "lantern glow",
                        "flavor": "festival booths, handheld cameras, and late-night study plans",
                    },
                    "palette": {"accent": "#FFB703", "neutral": "#22313F"},
                    "camera": {"movement": "handheld_drift", "grade": "vibrant"},
                    "props": {
                        "foreground": ["props.festival.booth_stall"],
                        "ui": ["ui/confetti_stream"],
                    },
                    "style_tags": ["festival", "night"],
                },
            },
        },
        default_subtype="day",
        highlight_overlay="ui/anchors/classroom_highlight",
        color_blind_palette={"accent": "#118AB2", "secondary": "#8D99AE"},
    ),
    "UrbanNoir": _theme_payload(
        label="Urban Noir",
        summary="Rain-slick neon alleys and smoky basements for mystery beats.",
        style_tags=["noir", "urban", "crime"],
        tag_remaps={
            "environment.city.alley": "environment.noir.alley_rain",
            "lighting.window": "lighting.noir.venetian_blind",
            "props.smoke": "fx.noir.steam_vent",
        },
        kit={
            "luts": ["cool", "noir_high_contrast", "grain_emphasis"],
            "music": {"set": "jazz", "mood": "brooding", "intensity": 0.52},
            "prompt": {
                "style": "rain-soaked detective pulp",
                "lighting": "hard rim + neon bounce",
                "flavor": "detectives tracking leads through back alleys",
                "keywords": ["detective", "rain", "neon", "mystery"],
            },
            "palette": {
                "primary": "#1B1F29",
                "secondary": "#3D405B",
                "accent": "#FF3366",
                "neutral": "#0B132B",
            },
            "camera": {
                "lens": "50mm",
                "framing": "shoulder",
                "movement": "crane_rise",
                "grade": "high_contrast",
            },
            "assets": {
                "backdrop": "noir/alley_midnight",
                "ambient_sfx": ["rain.gutter.heavy", "neon.buzz.low"],
                "weather": "downpour",
                "overlays": ["fx/rain/sheets"],
            },
            "props": {
                "foreground": ["props.noir.cigarette_glow"],
                "midground": ["props.noir.streetlamp"],
                "ui": ["ui/noir_filmgrain"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "white"},
                "roles": {
                    "protagonist": {"accent": "steel_blue"},
                    "informant": {"accent": "amber"},
                    "antagonist": {"accent": "crimson"},
                },
            },
        },
        subtypes={
            "investigation": {
                "label": "Back-Alley Stakeout",
                "description": "Steady cams, rain slickers, and patient surveillance.",
                "overrides": {
                    "camera": {"movement": "tripod_locked"},
                    "style_tags": ["stakeout"],
                    "assets": {"overlays": ["fx/rain/drizzle"]},
                },
            },
            "speakeasy": {
                "label": "Speakeasy Den",
                "description": "Smoky club lights, brass, and whispered deals.",
                "overrides": {
                    "assets": {
                        "backdrop": "noir/speakeasy_smoke",
                        "ambient_sfx": ["club.piano.low", "crowd.murmur.smoke"],
                        "overlays": ["fx/smoke_plumes"],
                    },
                    "music": {"mood": "melancholic", "intensity": 0.4},
                    "prompt": {
                        "lighting": "spotlight haze",
                        "flavor": "late-night speakeasy tension and double-crosses",
                    },
                    "palette": {"accent": "#F4AF24", "neutral": "#1A1A2E"},
                    "style_tags": ["speakeasy", "night"],
                },
            },
        },
        default_subtype="investigation",
        highlight_overlay="ui/anchors/noir_highlight",
        color_blind_palette={"accent": "#F4D35E", "secondary": "#577590"},
    ),
    "Gothic": _theme_payload(
        label="Gothic",
        summary="Shadowed cathedrals and moonlit vows for dramatic rituals.",
        style_tags=["gothic", "melancholy", "ritual"],
        tag_remaps={
            "environment.cathedral": "environment.gothic.cathedral_candle",
            "props.statue": "props.gothic.gargoyle",
            "lighting.candle": "lighting.gothic.candle_cluster",
        },
        kit={
            "luts": ["warm", "gothic_shadow", "moonlit_blue"],
            "music": {"set": "orchestral", "mood": "somber", "intensity": 0.48},
            "prompt": {
                "style": "ancient cathedrals and heirloom curses",
                "lighting": "candle flicker with moon shafts",
                "flavor": "oaths whispered beneath stained glass",
                "keywords": ["cathedral", "ritual", "curse", "moonlight"],
            },
            "palette": {
                "primary": "#2F1B41",
                "secondary": "#6A4C93",
                "accent": "#C9ADA7",
                "neutral": "#160A1E",
            },
            "camera": {
                "lens": "40mm",
                "framing": "three_quarter",
                "movement": "slow_dolly",
                "grade": "deep_shadow",
            },
            "assets": {
                "backdrop": "gothic/cathedral_candle",
                "ambient_sfx": ["choir.distant", "wind.howl"],
                "weather": "mist",
                "overlays": ["fx/dust_motes"],
            },
            "props": {
                "foreground": ["props.gothic.candle_cluster"],
                "midground": ["props.gothic.stained_glass"],
                "ui": ["ui/scrollwork_frame"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "violet"},
                "roles": {
                    "protagonist": {"accent": "silver"},
                    "mystic": {"accent": "amethyst"},
                    "villain": {"accent": "crimson"},
                },
            },
        },
        subtypes={
            "cathedral": {
                "label": "Cathedral Nave",
                "description": "Echoing halls lit by candles and moonlight.",
                "overrides": {},
            },
            "graveyard": {
                "label": "Graveyard Fog",
                "description": "Mist-shrouded tombstones and willow silhouettes.",
                "overrides": {
                    "assets": {
                        "backdrop": "gothic/graveyard_fog",
                        "ambient_sfx": ["ravens.caw", "wind.branch.creak"],
                        "weather": "drizzle",
                        "overlays": ["fx/fog/rolling"],
                    },
                    "prompt": {
                        "lighting": "grave soil mist",
                        "flavor": "vows exchanged among tombstones",
                    },
                    "style_tags": ["graveyard", "fog"],
                    "camera": {"movement": "crane_rise"},
                },
            },
        },
        default_subtype="cathedral",
        highlight_overlay="ui/anchors/candle_glow",
        color_blind_palette={"accent": "#FFD166", "secondary": "#4A4E69"},
    ),
    "Cosmic": _theme_payload(
        label="Cosmic",
        summary="Nebula-lit observatories and eldritch experiments.",
        style_tags=["cosmic", "eldritch", "science"],
        tag_remaps={
            "environment.lab": "environment.cosmic.observatory",
            "lighting.monitor": "lighting.cosmic.ultraviolet",
            "props.library": "props.cosmic.star_chart",
        },
        kit={
            "luts": ["cool", "cosmic_violet", "starfield_overlay"],
            "music": {"set": "synth", "mood": "mysterious", "intensity": 0.4},
            "prompt": {
                "style": "liminal observatory research",
                "lighting": "nebula rim and monitor glow",
                "flavor": "scientists decoding stellar anomalies",
                "keywords": ["nebula", "research", "eldritch", "observatory"],
            },
            "palette": {
                "primary": "#0B132B",
                "secondary": "#1C2541",
                "accent": "#5BC0BE",
                "neutral": "#3A506B",
            },
            "camera": {
                "lens": "24mm",
                "framing": "wide",
                "movement": "orbit_pan",
                "grade": "neon_violet",
            },
            "assets": {
                "backdrop": "cosmic/observatory_nebula",
                "ambient_sfx": ["equipment.hum.low", "radio.scan"],
                "weather": "aurora",
                "overlays": ["fx/nebula_particles"],
            },
            "props": {
                "foreground": ["props.cosmic.star_map"],
                "midground": ["props.cosmic.hologram_armillary"],
                "ui": ["ui/cosmic_constellations"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "teal"},
                "roles": {
                    "navigator": {"accent": "cyan"},
                    "researcher": {"accent": "violet"},
                    "oracle": {"accent": "gold"},
                },
            },
        },
        subtypes={
            "observatory": {
                "label": "Deep-Sky Observatory",
                "description": "Telescopes, chart tables, and midnight shifts.",
                "overrides": {},
            },
            "eldritch": {
                "label": "Eldritch Storm",
                "description": "Anomalous symbols flicker across containment glass.",
                "overrides": {
                    "assets": {
                        "ambient_sfx": ["whispers.layered", "radio.static.corrupt"],
                        "overlays": ["fx/eldritch_runes"],
                        "weather": "geomagnetic_storm",
                    },
                    "music": {"mood": "unsettling", "intensity": 0.6},
                    "prompt": {
                        "flavor": "summoning circles flare as reality distorts",
                        "lighting": "violet breach flares",
                    },
                    "style_tags": ["eldritch", "storm"],
                },
            },
        },
        default_subtype="observatory",
        highlight_overlay="ui/anchors/constellation_highlight",
        color_blind_palette={"accent": "#F4D35E", "secondary": "#4CC9F0"},
    ),
    "Cyberpunk": _theme_payload(
        label="Cyberpunk",
        summary="Neon arteries, holographic billboards, and corporate intrigue.",
        style_tags=["cyberpunk", "neon", "future"],
        tag_remaps={
            "environment.city.center": "environment.cyberpunk.avenue",
            "lighting.billboard": "lighting.cyberpunk.hologram",
            "props.vehicle": "props.cyberpunk.hoversled",
        },
        kit={
            "luts": ["vibrant", "neon_split", "chromatic_aberration"],
            "music": {"set": "synthwave", "mood": "driving", "intensity": 0.62},
            "prompt": {
                "style": "dense megacity holograms",
                "lighting": "hologram spill and street-level neon",
                "flavor": "runners weaving through corporate choke points",
                "keywords": ["neon", "augmented", "runner", "megacity"],
            },
            "palette": {
                "primary": "#0A0E1A",
                "secondary": "#FF3366",
                "accent": "#21FBDD",
                "neutral": "#111827",
            },
            "camera": {
                "lens": "24mm",
                "framing": "dynamic_wide",
                "movement": "drone_glide",
                "grade": "hyper_saturated",
            },
            "assets": {
                "backdrop": "cyberpunk/avenue_neon",
                "ambient_sfx": ["city.hum.neon", "drones.flyover"],
                "weather": "rain_neon",
                "overlays": ["fx/neon_scanlines"],
            },
            "props": {
                "foreground": ["props.cyberpunk.holo_ads"],
                "midground": ["props.cyberpunk.skyrail"],
                "ui": ["ui/hud_circuitry"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "teal"},
                "roles": {
                    "runner": {"accent": "electric_cyan"},
                    "net_op": {"accent": "magenta"},
                    "fixer": {"accent": "amber"},
                },
            },
        },
        subtypes={
            "streets": {
                "label": "Lower Streets",
                "description": "Towering signage and market bustle at street level.",
                "overrides": {},
            },
            "corporate": {
                "label": "Corporate Atrium",
                "description": "Glass skybridges and security drones above the smog layer.",
                "overrides": {
                    "assets": {
                        "backdrop": "cyberpunk/corporate_atrium",
                        "ambient_sfx": ["atrium.hum", "security.drone.hover"],
                        "overlays": ["fx/holo_panels"],
                    },
                    "music": {"mood": "tense", "intensity": 0.55},
                    "prompt": {
                        "lighting": "corporate cool wash",
                        "flavor": "suits negotiate behind mirrored glass",
                    },
                    "palette": {"accent": "#8AFF80", "neutral": "#0D1B2A"},
                    "style_tags": ["corporate", "atrium"],
                },
            },
        },
        default_subtype="streets",
        highlight_overlay="ui/anchors/neon_trace",
        color_blind_palette={"accent": "#FEE440", "secondary": "#2EC4B6"},
    ),
    "Space": _theme_payload(
        label="Space Frontier",
        summary="Bridge briefings, holo tables, and starlit vistas.",
        style_tags=["space", "bridge", "scifi"],
        tag_remaps={
            "environment.bridge": "environment.space.bridge_command",
            "lighting.console": "lighting.space.hologrid",
            "props.screen": "props.space.holo_table",
        },
        kit={
            "luts": ["cool", "sterile_white", "starlight_reflect"],
            "music": {"set": "ambient", "mood": "expansive", "intensity": 0.35},
            "prompt": {
                "style": "bridge command drama",
                "lighting": "console flood with rim light",
                "flavor": "captains plotting jumps across uncharted sectors",
                "keywords": ["bridge", "starfield", "captain", "jump"],
            },
            "palette": {
                "primary": "#0D1B2A",
                "secondary": "#1B263B",
                "accent": "#70F0FF",
                "neutral": "#415A77",
            },
            "camera": {
                "lens": "28mm",
                "framing": "two_shot",
                "movement": "steady_float",
                "grade": "clean_specular",
            },
            "assets": {
                "backdrop": "space/bridge_gold",
                "ambient_sfx": ["engines.hum.low", "console.beep"],
                "weather": "starfield",
                "overlays": ["fx/hologrid_lines"],
            },
            "props": {
                "foreground": ["props.space.holo_emitter"],
                "midground": ["props.space.command_chair"],
                "ui": ["ui/hud_reticle"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "ice_blue"},
                "roles": {
                    "captain": {"accent": "gold"},
                    "navigator": {"accent": "cyan"},
                    "science_officer": {"accent": "violet"},
                },
            },
        },
        subtypes={
            "bridge": {
                "label": "Command Bridge",
                "description": "Flagship consoles and panoramic starfields.",
                "overrides": {},
            },
            "colony": {
                "label": "Colony Concourse",
                "description": "Curved glass promenades overlooking terraform domes.",
                "overrides": {
                    "assets": {
                        "backdrop": "space/colony_concourse",
                        "ambient_sfx": ["crowd.low", "tram.chime"],
                        "overlays": ["fx/holo_adverts"],
                    },
                    "music": {"mood": "hopeful", "intensity": 0.3},
                    "prompt": {
                        "flavor": "citizens gather under the colony shield",
                        "lighting": "dome daylight",
                    },
                    "style_tags": ["colony", "civilians"],
                },
            },
        },
        default_subtype="bridge",
        highlight_overlay="ui/anchors/holo_ping",
        color_blind_palette={"accent": "#FFD23F", "secondary": "#4EA8DE"},
    ),
    "PostApoc": _theme_payload(
        label="Post-Apoc",
        summary="Sun-bleached ruins, scavenger camps, and survival fires.",
        style_tags=["post_apocalyptic", "survival", "dust"],
        tag_remaps={
            "environment.city.ruins": "environment.postapoc.overpass",
            "lighting.street": "lighting.postapoc.firebarrel",
            "props.vehicle": "props.postapoc.rusted_van",
        },
        kit={
            "luts": ["warm_desaturate", "dust_filter", "sunset_smoke"],
            "music": {"set": "percussion", "mood": "tense", "intensity": 0.58},
            "prompt": {
                "style": "sun-bleached ruins and scavenger scrawls",
                "lighting": "hard sun with ember fill",
                "flavor": "survivors bargaining for clean water",
                "keywords": ["ruins", "scavenger", "dust", "survival"],
            },
            "palette": {
                "primary": "#3D2C29",
                "secondary": "#735751",
                "accent": "#E07A5F",
                "neutral": "#403D39",
            },
            "camera": {
                "lens": "35mm",
                "framing": "medium",
                "movement": "handheld_shake",
                "grade": "grit",
            },
            "assets": {
                "backdrop": "postapoc/overpass_dust",
                "ambient_sfx": ["wind.dust", "metal.creak"],
                "weather": "dust_storm",
                "overlays": ["fx/dust_particles"],
            },
            "props": {
                "foreground": ["props.postapoc.barrel_fire"],
                "midground": ["props.postapoc.sign_warning"],
                "ui": ["ui/tape_overlay"],
            },
            "characters": {
                "default": {"palette": "warm", "rim_light": "amber"},
                "roles": {
                    "scavenger": {"accent": "rust"},
                    "guardian": {"accent": "sage"},
                    "trader": {"accent": "copper"},
                },
            },
        },
        subtypes={
            "overpass": {
                "label": "Collapsed Overpass",
                "description": "Highway skeletons and dusty winds.",
                "overrides": {},
            },
            "refuge": {
                "label": "Makeshift Refuge",
                "description": "Canvas walls, flickering fires, and recycled tech.",
                "overrides": {
                    "assets": {
                        "backdrop": "postapoc/refuge_tent",
                        "ambient_sfx": ["campfire.low", "generator.hum"],
                        "weather": "calm",
                        "overlays": ["fx/smoke_column"],
                    },
                    "music": {"mood": "resilient", "intensity": 0.32},
                    "prompt": {
                        "flavor": "bargains struck over ration tins",
                        "lighting": "lantern warm",
                    },
                    "style_tags": ["camp", "refuge"],
                },
            },
        },
        default_subtype="overpass",
        highlight_overlay="ui/anchors/flare_marker",
        color_blind_palette={"accent": "#F6AE2D", "secondary": "#5E6F64"},
    ),
    "HighFantasy": _theme_payload(
        label="High Fantasy",
        summary="Verdant glades, citadel halls, and gleaming sigils.",
        style_tags=["high_fantasy", "magic", "quest"],
        tag_remaps={
            "environment.forest": "environment.fantasy.elven_glade",
            "lighting.sunshaft": "lighting.fantasy.sunrays",
            "props.banner": "props.fantasy.banner_sigil",
        },
        kit={
            "luts": ["warm", "storybook", "verdant_glow"],
            "music": {"set": "orchestral", "mood": "adventurous", "intensity": 0.55},
            "prompt": {
                "style": "verdant glades and heroic vows",
                "lighting": "sun shafts with rim bloom",
                "flavor": "companions swear oaths beneath ancient trees",
                "keywords": ["glade", "hero", "sigil", "magic"],
            },
            "palette": {
                "primary": "#2A9D8F",
                "secondary": "#264653",
                "accent": "#E9C46A",
                "neutral": "#2F3E46",
            },
            "camera": {
                "lens": "32mm",
                "framing": "two_shot",
                "movement": "crane_swoop",
                "grade": "painterly",
            },
            "assets": {
                "backdrop": "fantasy/elven_glade",
                "ambient_sfx": ["forest.birds", "stream.gentle"],
                "weather": "sun_dappled",
                "overlays": ["fx/pollen_glow"],
            },
            "props": {
                "foreground": ["props.fantasy.stone_circle"],
                "midground": ["props.fantasy.banner_sigil"],
                "ui": ["ui/rune_frame"],
            },
            "characters": {
                "default": {"palette": "warm", "rim_light": "gold"},
                "roles": {
                    "hero": {"accent": "gold"},
                    "mage": {"accent": "azure"},
                    "villain": {"accent": "obsidian"},
                },
            },
        },
        subtypes={
            "glade": {
                "label": "Elven Glade",
                "description": "Sun-dappled groves and rune-carved stones.",
                "overrides": {},
            },
            "citadel": {
                "label": "Citadel Hall",
                "description": "Vaulted ceilings, banners, and marble light.",
                "overrides": {
                    "assets": {
                        "backdrop": "fantasy/citadel_hall",
                        "ambient_sfx": ["hall.echo", "armor.clink"],
                        "overlays": ["fx/light_shafts"],
                    },
                    "music": {"mood": "majestic", "intensity": 0.5},
                    "prompt": {
                        "flavor": "councils debate in banner-lined halls",
                        "lighting": "torchlight with stained glass",
                    },
                    "palette": {"accent": "#FFD166", "neutral": "#3C2F2F"},
                    "style_tags": ["court", "citadel"],
                },
            },
        },
        default_subtype="glade",
        highlight_overlay="ui/anchors/glimmer_trail",
        color_blind_palette={"accent": "#FFD166", "secondary": "#4E9F3D"},
    ),
    "Historical": _theme_payload(
        label="Historical",
        summary="Tea house intrigue, court scribes, and dusk campaigns.",
        style_tags=["historical", "period_drama", "tradition"],
        tag_remaps={
            "environment.tea_house": "environment.historical.tea_house_evening",
            "lighting.paper": "lighting.historical.paper_lantern",
            "props.scroll": "props.historical.calligraphy",
        },
        kit={
            "luts": ["warm", "tea_brown", "film_grain_soft"],
            "music": {"set": "chamber", "mood": "reflective", "intensity": 0.33},
            "prompt": {
                "style": "period drama etiquette",
                "lighting": "paper lantern warmth",
                "flavor": "quiet negotiations over tea",
                "keywords": ["tea", "diplomacy", "lantern", "scroll"],
            },
            "palette": {
                "primary": "#F1E4C3",
                "secondary": "#8B5E3C",
                "accent": "#C06014",
                "neutral": "#3D2B1F",
            },
            "camera": {
                "lens": "45mm",
                "framing": "two_shot",
                "movement": "slider",
                "grade": "sepia_soft",
            },
            "assets": {
                "backdrop": "historical/tea_house_evening",
                "ambient_sfx": ["tea.pour", "paper.rustle"],
                "weather": "clear",
                "overlays": ["fx/smoke_delicate"],
            },
            "props": {
                "foreground": ["props.historical.tea_service"],
                "midground": ["props.historical.screen"],
                "ui": ["ui/ink_brush"],
            },
            "characters": {
                "default": {"palette": "warm", "rim_light": "amber"},
                "roles": {
                    "diplomat": {"accent": "crimson"},
                    "scribe": {"accent": "navy"},
                    "general": {"accent": "steel"},
                },
            },
        },
        subtypes={
            "tea_house": {
                "label": "Tea House",
                "description": "Tatami floors, paper screens, and incense smoke.",
                "overrides": {},
            },
            "battlefield": {
                "label": "Battlefield Dusk",
                "description": "Banners snapping against twilight skies.",
                "overrides": {
                    "assets": {
                        "backdrop": "historical/battlefield_dusk",
                        "ambient_sfx": ["banner.flap", "distant.drums"],
                        "weather": "windy",
                        "overlays": ["fx/embers_scatter"],
                    },
                    "music": {"mood": "solemn", "intensity": 0.45},
                    "prompt": {
                        "flavor": "commanders weigh sacrifice on the eve of battle",
                        "lighting": "sunset smoke",
                    },
                    "style_tags": ["campaign", "battlefield"],
                },
            },
        },
        default_subtype="tea_house",
        highlight_overlay="ui/anchors/paper_glow",
        color_blind_palette={"accent": "#B5838D", "secondary": "#6D6875"},
    ),
    "Steampunk": _theme_payload(
        label="Steampunk",
        summary="Brass foundries, dirigible decks, and alchemical gauges.",
        style_tags=["steampunk", "industrial", "brass"],
        tag_remaps={
            "environment.factory": "environment.steampunk.foundry",
            "lighting.spark": "lighting.steampunk.arc",
            "props.pipe": "props.steampunk.brass_pipe",
        },
        kit={
            "luts": ["warm_copper", "smog_filter", "brass_glow"],
            "music": {"set": "clockwork", "mood": "driving", "intensity": 0.6},
            "prompt": {
                "style": "whirring gears and dirigible fleets",
                "lighting": "steam flare and amber gauge",
                "flavor": "captains haggle over aether routes",
                "keywords": ["gear", "dirigible", "aether", "brass"],
            },
            "palette": {
                "primary": "#3A2618",
                "secondary": "#B08968",
                "accent": "#E09F3E",
                "neutral": "#5E503F",
            },
            "camera": {
                "lens": "30mm",
                "framing": "medium_wide",
                "movement": "gear_pan",
                "grade": "bronze_contrast",
            },
            "assets": {
                "backdrop": "steampunk/foundry_core",
                "ambient_sfx": ["machinery.clank", "steam.hiss"],
                "weather": "smoke",
                "overlays": ["fx/steam_plume"],
            },
            "props": {
                "foreground": ["props.steampunk.gauge_console"],
                "midground": ["props.steampunk.gear_wall"],
                "ui": ["ui/gear_overlay"],
            },
            "characters": {
                "default": {"palette": "warm", "rim_light": "brass"},
                "roles": {
                    "engineer": {"accent": "copper"},
                    "captain": {"accent": "navy"},
                    "mechanic": {"accent": "rust"},
                },
            },
        },
        subtypes={
            "foundry": {
                "label": "Gear Foundry",
                "description": "Riveted beams and roaring furnaces.",
                "overrides": {},
            },
            "airship": {
                "label": "Airship Deck",
                "description": "Rope lattices, steam vents, and skyline vistas.",
                "overrides": {
                    "assets": {
                        "backdrop": "steampunk/airship_deck",
                        "ambient_sfx": ["wind.deck", "propellers.spin"],
                        "overlays": ["fx/cloud_scud"],
                    },
                    "music": {"mood": "adventurous", "intensity": 0.52},
                    "prompt": {
                        "flavor": "crews brace for aether turbulence",
                        "lighting": "sunset bronze",
                    },
                    "style_tags": ["airship", "sky"],
                },
            },
        },
        default_subtype="foundry",
        highlight_overlay="ui/anchors/cog_glow",
        color_blind_palette={"accent": "#FFD166", "secondary": "#6A994E"},
    ),
    "Pirate": _theme_payload(
        label="Pirate",
        summary="Salt-sprayed decks, lantern-lit gambits, and raucous crews.",
        style_tags=["pirate", "high_seas", "swashbuckler"],
        tag_remaps={
            "environment.ship.deck": "environment.pirate.deck_storm",
            "lighting.lantern": "lighting.pirate.lantern",
            "props.flag": "props.pirate.flag_jolly",
        },
        kit={
            "luts": ["warm", "sunset_glow", "spray_highlight"],
            "music": {"set": "sea_shanty", "mood": "rollicking", "intensity": 0.5},
            "prompt": {
                "style": "salt-sprayed decks and daring heists",
                "lighting": "lantern backlight with horizon bloom",
                "flavor": "crews chart mutinous courses at dusk",
                "keywords": ["deck", "lantern", "treasure", "storm"],
            },
            "palette": {
                "primary": "#1C2A3A",
                "secondary": "#2A4D69",
                "accent": "#F4A261",
                "neutral": "#3E3D32",
            },
            "camera": {
                "lens": "28mm",
                "framing": "dynamic_wide",
                "movement": "boom_sway",
                "grade": "sunset_dramatic",
            },
            "assets": {
                "backdrop": "pirate/harbor_sunset",
                "ambient_sfx": ["waves.crash", "gulls.call"],
                "weather": "breezy",
                "overlays": ["fx/spray_mist"],
            },
            "props": {
                "foreground": ["props.pirate.treasure_chest"],
                "midground": ["props.pirate.mast"],
                "ui": ["ui/map_edges"],
            },
            "characters": {
                "default": {"palette": "warm", "rim_light": "sunset"},
                "roles": {
                    "captain": {"accent": "gold"},
                    "first_mate": {"accent": "teal"},
                    "raider": {"accent": "scarlet"},
                },
            },
        },
        subtypes={
            "harbor": {
                "label": "Harbor Sunset",
                "description": "Anchored ships, market lanterns, and plotting crews.",
                "overrides": {},
            },
            "storm": {
                "label": "Tempest Deck",
                "description": "Raging surf, lightning strikes, and taut rigging.",
                "overrides": {
                    "assets": {
                        "backdrop": "pirate/tempest_deck",
                        "ambient_sfx": ["thunder.roll", "sails.snap"],
                        "weather": "storm",
                        "overlays": ["fx/rain/heavy"],
                    },
                    "music": {"mood": "urgent", "intensity": 0.62},
                    "prompt": {
                        "flavor": "storm-lashed duel along the railing",
                        "lighting": "lightning strobe",
                    },
                    "style_tags": ["storm", "battle"],
                },
            },
        },
        default_subtype="harbor",
        highlight_overlay="ui/anchors/lantern_glow",
        color_blind_palette={"accent": "#FFD166", "secondary": "#577590"},
    ),
    "Superhero": _theme_payload(
        label="Superhero",
        summary="City skylines, signal beacons, and kinetic hero poses.",
        style_tags=["superhero", "city", "action"],
        tag_remaps={
            "environment.city.rooftop": "environment.superhero.rooftop_city",
            "lighting.searchlight": "lighting.superhero.signal",
            "props.billboard": "props.superhero.holo_briefing",
        },
        kit={
            "luts": ["vibrant", "comic_pop", "deep_blue"],
            "music": {"set": "orchestral_hybrid", "mood": "heroic", "intensity": 0.7},
            "prompt": {
                "style": "heroic silhouettes over gleaming skylines",
                "lighting": "signal beams and city glow",
                "flavor": "team briefings high above the streets",
                "keywords": ["rooftop", "signal", "mission", "city"],
            },
            "palette": {
                "primary": "#0D1F2D",
                "secondary": "#34495E",
                "accent": "#F94144",
                "neutral": "#2C3E50",
            },
            "camera": {
                "lens": "24mm",
                "framing": "hero_plunge",
                "movement": "hero_push",
                "grade": "punchy",
            },
            "assets": {
                "backdrop": "superhero/rooftop_night",
                "ambient_sfx": ["sirens.distant", "wind.gust"],
                "weather": "clear",
                "overlays": ["fx/city_light_trails"],
            },
            "props": {
                "foreground": ["props.superhero.banner"],
                "midground": ["props.superhero.signal"],
                "ui": ["ui/comic_panels"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "white_hot"},
                "roles": {
                    "leader": {"accent": "crimson"},
                    "tech": {"accent": "teal"},
                    "antihero": {"accent": "violet"},
                },
            },
        },
        subtypes={
            "rooftop": {
                "label": "Rooftop Signal",
                "description": "Signal beams cut through the night as the team assembles.",
                "overrides": {},
            },
            "hq": {
                "label": "Hero HQ",
                "description": "Holographic briefings inside a reinforced command center.",
                "overrides": {
                    "assets": {
                        "backdrop": "superhero/hq_command_center",
                        "ambient_sfx": ["computers.chatter", "airlock.seal"],
                        "overlays": ["fx/hologrid_panels"],
                    },
                    "music": {"mood": "strategic", "intensity": 0.5},
                    "prompt": {
                        "flavor": "mission briefings around a glowing table",
                        "lighting": "hologrid spill",
                    },
                    "style_tags": ["hq", "command"],
                },
            },
        },
        default_subtype="rooftop",
        highlight_overlay="ui/anchors/signal_glow",
        color_blind_palette={"accent": "#FFD23F", "secondary": "#4ECDC4"},
    ),
    "Mecha": _theme_payload(
        label="Mecha",
        summary="Towering frames, maintenance crews, and briefing alarms.",
        style_tags=["mecha", "military", "hangar"],
        tag_remaps={
            "environment.hangar": "environment.mecha.hangar_dawn",
            "lighting.panel": "lighting.mecha.indicator",
            "props.armory": "props.mecha.weapon_rack",
        },
        kit={
            "luts": ["cool", "steel_blue", "sparks"],
            "music": {"set": "industrial", "mood": "tense", "intensity": 0.6},
            "prompt": {
                "style": "towering frames and maintenance crews",
                "lighting": "sodium vapor with indicator lights",
                "flavor": "pilots suit up amid hydraulic hiss",
                "keywords": ["hangar", "pilot", "hydraulics", "briefing"],
            },
            "palette": {
                "primary": "#1A2A33",
                "secondary": "#2E4756",
                "accent": "#FF9F1C",
                "neutral": "#14213D",
            },
            "camera": {
                "lens": "21mm",
                "framing": "monumental",
                "movement": "dolly_parallax",
                "grade": "chromed",
            },
            "assets": {
                "backdrop": "mecha/hangar_dawn",
                "ambient_sfx": ["hydraulics.hiss", "alarm.chime"],
                "weather": "fog_low",
                "overlays": ["fx/sparks_arc"],
            },
            "props": {
                "foreground": ["props.mecha.tool_crate"],
                "midground": ["props.mecha.frame_silhouette"],
                "ui": ["ui/hud_scanlines"],
            },
            "characters": {
                "default": {"palette": "cool", "rim_light": "amber"},
                "roles": {
                    "pilot": {"accent": "orange"},
                    "engineer": {"accent": "lime"},
                    "commander": {"accent": "steel"},
                },
            },
        },
        subtypes={
            "hangar": {
                "label": "Hangar Dawn",
                "description": "Pre-launch checks under tungsten floods.",
                "overrides": {},
            },
            "field": {
                "label": "Training Field",
                "description": "Skirmish drills over scorched grasses.",
                "overrides": {
                    "assets": {
                        "backdrop": "mecha/training_field",
                        "ambient_sfx": ["wind.flag", "mecha.step"],
                        "weather": "dust",
                        "overlays": ["fx/heat_haze"],
                    },
                    "music": {"mood": "urgent", "intensity": 0.55},
                    "prompt": {
                        "flavor": "commanders critique maneuvers beside mobile HQs",
                        "lighting": "heat shimmer",
                    },
                    "style_tags": ["training", "field"],
                },
            },
        },
        default_subtype="hangar",
        highlight_overlay="ui/anchors/hud_trace",
        color_blind_palette={"accent": "#FFB703", "secondary": "#4361EE"},
    ),
    "Cozy": _theme_payload(
        label="Cozy",
        summary="Fireplace glow, rainy cafe breaks, and intimate conversations.",
        style_tags=["cozy", "home", "warmth"],
        tag_remaps={
            "environment.cabin": "environment.cozy.cabin_fireplace",
            "lighting.string": "lighting.cozy.stringlights",
            "props.mug": "props.cozy.mug_stack",
        },
        kit={
            "luts": ["warm", "ember_glow", "soft_focus"],
            "music": {"set": "acoustic", "mood": "relaxed", "intensity": 0.24},
            "prompt": {
                "style": "hearthside stories and restful evenings",
                "lighting": "fireplace bounce and lamplight",
                "flavor": "friends exchange gifts beneath string lights",
                "keywords": ["fireplace", "cabin", "blanket", "tea"],
            },
            "palette": {
                "primary": "#F2E9E4",
                "secondary": "#C9ADA7",
                "accent": "#9A8C98",
                "neutral": "#4A4E69",
            },
            "camera": {
                "lens": "45mm",
                "framing": "intimate",
                "movement": "gentle_push",
                "grade": "soft_bloom",
            },
            "assets": {
                "backdrop": "cozy/cabin_fireplace",
                "ambient_sfx": ["fireplace.crackle", "wind.window"],
                "weather": "snow",
                "overlays": ["fx/ember_float"],
            },
            "props": {
                "foreground": ["props.cozy.knit_blanket"],
                "midground": ["props.cozy.books_stack"],
                "ui": ["ui/recipe_card"],
            },
            "characters": {
                "default": {"palette": "warm", "rim_light": "amber"},
                "roles": {
                    "protagonist": {"accent": "rose"},
                    "friend": {"accent": "sage"},
                    "pet": {"accent": "cream"},
                },
            },
        },
        subtypes={
            "cabin": {
                "label": "Mountain Cabin",
                "description": "Snow drifts outside while cocoa steams inside.",
                "overrides": {},
            },
            "cafe": {
                "label": "Neighborhood Cafe",
                "description": "Rainy windows, latte art, and sketchbooks.",
                "overrides": {
                    "assets": {
                        "backdrop": "cozy/neighborhood_cafe",
                        "ambient_sfx": ["cafe.murmur", "spoon.clink"],
                        "weather": "rain",
                        "overlays": ["fx/rain_window"],
                    },
                    "music": {"mood": "lounge", "intensity": 0.26},
                    "prompt": {
                        "flavor": "rainy cafe solace and whispered confessions",
                        "lighting": "window reflections",
                    },
                    "style_tags": ["cafe", "rain"],
                },
            },
        },
        default_subtype="cabin",
        highlight_overlay="ui/anchors/soft_glow",
        color_blind_palette={"accent": "#F4D35E", "secondary": "#8ECAE6"},
    ),
}

_THEME_ALIASES: dict[str, str] = {
    "modern": "ModernSchool",
    "modern school": "ModernSchool",
    "modern-school": "ModernSchool",
    "modern_school": "ModernSchool",
    "school": "ModernSchool",
    "urban noir": "UrbanNoir",
    "urban-noir": "UrbanNoir",
    "urban_noir": "UrbanNoir",
    "noir": "UrbanNoir",
    "modern noir": "UrbanNoir",
    "dark": "UrbanNoir",
    "gothic": "Gothic",
    "gothic horror": "Gothic",
    "cathedral": "Gothic",
    "graveyard": "Gothic",
    "cosmic": "Cosmic",
    "eldritch": "Cosmic",
    "cyberpunk": "Cyberpunk",
    "neon": "Cyberpunk",
    "space": "Space",
    "space frontier": "Space",
    "spacefrontier": "Space",
    "space-opera": "Space",
    "space_opera": "Space",
    "post-apoc": "PostApoc",
    "post apoc": "PostApoc",
    "postapoc": "PostApoc",
    "post-apocalyptic": "PostApoc",
    "high fantasy": "HighFantasy",
    "fantasy": "HighFantasy",
    "historical": "Historical",
    "period": "Historical",
    "steampunk": "Steampunk",
    "pirate": "Pirate",
    "swashbuckler": "Pirate",
    "superhero": "Superhero",
    "hero": "Superhero",
    "mecha": "Mecha",
    "mech": "Mecha",
    "cozy": "Cozy",
    "comfort": "Cozy",
    "romantic": "Cozy",
    "romance": "Cozy",
    "action": "Superhero",
}


def available_templates(*, detailed: bool = False) -> list[Any]:
    ordered = sorted(TEMPLATES.items(), key=lambda item: item[1].get("label", item[0]))
    if not detailed:
        return [name for name, _ in ordered]

    catalog: list[dict[str, Any]] = []
    for name, payload in ordered:
        subtypes = []
        for key, entry in (payload.get("subtypes") or {}).items():
            subtypes.append(
                {
                    "name": key,
                    "label": entry.get("label", key.title()),
                    "description": entry.get("description", ""),
                    "default": key == payload.get("default_subtype", "default"),
                }
            )
        variants = []
        for key, entry in (payload.get("accessibility") or {}).items():
            variants.append(
                {
                    "name": key,
                    "label": entry.get("label", key.title()),
                    "description": entry.get("description", ""),
                }
            )
        catalog.append(
            {
                "name": name,
                "label": payload.get("label", name),
                "summary": payload.get("summary", ""),
                "style_tags": list(payload.get("style_tags") or []),
                "tag_remaps": dict(payload.get("tag_remaps") or {}),
                "subtypes": sorted(subtypes, key=lambda item: item["label"].lower()),
                "variants": sorted(variants, key=lambda item: item["name"]),
            }
        )
    return catalog


def template_catalog() -> list[dict[str, Any]]:
    return available_templates(detailed=True)


def plan(
    theme: str,
    scene: Mapping[str, Any] | None = None,
    *,
    subtype: str | None = None,
    anchors: Iterable[str] | None = None,
    overrides: Mapping[str, Any] | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    template_name = _canonical_theme(theme)
    template = deepcopy(TEMPLATES[template_name])
    kit = deepcopy(template.get("kit") or {})
    kit.setdefault("style_tags", list(template.get("style_tags") or []))
    kit.setdefault("tag_remaps", dict(template.get("tag_remaps") or {}))

    subtype_key, subtype_payload = _resolve_subtype(template, subtype)
    variant_key, variant_payload = _resolve_variant(template, variant)

    kit = _merge_nested(kit, dict(subtype_payload.get("overrides") or {}))
    kit = _merge_nested(kit, dict(variant_payload.get("overrides") or {}))

    scene_state = dict(scene or {})
    scene_theme_state = _to_dict(
        scene_state.get("theme") or scene_state.get("theme_state")
    )
    character_overrides = _extract_character_overrides(overrides, scene_state)
    characters = _normalise_characters(scene_state.get("characters"))

    assets_after = _sorted_dict(_to_dict(kit.get("assets")))
    luts_after = _normalise_list(kit.get("luts"))
    music_after = _sorted_dict(_to_dict(kit.get("music")))
    prompt_after = _sorted_dict(_to_dict(kit.get("prompt")))
    palette_after = _sorted_dict(_to_dict(kit.get("palette")))
    camera_after = _sorted_dict(_to_dict(kit.get("camera")))
    props_after = _normalise_props(kit.get("props"))
    style_tags_after = _normalise_list(kit.get("style_tags"))
    tag_remaps_after = _sorted_dict(_to_dict(kit.get("tag_remaps")))

    assets_before = _sorted_dict(_to_dict(scene_theme_state.get("assets")))
    luts_before = _normalise_list(scene_theme_state.get("luts"))
    music_before = _sorted_dict(_to_dict(scene_theme_state.get("music")))
    prompt_before = _sorted_dict(_to_dict(scene_theme_state.get("prompt")))
    palette_before = _sorted_dict(
        _to_dict(scene_theme_state.get("palette") or scene_state.get("palette"))
    )
    camera_before = _sorted_dict(
        _to_dict(scene_theme_state.get("camera") or scene_state.get("camera"))
    )
    props_before = _normalise_props(
        scene_theme_state.get("props") or scene_state.get("props")
    )
    style_tags_before = _normalise_list(
        scene_theme_state.get("style_tags") or scene_state.get("style_tags")
    )
    tag_remaps_before = _sorted_dict(
        _to_dict(scene_theme_state.get("tag_remaps") or scene_state.get("tag_remaps"))
    )

    delta_characters = _compose_character_deltas(
        characters,
        kit.get("characters", {}),
        character_overrides,
    )

    anchor_catalog, anchor_details = _extract_scene_anchors(scene_state)
    requested_anchors = _normalise_anchor_ids(
        anchors
        or scene_state.get("anchors_preserve")
        or scene_state.get("anchors_keep")
        or scene_theme_state.get("anchors_preserve")
    )
    preserved = [anchor for anchor in requested_anchors if anchor in anchor_catalog]
    released = [anchor for anchor in anchor_catalog if anchor not in preserved]

    mutations = {
        "assets": _compose_delta(assets_before, assets_after),
        "luts": _compose_delta(luts_before, luts_after),
        "music": _compose_delta(music_before, music_after),
        "prompt": _compose_delta(prompt_before, prompt_after),
        "palette": _compose_delta(palette_before, palette_after),
        "camera": _compose_delta(camera_before, camera_after),
        "props": _compose_delta(props_before, props_after),
        "style_tags": _compose_delta(style_tags_before, style_tags_after),
        "tag_remaps": _compose_delta(tag_remaps_before, tag_remaps_after),
        "characters": delta_characters,
    }

    plan_payload = {
        "theme": template_name,
        "theme_label": template.get("label", template_name),
        "scene_id": _scene_identifier(scene_state),
        "world_id": _world_identifier(scene_state),
        "mutations": mutations,
        "anchors": {
            "available": anchor_catalog,
            "preserved": preserved,
            "released": released,
            "details": anchor_details,
        },
        "metadata": {
            "template_label": template.get("label", template_name),
            "summary": template.get("summary", ""),
            "subtype": subtype_key,
            "subtype_label": subtype_payload.get("label", subtype_key.title()),
            "variant": variant_key,
            "variant_label": variant_payload.get("label", variant_key.title()),
            "anchors_preserved": preserved,
            "available_subtypes": _subtype_catalog(template),
            "available_variants": _variant_catalog(template),
            "style_tags": style_tags_after,
            "prompt_flavor": prompt_after.get("flavor"),
        },
        "preview": {
            "palette": palette_after,
            "luts": luts_after,
            "camera": camera_after,
            "props": props_after,
            "prompt": prompt_after,
            "assets": assets_after,
            "music": music_after,
        },
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
    raw = str(theme).strip()
    key_lower = raw.lower()
    resolved = _THEME_ALIASES.get(key_lower)
    if resolved:
        return resolved
    compact = key_lower.replace("-", "").replace("_", "").replace(" ", "")
    for candidate in TEMPLATES:
        candidate_compact = candidate.lower().replace("-", "").replace("_", "")
        if candidate_compact == compact:
            return candidate
    normalised = key_lower.replace("-", " ").replace("_", " ")
    normalised = normalised.title().replace(" ", "")
    if normalised in TEMPLATES:
        return normalised
    raise KeyError(f"Unknown theme '{theme}'")


def _canonical_subtype(template: Mapping[str, Any], subtype: str | None) -> str:
    subtypes = template.get("subtypes") or {}
    if not subtypes:
        return "default"
    default_key = template.get("default_subtype") or next(iter(subtypes))
    if not subtype:
        return default_key
    target = _normalise_key(subtype)
    for key, payload in subtypes.items():
        label = payload.get("label")
        if _normalise_key(key) == target or _normalise_key(str(label or "")) == target:
            return key
    return default_key


def _canonical_variant(template: Mapping[str, Any], variant: str | None) -> str:
    variants = template.get("accessibility") or {}
    if not variants:
        return "base"
    default = "base"
    if not variant:
        return default if default in variants else next(iter(variants))
    target = _normalise_key(variant)
    for key, payload in variants.items():
        label = payload.get("label")
        if _normalise_key(key) == target or _normalise_key(str(label or "")) == target:
            return key
    return default if default in variants else next(iter(variants))


def _resolve_subtype(
    template: Mapping[str, Any], subtype: str | None
) -> tuple[str, Mapping[str, Any]]:
    subtypes = template.get("subtypes") or {}
    key = _canonical_subtype(template, subtype)
    payload = _to_dict(subtypes.get(key) or {})
    payload.setdefault("overrides", {})
    return key, payload


def _resolve_variant(
    template: Mapping[str, Any], variant: str | None
) -> tuple[str, Mapping[str, Any]]:
    variants = template.get("accessibility") or {}
    key = _canonical_variant(template, variant)
    payload = _to_dict(variants.get(key) or {})
    payload.setdefault("overrides", {})
    return key, payload


def _normalise_key(value: str) -> str:
    text = (value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum())


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


def _normalise_anchor_ids(value: Any) -> list[str]:
    if value is None:
        return []
    result: list[str] = []
    if isinstance(value, Mapping):
        for key, entry in value.items():
            if isinstance(entry, Mapping):
                anchor_id = entry.get("id") or entry.get("anchor_id") or key
            else:
                anchor_id = key
            if anchor_id is None:
                continue
            anchor_id = str(anchor_id).strip()
            if anchor_id:
                result.append(anchor_id)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, Mapping):
                anchor_id = item.get("id") or item.get("anchor_id") or item.get("name")
            else:
                anchor_id = item
            if anchor_id is None:
                continue
            anchor_id = str(anchor_id).strip()
            if anchor_id:
                result.append(anchor_id)
    elif isinstance(value, str):
        for token in value.split(","):
            token = token.strip()
            if token:
                result.append(token)
    return sorted(dict.fromkeys(result))


def _extract_scene_anchors(
    scene: Mapping[str, Any]
) -> tuple[list[str], list[dict[str, Any]]]:
    anchors_raw = scene.get("anchors") or scene.get("event_anchors")
    if not anchors_raw:
        return [], []
    anchor_ids: list[str] = []
    details: list[dict[str, Any]] = []

    def _record(anchor_id: str, payload: Mapping[str, Any] | None) -> None:
        if not anchor_id:
            return
        if anchor_id not in anchor_ids:
            anchor_ids.append(anchor_id)
        if payload is not None:
            detail = {"id": anchor_id}
            label = payload.get("label") or payload.get("name")
            if isinstance(label, str) and label.strip():
                detail["label"] = label.strip()
            for axis in ("x", "y", "z"):
                if axis in payload:
                    try:
                        detail.setdefault("position", {})[axis] = float(payload[axis])
                    except (TypeError, ValueError):
                        continue
            details.append(detail)

    if isinstance(anchors_raw, Mapping):
        for key, value in anchors_raw.items():
            anchor_id = ""
            payload: Mapping[str, Any] | None = None
            if isinstance(value, Mapping):
                anchor_id = str(value.get("id") or key or "").strip()
                payload = value
            else:
                anchor_id = str(key or "").strip()
            _record(anchor_id, payload)
    elif isinstance(anchors_raw, (list, tuple, set)):
        for entry in anchors_raw:
            if isinstance(entry, Mapping):
                anchor_id = str(
                    entry.get("id") or entry.get("anchor_id") or entry.get("name") or ""
                ).strip()
                _record(anchor_id, entry)
            else:
                anchor_id = str(entry or "").strip()
                _record(anchor_id, None)
    return sorted(anchor_ids), details


def _subtype_catalog(template: Mapping[str, Any]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    subtypes = template.get("subtypes") or {}
    default_key = template.get("default_subtype") or (
        next(iter(subtypes)) if subtypes else "default"
    )
    for key, payload in subtypes.items():
        catalog.append(
            {
                "name": key,
                "label": payload.get("label", key.title()),
                "description": payload.get("description", ""),
                "default": key == default_key,
            }
        )
    return sorted(catalog, key=lambda item: item["label"].lower())


def _variant_catalog(template: Mapping[str, Any]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    variants = template.get("accessibility") or {}
    for key, payload in variants.items():
        catalog.append(
            {
                "name": key,
                "label": payload.get("label", key.title()),
                "description": payload.get("description", ""),
            }
        )
    return sorted(catalog, key=lambda item: item["name"])


def _normalise_props(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, payload in value.items():
        key_str = str(key)
        if isinstance(payload, Mapping):
            result[key_str] = {
                sub_key: (
                    _normalise_list(sub_value)
                    if isinstance(sub_value, (list, tuple, set))
                    and not isinstance(sub_value, (str, bytes))
                    else sub_value
                )
                for sub_key, sub_value in payload.items()
            }
        elif isinstance(payload, (list, tuple, set)) and not isinstance(
            payload, (str, bytes)
        ):
            result[key_str] = _normalise_list(payload)
        else:
            result[key_str] = payload
    return result


def _normalise_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)) and not isinstance(value, (str, bytes)):
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


def _stable_checksum(payload: Mapping[str, Any]) -> str:
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialised.encode("utf-8")).hexdigest()


__all__ = [
    "TEMPLATES",
    "available_templates",
    "plan",
    "template_catalog",
]
