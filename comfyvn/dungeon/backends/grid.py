from __future__ import annotations

import hashlib
import random
import time
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

__all__ = ["GridBackend"]


class GridBackend:
    """Deterministic grid-crawler backend."""

    name = "grid"
    version = "v1"
    anchor_prefix = "grid://room/"

    _ROOM_DESCRIPTORS: Tuple[str, ...] = (
        "A mossy chamber with low vaulted ceilings.",
        "Corridor framed by cracked stone arches.",
        "Circular hub lit by faint bioluminescent fungi.",
        "Collapsed hall; rubble narrows the passage.",
        "Storage alcove lined with weathered crates.",
        "Flooded junction — ankle-deep shimmering water.",
        "Gallery of broken statues facing one another.",
        "Dusty barracks; bunks overturned long ago.",
        "Workshop scarred by scorch marks and rust.",
        "Observation deck overlooking a dark chasm.",
    )

    _HAZARD_TEMPLATES: Tuple[Dict[str, Any], ...] = (
        {
            "type": "trap",
            "names": ("Pressure Plate", "Spiked Grate", "Pendulum Scythes"),
            "reward": {
                "id": "salvaged_springs",
                "name": "Salvaged Springs",
                "rarity": "common",
            },
        },
        {
            "type": "puzzle",
            "names": ("Runic Lock", "Mirror Alignment", "Arcane Dial"),
            "reward": {
                "id": "glyph_fragment",
                "name": "Glyph Fragment",
                "rarity": "uncommon",
            },
        },
        {
            "type": "ambush",
            "names": ("Gloom Wisp", "Hollow Sentinel", "Cinder Shade"),
            "reward": {"id": "soulpearl", "name": "Soulpearl", "rarity": "rare"},
        },
    )

    _ENCOUNTER_ROSTER: Tuple[Dict[str, Any], ...] = (
        {"name": "Hollow Sentinel", "type": "construct", "power_mod": 2},
        {"name": "Gloom Wisp", "type": "specter", "power_mod": 1},
        {"name": "Shardscale Raider", "type": "raider", "power_mod": 3},
        {"name": "Runic Echo", "type": "anomaly", "power_mod": 0},
    )

    _LOOT_TEMPLATES: Tuple[Dict[str, Any], ...] = (
        {"id": "restorative_draft", "name": "Restorative Draft", "rarity": "common"},
        {"id": "ancient_coin", "name": "Ancient Coin", "rarity": "uncommon"},
        {"id": "lumicrystal", "name": "Lumicrystal", "rarity": "rare"},
        {"id": "forgotten_map", "name": "Forgotten Map Shard", "rarity": "uncommon"},
        {"id": "tinker_cache", "name": "Tinker's Cache", "rarity": "rare"},
    )

    _DIRECTION_OFFSETS: Mapping[str, Tuple[int, int]] = {
        "north": (0, -1),
        "south": (0, 1),
        "west": (-1, 0),
        "east": (1, 0),
    }

    def enter(
        self,
        *,
        seed: int,
        options: Mapping[str, Any],
        rng: random.Random,
        context: Mapping[str, Any],
    ) -> Tuple[MutableMapping[str, Any], Mapping[str, Any]]:
        width = self._clamp_dimension(options.get("width"), default=5)
        height = self._clamp_dimension(options.get("height"), default=5)
        start = self._coerce_start(options.get("start"), width, height)
        state: MutableMapping[str, Any] = {
            "seed": int(seed),
            "width": width,
            "height": height,
            "position": list(start),
            "visited": {},
            "resolved_hazards": {},
            "collected_loot": [],
            "active_encounter": None,
            "steps": 0,
            "created_at": time.time(),
        }
        room = self.describe_room(state)
        anchor = room["anchor"]
        state["visited"][anchor] = {"entered_at": time.time(), "visits": 1}
        return state, room

    # ------------------------------------------------------------------ room helpers
    def describe_room(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        x, y = self._position(state)
        width = int(state["width"])
        height = int(state["height"])
        anchor = self._room_anchor(x, y)
        profile = self._cell_profile(int(state["seed"]), x, y)
        resolved_map: Mapping[str, Any] = state.get("resolved_hazards", {})
        collected: Iterable[str] = state.get("collected_loot", ())

        hazards: List[Dict[str, Any]] = []
        for idx, hazard in enumerate(profile["hazards"]):
            hazard_id = f"{anchor}hazard/{idx}"
            resolution = resolved_map.get(hazard_id)
            status = "active"
            outcome = None
            if resolution:
                status = resolution.get("status", "resolved")
                outcome = resolution.get("outcome")
            hazards.append(
                {
                    "id": hazard_id,
                    "name": hazard["name"],
                    "type": hazard["type"],
                    "severity": hazard["severity"],
                    "status": status,
                    "outcome": outcome,
                    "anchor": f"{hazard_id}",
                    "reward": hazard.get("reward"),
                }
            )

        loot: List[Dict[str, Any]] = []
        for idx, item in enumerate(profile["loot"]):
            loot_id = f"{anchor}loot/{idx}"
            loot.append(
                {
                    "id": loot_id,
                    "name": item["name"],
                    "rarity": item["rarity"],
                    "collected": bool(loot_id in collected),
                }
            )

        exits = []
        for direction, (dx, dy) in self._DIRECTION_OFFSETS.items():
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                exits.append(direction)

        return {
            "coords": [x, y],
            "anchor": anchor,
            "desc": profile["desc"],
            "exits": exits,
            "hazards": hazards,
            "loot": loot,
        }

    # ------------------------------------------------------------------ state transitions
    def step(
        self,
        state: MutableMapping[str, Any],
        *,
        direction: str,
        rng: random.Random,
    ) -> Tuple[MutableMapping[str, Any], Mapping[str, Any], Dict[str, Any]]:
        direction_key = direction.lower().strip()
        if direction_key not in self._DIRECTION_OFFSETS:
            raise ValueError(f"Unsupported direction '{direction}'")

        dx, dy = self._DIRECTION_OFFSETS[direction_key]
        width = int(state["width"])
        height = int(state["height"])
        x, y = self._position(state)
        nx, ny = x + dx, y + dy
        movement = {
            "from": [x, y],
            "to": [x, y],
            "blocked": False,
            "direction": direction_key,
        }
        if nx < 0 or ny < 0 or nx >= width or ny >= height:
            movement["blocked"] = True
            movement["reason"] = "wall"
            return state, self.describe_room(state), movement

        state["position"] = [nx, ny]
        state["steps"] = int(state.get("steps", 0)) + 1
        state["active_encounter"] = None
        movement["to"] = [nx, ny]

        room = self.describe_room(state)
        anchor = room["anchor"]
        visited = state.setdefault("visited", {})
        entry = visited.setdefault(anchor, {"entered_at": time.time(), "visits": 0})
        entry["visits"] = int(entry.get("visits", 0)) + 1
        entry.setdefault("last_seen_at", time.time())
        entry["last_seen_at"] = time.time()

        return state, room, movement

    def collect_loot(
        self, state: MutableMapping[str, Any], loot_ids: Iterable[str]
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        current_room = self.describe_room(state)
        wanted = {loot_id for loot_id in loot_ids}
        inventory = state.setdefault("collected_loot", [])
        for item in current_room["loot"]:
            if item["id"] not in wanted:
                continue
            if item["id"] in inventory:
                continue
            inventory.append(item["id"])
            item = dict(item)
            item["collected"] = True
            collected.append(item)
        return collected

    def encounter_start(
        self,
        state: MutableMapping[str, Any],
        *,
        hazard_id: Optional[str],
        rng: random.Random,
    ) -> Dict[str, Any]:
        if state.get("active_encounter"):
            return state["active_encounter"]  # type: ignore[return-value]

        room = self.describe_room(state)
        target_id = hazard_id
        hazard_payload = None
        for entry in room["hazards"]:
            if entry["status"] != "active":
                continue
            if target_id and entry["id"] != target_id:
                continue
            hazard_payload = entry
            break
        if not hazard_payload:
            raise ValueError("No active hazard available in this room")

        encounter_seed = self._hash_int(
            int(state["seed"]), hazard_payload["id"], "encounter"
        )
        roster = self._ENCOUNTER_ROSTER[encounter_seed % len(self._ENCOUNTER_ROSTER)]
        difficulty = int(hazard_payload["severity"])
        foe_power = max(1, difficulty + roster["power_mod"])
        encounter = {
            "id": hazard_payload["id"],
            "anchor": f"{hazard_payload['anchor']}/encounter",
            "hazard": hazard_payload,
            "enemy": {
                "name": roster["name"],
                "type": roster["type"],
                "power": foe_power,
            },
            "difficulty": difficulty,
            "seed": encounter_seed,
        }
        state["active_encounter"] = encounter
        return encounter

    def resolve(
        self,
        state: MutableMapping[str, Any],
        *,
        outcome: Mapping[str, Any],
        rng: random.Random,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Mapping[str, Any]]:
        encounter = state.get("active_encounter")
        if not encounter:
            raise ValueError("No active encounter to resolve")
        hazard_id = encounter["id"]
        decision = str(outcome.get("result") or outcome.get("outcome") or "").strip()
        if decision not in {"victory", "defeat", "escape"}:
            raise ValueError("Outcome must be victory|defeat|escape")
        roll = rng.random()
        xp = int(encounter["difficulty"] * 10)
        summary = {
            "encounter_id": hazard_id,
            "outcome": decision,
            "roll": roll,
            "xp": xp,
        }
        status = "resolved" if decision == "victory" else "consumed"
        if decision == "escape":
            status = "escaped"
        resolution = {
            "status": status,
            "outcome": decision,
            "roll": roll,
            "xp": xp,
            "resolved_at": time.time(),
        }
        state.setdefault("resolved_hazards", {})[hazard_id] = resolution
        state["active_encounter"] = None

        loot_results: List[Dict[str, Any]] = []
        reward = encounter["hazard"].get("reward")
        if decision == "victory" and reward:
            inventory = state.setdefault("collected_loot", [])
            reward_entry = dict(reward)
            reward_id = f"{hazard_id}/reward::{reward_entry.get('id', 'reward')}"
            reward_entry["id"] = reward_id
            reward_entry["source"] = "encounter"
            if reward_id not in inventory:
                inventory.append(reward_id)
            loot_results.append(reward_entry)

        room = self.describe_room(state)
        return summary, loot_results, room

    def finalize(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        visited = state.get("visited", {})
        resolved = state.get("resolved_hazards", {})
        loot_ids = state.get("collected_loot", [])
        remaining = 0
        for x in range(int(state["width"])):
            for y in range(int(state["height"])):
                profile = self._cell_profile(int(state["seed"]), x, y)
                for idx, _ in enumerate(profile["hazards"]):
                    hazard_id = f"{self._room_anchor(x, y)}hazard/{idx}"
                    if hazard_id not in resolved:
                        remaining += 1
        return {
            "rooms_explored": len(visited),
            "hazards_resolved": len(
                [r for r in resolved.values() if r.get("status") == "resolved"]
            ),
            "hazards_remaining": remaining,
            "loot_collected": loot_ids,
        }

    def snapshot(
        self,
        state: Mapping[str, Any],
        *,
        context: Mapping[str, Any],
        path: Iterable[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        x, y = self._position(state)
        profile = self._cell_profile(int(state["seed"]), x, y)
        return {
            "mode": self.name,
            "version": self.version,
            "coords": [x, y],
            "grid": {"width": int(state["width"]), "height": int(state["height"])},
            "room": {
                "anchor": self._room_anchor(x, y),
                "desc": profile["desc"],
                "hazards": profile["hazards"],
                "loot": profile["loot"],
            },
            "path": list(path),
            "context": dict(context),
        }

    # ------------------------------------------------------------------ utilities
    def _room_anchor(self, x: int, y: int) -> str:
        return f"{self.anchor_prefix}{x}:{y}"

    def _position(self, state: Mapping[str, Any]) -> Tuple[int, int]:
        pos = state.get("position", (0, 0))
        if isinstance(pos, Mapping):
            x = int(pos.get("x", 0))
            y = int(pos.get("y", 0))
        else:
            x = int(pos[0])
            y = int(pos[1])
        return x, y

    def _clamp_dimension(self, value: Any, *, default: int) -> int:
        try:
            coerced = int(value)
        except Exception:
            coerced = default
        return max(3, min(12, coerced))

    def _coerce_start(self, value: Any, width: int, height: int) -> Tuple[int, int]:
        if isinstance(value, Mapping):
            x = value.get("x")
            y = value.get("y")
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            x, y = value[0], value[1]
        else:
            x = y = None
        try:
            sx = int(x)
        except Exception:
            sx = width // 2
        try:
            sy = int(y)
        except Exception:
            sy = height // 2
        return max(0, min(width - 1, sx)), max(0, min(height - 1, sy))

    def _hash_int(self, *parts: Any) -> int:
        text = ":".join(str(part) for part in parts).encode("utf-8")
        digest = hashlib.sha256(text).digest()
        return int.from_bytes(digest[:8], "big")

    def _cell_profile(self, seed: int, x: int, y: int) -> Dict[str, Any]:
        rng = random.Random(self._hash_int(seed, x, y))
        desc = self._ROOM_DESCRIPTORS[int(rng.random() * len(self._ROOM_DESCRIPTORS))]
        hazards: List[Dict[str, Any]] = []
        hazard_rolls = int(rng.random() * 100)
        hazard_count = 0
        if hazard_rolls < 45:
            hazard_count = 1
        if hazard_rolls < 12:
            hazard_count = 2
        for idx in range(hazard_count):
            template = self._HAZARD_TEMPLATES[
                (idx + hazard_rolls) % len(self._HAZARD_TEMPLATES)
            ]
            name = template["names"][(hazard_rolls + idx) % len(template["names"])]
            severity = 1 + (hazard_rolls + idx * 3) % 4
            hazards.append(
                {
                    "name": name,
                    "type": template["type"],
                    "severity": severity,
                    "reward": template.get("reward"),
                }
            )

        loot: List[Dict[str, Any]] = []
        loot_roll = int(rng.random() * 100)
        if loot_roll % 3 == 0:
            template = self._LOOT_TEMPLATES[loot_roll % len(self._LOOT_TEMPLATES)]
            loot.append(dict(template))
        if loot_roll % 17 == 0:
            template = self._LOOT_TEMPLATES[(loot_roll + 2) % len(self._LOOT_TEMPLATES)]
            loot.append(dict(template))

        return {"desc": desc, "hazards": hazards, "loot": loot}
