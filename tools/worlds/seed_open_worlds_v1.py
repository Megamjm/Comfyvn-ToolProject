#!/usr/bin/env python3
# tools/worlds/seed_open_worlds_v1.py
# [ComfyVN Architect | Codex implementation script]
"""
Seeds CC0/PD starter worlds and asset policies into the repo.
Creates:
- comfyvn/schemas/*.json (world, scene, timeline, asset)
- comfyvn/policies/licensing_policy.yaml
- data/worlds/{grayshore,veiled_age,throne_of_echoes}/...
- defaults/worlds/*.json summary payloads for the legacy world loader
- defaults/characters/*.json seeds for CharacterManager bootstrap
- exports/assets/worlds/* empty buckets for future renders
Safe to run multiple times (idempotent-ish).
"""

import json
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "comfyvn" / "schemas"
POLICIES = ROOT / "comfyvn" / "policies"
WORLDS = ROOT / "data" / "worlds"
EXPORTS = ROOT / "exports" / "assets" / "worlds"
DEFAULT_WORLDS = ROOT / "defaults" / "worlds"
DEFAULT_CHARACTERS = ROOT / "defaults" / "characters"
CHARACTERS_DATA = ROOT / "data" / "characters"


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") == content:
            return
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write(path, json.dumps(payload, indent=2, ensure_ascii=False))


def jdump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _structured_map(entries, *, key_field: str = "id") -> dict:
    mapping: dict[str, dict] = {}
    if not isinstance(entries, list):
        return mapping
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get(key_field) or entry.get("name") or "").strip()
        if not key:
            continue
        payload = {k: v for k, v in entry.items() if k != key_field}
        mapping[key] = payload
    return mapping


def _build_world_default_payload(
    world_id: str,
    *,
    meta_yaml: str,
    summary_text: str,
    payload: dict,
    openers: list[dict],
    epochs: dict,
) -> dict:
    try:
        meta = yaml.safe_load(meta_yaml) or {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    title = str(meta.get("title") or world_id).strip()
    tags = [str(tag).strip() for tag in meta.get("tags", []) if str(tag).strip()]
    tone = ", ".join(tags) if tags else "Shared CC0 seed"
    locations = _structured_map(payload.get("locations_json") or [], key_field="id")
    factions = _structured_map(payload.get("factions_json") or [], key_field="id")
    lore_payload: dict = {
        "summary": summary_text.strip(),
        "notes": payload.get("notes", []),
    }
    if payload.get("oracle_tables"):
        lore_payload["oracle_tables"] = payload["oracle_tables"]
    if payload.get("quickplay_md"):
        lore_payload["rules_text"] = payload["quickplay_md"]
    timeline_epochs = epochs.get("epochs") or []
    prompt_templates = {
        "scene_hooks": payload.get("scene_hooks"),
        "session_zero": payload.get("session_zero"),
        "starter_md": payload.get("starters_md"),
        "opening_md": payload.get("opening_md"),
    }
    openers_payload = []
    for entry in openers:
        if not isinstance(entry, dict):
            continue
        openers_payload.append(
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "summary": entry.get("summary"),
                "location": entry.get("location"),
                "tags": entry.get("tags", []),
            }
        )
    return {
        "id": world_id,
        "name": title,
        "summary": summary_text.strip(),
        "tone": tone,
        "tags": tags,
        "rules": {
            "systems": meta.get("compat", {}).get("systems", []),
            "assets": meta.get("assets", {}),
            "license": meta.get("license", {}),
        },
        "locations": locations,
        "factions": factions,
        "lore": lore_payload,
        "openers": openers_payload,
        "timeline": timeline_epochs,
        "prompt_templates": {k: v for k, v in prompt_templates.items() if v},
        "source": meta.get("source") or {},
    }


def _character_record(world_id: str, entry: dict) -> dict:
    aspects = [str(value).strip() for value in entry.get("aspects", []) if value]
    tags = [world_id, *(str(entry.get("role") or "").split()), *aspects]
    notes = str(entry.get("notes") or "").strip()
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "role": entry.get("role"),
        "tags": [tag for tag in tags if tag],
        "culture": entry.get("culture"),
        "epoch": entry.get("epoch"),
        "aspects": aspects,
        "notes": notes or None,
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "meta": {
            "world_id": world_id,
            "source": "world_seed_v1",
        },
    }


# ---------- Schemas ----------
WORLD_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ComfyVN World",
    "type": "object",
    "required": ["id", "title", "license", "lore"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9_\\-]+$"},
        "title": {"type": "string"},
        "license": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "url": {"type": "string"},
            },
        },
        "source": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "url": {"type": "string"},
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}},
        "assets": {"type": "object"},
        "lore": {"type": "object"},
        "characters": {"type": ["object", "null"]},
        "play_examples": {"type": ["object", "null"]},
        "compat": {"type": ["object", "null"]},
        "notes": {"type": ["array", "null"], "items": {"type": "string"}},
    },
}

SCENE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ComfyVN Scene",
    "type": "object",
    "required": ["id", "world_id", "title", "beats"],
    "properties": {
        "id": {"type": "string"},
        "world_id": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "location": {"type": "string"},
        "timeline_ref": {"type": ["string", "null"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["narration", "dialogue", "choice", "effect"],
                    },
                    "speaker": {"type": ["string", "null"]},
                    "text": {"type": ["string", "null"]},
                    "assets": {
                        "type": ["array", "null"],
                        "items": {"$ref": "asset.schema.json"},
                    },
                },
            },
        },
    },
}

TIMELINE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ComfyVN Timeline",
    "type": "object",
    "required": ["world_id", "epochs"],
    "properties": {
        "world_id": {"type": "string"},
        "epochs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "start": {"type": ["string", "null"]},
                    "end": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
            },
        },
    },
}

ASSET_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ComfyVN Asset Metadata",
    "type": "object",
    "required": ["id", "type", "world_id", "path", "license"],
    "properties": {
        "id": {"type": "string"},
        "type": {
            "type": "string",
            "enum": ["portrait", "sprite", "background", "ui", "audio", "fx"],
        },
        "world_id": {"type": "string"},
        "path": {"type": "string"},
        "sidecar": {"type": ["string", "null"]},
        "hash": {"type": ["string", "null"]},
        "license": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "url": {"type": ["string", "null"]},
            },
        },
        "source": {
            "type": ["object", "null"],
            "properties": {
                "name": {"type": "string"},
                "url": {"type": "string"},
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}},
        "width": {"type": ["integer", "null"]},
        "height": {"type": ["integer", "null"]},
        "attribution": {"type": ["string", "null"]},
    },
}

# ---------- Policies ----------
LICENSING_POLICY = textwrap.dedent(
    """\
allowed_ids:
  - "CC0-1.0"
  - "Public Domain"
  - "CC-BY-4.0"
  - "CC-BY-SA-4.0"
require_attribution_for:
  - "CC-BY-4.0"
  - "CC-BY-SA-4.0"
block_art_for:
  - id: "CC-BY-SA-4.0"
    note: "Ship text/maps only unless artwork for that file is explicitly CC-BY-SA."
"""
)


# ---------- World payloads ----------
def grayshore():
    return {
        "world_yaml": textwrap.dedent(
            """\
        id: grayshore
        title: "Grayshore"
        license:
          id: "CC0-1.0"
          url: "https://creativecommons.org/publicdomain/zero/1.0/"
        source:
          name: "Community seed (PD/CC0)"
          url: ""
        tags: [fantasy, sandbox, coastal, factions]
        assets:
          maps: []
          art: []
        lore:
          summary_md: "lore/summary.md"
          factions_json: "lore/factions.json"
          locations_json: "lore/locations.json"
        play_examples:
          roleplay_threads:
            - "examples/session_zero_prompt.md"
            - "examples/scene_hooks.md"
        compat:
          systems: ["generic", "FateSRD-CCBY"]
      """
        ),
        "summary_md": "Grayshore is a wind-carved coast of coves and drowned forts. Trade runs on fog and rumor. The old road appears at low tide.",
        "factions_json": [
            {
                "id": "shipwrights_guild",
                "name": "Shipwrights' Guild",
                "influence": 3,
                "notes": "Controls drydocks and hardwood trade.",
            },
            {
                "id": "mistwardens",
                "name": "Mistwardens",
                "influence": 2,
                "notes": "Lantern-keepers who map fog channels at night.",
            },
        ],
        "locations_json": [
            {
                "id": "low_tide_road",
                "name": "Low-Tide Road",
                "notes": "Revealed twice nightly; stones slick with kelp.",
            },
            {
                "id": "drowned_fort",
                "name": "Drowned Fort",
                "notes": "Bell still tolls beneath the waterline.",
            },
        ],
        "session_zero": "You arrive where the road surfaces from the sea. A lantern bobs in the fog.",
        "scene_hooks": "- A bell tolls beneath the water.\n- A gull drops a wax-sealed key on your boot.\n- Scrimshaw maps hint at a shortcut.",
    }


def veiled_age():
    return {
        "world_yaml": textwrap.dedent(
            """\
        id: veiled_age
        title: "The Veiled Age"
        license:
          id: "Public Domain"
          url: ""
        source:
          name: "Community PD forum seed"
          url: ""
        tags: [fantasy, collaborative, mythic, city-states]
        assets:
          maps: []
          art: []
        lore:
          summary_md: "lore/summary.md"
          generators:
            - "tools/oracle_tables.json"
        play_examples:
          roleplay_threads:
            - "examples/starter-scenes.md"
        compat:
          systems: ["generic", "FateSRD-CCBY"]
      """
        ),
        "summary_md": "High fantasy in the afterglow of a vanished empire. City-states bargain with masked oracles; rivers remember old names.",
        "oracle_tables": {
            "omens": ["Cracked moon", "Salt in the well", "Lantern goes out"],
            "factions": ["Mask-Guild", "Archivists", "River Wardens"],
            "masks": ["Laughing Copper", "Blind Marble", "Horned Glass"],
        },
        "starters_md": textwrap.dedent(
            """\
        - Market of Masks at dusk; bidding on a prophecy fragment.
        - A river-spirit offers a bargain for your name.
        - A courier drops a signet ring etched with three waves.
      """
        ),
    }


def throne_of_echoes():
    return {
        "world_yaml": textwrap.dedent(
            """\
        id: throne_of_echoes
        title: "Throne of Echoes"
        license:
          id: "CC0-1.0"
          url: "https://creativecommons.org/publicdomain/zero/1.0/"
        source:
          name: "Wikidata (CC0) + Original CC0 text"
          url: "https://www.wikidata.org/"
        tags: [modern-fantasy, mythic, summons, factions]
        assets:
          maps: []
          art: []
        lore:
          summary_md: "lore/summary.md"
          rules_md: "rules/quickplay.md"
        characters:
          roster_json: "characters/roster.json"
        play_examples:
          roleplay_threads:
            - "examples/opening_scene.md"
        compat:
          systems: ["generic", "FateSRD-CCBY"]
        notes:
          - "Character facts can be extended from Wikidata (CC0). Portraits optional via Commons."
      """
        ),
        "summary_md": "When the city sleeps, the river counts the names of old heroes. Masks, sigils, relics—the bait and the binding. Seven factions. One night that keeps repeating until someone breaks the oath that started it.",
        "quickplay_md": textwrap.dedent(
            """\
        > Uses concepts compatible with the Fate Core SRD (CC-BY). Include Evil Hat's attribution block in credits.

        Aspects: Title • Legendary Deed • Fatal Flaw
        Approaches: Force • Finesse • Wit • Will
        Stunts: 2 per hero; +2 when Legendary Deed clearly applies.
        Stress: 3 boxes; Consequences: Mild/Moderate.
      """
        ),
        "opening_md": textwrap.dedent(
            """\
        [Scene] Empty museum at 2:07 AM.
        A cracked amphora hums. Air tastes like copper. A shadow speaks with your voice: "Name your price."
        What relic did you bring, and who answers it?
      """
        ),
        "roster_json": [
            {
                "id": "heracles",
                "name": "Heracles",
                "role": "Valor",
                "culture": "Greek mythology",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Heracles", "Origin: Greek"],
                "stunts": [],
                "notes": "Seed (CC0 data).",
            },
            {
                "id": "artemis",
                "name": "Artemis",
                "role": "Bow",
                "culture": "Greek mythology",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Artemis", "Origin: Greek"],
                "stunts": [],
                "notes": "Seed (CC0 data).",
            },
            {
                "id": "achilles",
                "name": "Achilles",
                "role": "Blade",
                "culture": "Greek mythology",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Achilles", "Origin: Greek"],
                "stunts": [],
                "notes": "Seed (CC0 data).",
            },
            {
                "id": "cu_chulainn",
                "name": "Cú Chulainn",
                "role": "Blade",
                "culture": "Irish mythology",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Cú Chulainn", "Origin: Irish"],
                "stunts": [],
                "notes": "Seed (CC0 data).",
            },
            {
                "id": "morgan_le_fay",
                "name": "Morgan le Fay",
                "role": "Arcana",
                "culture": "Arthurian legend",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Morgan le Fay", "Origin: Arthurian"],
                "stunts": [],
                "notes": "Seed (CC0 data).",
            },
            {
                "id": "sun_wukong",
                "name": "Sun Wukong",
                "role": "Shadow",
                "culture": "Chinese mythology",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Sun Wukong", "Origin: Chinese"],
                "stunts": [],
                "notes": "Journey to the West is public domain; facts drawn from PD translations.",
            },
            {
                "id": "gilgamesh",
                "name": "Gilgamesh",
                "role": "Valor",
                "culture": "Mesopotamian mythology",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Gilgamesh", "Origin: Mesopotamian"],
                "stunts": [],
                "notes": "Epic of Gilgamesh is public domain.",
            },
            {
                "id": "joan_of_arc",
                "name": "Joan of Arc",
                "role": "Will",
                "culture": "French history",
                "epoch": {"birth": "1412-01-06", "death": "1431-05-30"},
                "aspects": ["Legendary: Joan of Arc", "Origin: French"],
                "stunts": [],
                "notes": "Historical figure in the public domain.",
            },
            {
                "id": "anansi",
                "name": "Anansi",
                "role": "Wit",
                "culture": "Akan folklore",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Anansi", "Origin: Akan"],
                "stunts": [],
                "notes": "Folktales recorded in the public domain.",
            },
            {
                "id": "thor",
                "name": "Thor",
                "role": "Force",
                "culture": "Norse mythology",
                "epoch": {"birth": None, "death": None},
                "aspects": ["Legendary: Thor", "Origin: Norse"],
                "stunts": [],
                "notes": "Poetic and Prose Edda translations are public domain.",
            },
        ],
    }


# ---------- Timelines ----------
GRAYSHORE_EPOCHS = {
    "world_id": "grayshore",
    "epochs": [
        {
            "id": "tide_age",
            "label": "Tide Age",
            "start": None,
            "end": None,
            "notes": "Drowned forts and fog lanes.",
        },
        {
            "id": "lantern_wars",
            "label": "Lantern Wars",
            "start": None,
            "end": None,
            "notes": "Guild skirmishes in the mist.",
        },
    ],
}
VEILED_AGE_EPOCHS = {
    "world_id": "veiled_age",
    "epochs": [
        {
            "id": "afterglow",
            "label": "Afterglow",
            "notes": "Empire gone; oracles bargain in alleys.",
        },
        {
            "id": "river_pacts",
            "label": "River Pacts",
            "notes": "Cities swear by old waters.",
        },
    ],
}
TOE_EPOCHS = {
    "world_id": "throne_of_echoes",
    "epochs": [
        {
            "id": "first_oath",
            "label": "First Oath",
            "notes": "The binding that soured the city.",
        },
        {
            "id": "repeating_night",
            "label": "Repeating Night",
            "notes": "The night that loops until the oath breaks.",
        },
    ],
}


# ---------- Scene Openers (multi-world) ----------
OPENERS = {
    "grayshore": [
        {
            "id": "gs_low_tide_road",
            "world_id": "grayshore",
            "title": "Low-Tide Road",
            "summary": "The road rises from the sea.",
            "location": "Shore Causeway",
            "tags": ["mystery", "coast"],
            "beats": [
                {
                    "type": "narration",
                    "speaker": None,
                    "text": "Fog thins over the slick stones.",
                },
                {
                    "type": "dialogue",
                    "speaker": "Lantern-Warden",
                    "text": "If you keep walking, choose who you leave behind.",
                },
                {
                    "type": "choice",
                    "text": "Do you cross now or light a signal lantern?",
                },
            ],
        },
        {
            "id": "gs_drowned_fort",
            "world_id": "grayshore",
            "title": "Drowned Fort Bell",
            "summary": "Underwater bell tolls.",
            "location": "Ruined Fort",
            "tags": ["eerie"],
            "beats": [
                {"type": "narration", "text": "A bell tolls beneath black water."}
            ],
        },
    ],
    "veiled_age": [
        {
            "id": "va_market_masks",
            "world_id": "veiled_age",
            "title": "Market of Masks",
            "summary": "Bid on a prophecy shard.",
            "location": "Mask Bazaar",
            "tags": ["intrigue"],
            "beats": [
                {"type": "narration", "text": "Masks glitter under lamplight."},
                {
                    "type": "dialogue",
                    "speaker": "Auctioneer",
                    "text": "Lot Seven: a line from a tomorrow that almost happened.",
                },
            ],
        }
    ],
    "throne_of_echoes": [
        {
            "id": "toe_museum",
            "world_id": "throne_of_echoes",
            "title": "Museum after hours",
            "summary": "Relic hums; voice bargains.",
            "location": "City Museum",
            "tags": ["mythic", "modern"],
            "beats": [
                {"type": "narration", "text": "Air tastes like copper."},
                {"type": "dialogue", "speaker": "Echo", "text": "Name your price."},
            ],
        }
    ],
}


def seed_schemas_and_policies():
    write(SCHEMAS / "world.schema.json", jdump(WORLD_SCHEMA))
    write(SCHEMAS / "scene.schema.json", jdump(SCENE_SCHEMA))
    write(SCHEMAS / "timeline.schema.json", jdump(TIMELINE_SCHEMA))
    write(SCHEMAS / "asset.schema.json", jdump(ASSET_SCHEMA))
    write(POLICIES / "licensing_policy.yaml", LICENSING_POLICY)


def seed_world(folder: Path, payload: dict, openers: list, epochs: dict):
    (folder / "lore").mkdir(parents=True, exist_ok=True)
    (folder / "examples").mkdir(parents=True, exist_ok=True)
    (folder / "timeline").mkdir(parents=True, exist_ok=True)

    write(folder / "world.yaml", payload["world_yaml"])
    write(folder / "lore" / "summary.md", payload["summary_md"])
    if folder.name == "grayshore":
        write(folder / "lore" / "factions.json", jdump(payload["factions_json"]))
        write(folder / "lore" / "locations.json", jdump(payload["locations_json"]))
        write(folder / "examples" / "session_zero_prompt.md", payload["session_zero"])
        write(folder / "examples" / "scene_hooks.md", payload["scene_hooks"])
    if folder.name == "veiled_age":
        write(folder / "tools" / "oracle_tables.json", jdump(payload["oracle_tables"]))
        write(folder / "examples" / "starter-scenes.md", payload["starters_md"])
    if folder.name == "throne_of_echoes":
        (folder / "rules").mkdir(exist_ok=True)
        (folder / "characters").mkdir(exist_ok=True)
        write(folder / "rules" / "quickplay.md", payload["quickplay_md"])
        write(folder / "examples" / "opening_scene.md", payload["opening_md"])
        write(folder / "characters" / "roster.json", jdump(payload["roster_json"]))

    write(folder / "timeline" / "epochs.json", jdump(epochs))

    scenedir = folder / "examples"
    for sc in openers:
        write(scenedir / f"{sc['id']}.scene.json", jdump(sc))


def seed_exports_buckets(world_ids):
    for world_id in world_ids:
        for sub in ["portraits", "sprites", "backgrounds", "ui", "audio", "meta"]:
            (EXPORTS / world_id / sub).mkdir(parents=True, exist_ok=True)


def seed_default_world_payloads(world_entries):
    DEFAULT_WORLDS.mkdir(parents=True, exist_ok=True)
    for entry in world_entries:
        payload = _build_world_default_payload(
            entry["id"],
            meta_yaml=entry["payload"]["world_yaml"],
            summary_text=entry["payload"]["summary_md"],
            payload=entry["payload"],
            openers=entry["openers"],
            epochs=entry["epochs"],
        )
        write_json(DEFAULT_WORLDS / f"{entry['id']}.json", payload)


def seed_default_characters(world_entries):
    DEFAULT_CHARACTERS.mkdir(parents=True, exist_ok=True)
    CHARACTERS_DATA.mkdir(parents=True, exist_ok=True)
    for entry in world_entries:
        roster = entry["payload"].get("roster_json")
        if not roster:
            continue
        world_id = entry["id"]
        for character in roster:
            record = _character_record(world_id, character)
            char_id = record.get("id")
            if not char_id:
                continue
            write_json(DEFAULT_CHARACTERS / f"{char_id}.json", record)
            runtime_dir = CHARACTERS_DATA / char_id
            runtime_dir.mkdir(parents=True, exist_ok=True)
            write_json(runtime_dir / "character.json", record)


def main():
    seed_schemas_and_policies()

    seeded_worlds = []

    payload_grayshore = grayshore()
    seed_world(
        WORLDS / "grayshore", payload_grayshore, OPENERS["grayshore"], GRAYSHORE_EPOCHS
    )
    seeded_worlds.append(
        {
            "id": "grayshore",
            "payload": payload_grayshore,
            "openers": OPENERS["grayshore"],
            "epochs": GRAYSHORE_EPOCHS,
        }
    )

    payload_veiled = veiled_age()
    seed_world(
        WORLDS / "veiled_age", payload_veiled, OPENERS["veiled_age"], VEILED_AGE_EPOCHS
    )
    seeded_worlds.append(
        {
            "id": "veiled_age",
            "payload": payload_veiled,
            "openers": OPENERS["veiled_age"],
            "epochs": VEILED_AGE_EPOCHS,
        }
    )

    payload_toe = throne_of_echoes()
    seed_world(
        WORLDS / "throne_of_echoes",
        payload_toe,
        OPENERS["throne_of_echoes"],
        TOE_EPOCHS,
    )
    seeded_worlds.append(
        {
            "id": "throne_of_echoes",
            "payload": payload_toe,
            "openers": OPENERS["throne_of_echoes"],
            "epochs": TOE_EPOCHS,
        }
    )

    seed_exports_buckets([world["id"] for world in seeded_worlds])
    seed_default_world_payloads(seeded_worlds)
    seed_default_characters(seeded_worlds)
    print("✅ Seed complete.")


if __name__ == "__main__":
    main()
