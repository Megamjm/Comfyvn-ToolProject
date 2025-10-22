from __future__ import annotations

import hashlib
import random
import time
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

__all__ = ["DoomLiteBackend"]


class DoomLiteBackend:
    """WebGL-friendly DOOM-lite bridge backend."""

    name = "doomlite"
    version = "v1"
    anchor_prefix = "doomlite://sector/"

    _SECTOR_DESCRIPTORS: Tuple[str, ...] = (
        "Entry gantry lit by flickering hazard strobes.",
        "Maintenance hallway with pipes rattling overhead.",
        "Storage hub stacked with ammunition crates.",
        "Collapsed tram station opening into lava vents.",
        "Observation deck facing a containment cylinder.",
        "Control nexus lined with holo-terminals.",
    )

    _HAZARD_ARCHETYPES: Tuple[Dict[str, Any], ...] = (
        {
            "type": "combat",
            "names": ("Imp Echo", "Shield Drone", "Blaze Stalker"),
            "reward": {
                "id": "ammo_cache",
                "name": "Ammunition Cache",
                "rarity": "common",
            },
        },
        {
            "type": "environment",
            "names": ("Coolant Leak", "Arc Coil Surge", "Vent Purge"),
            "reward": {
                "id": "coolant_core",
                "name": "Coolant Core",
                "rarity": "uncommon",
            },
        },
        {
            "type": "challenge",
            "names": ("Drone Arena", "Turret Gauntlet", "Shielded Array"),
            "reward": {
                "id": "prototype_mod",
                "name": "Prototype Mod",
                "rarity": "rare",
            },
        },
    )

    _LOOT_TABLE: Tuple[Dict[str, Any], ...] = (
        {"id": "medkit", "name": "Field Medkit", "rarity": "common"},
        {"id": "armor_plate", "name": "Reactive Armor Plate", "rarity": "uncommon"},
        {"id": "overcharge_cell", "name": "Overcharge Cell", "rarity": "rare"},
        {"id": "map_hololog", "name": "Sector Hololog", "rarity": "uncommon"},
    )

    _ENEMY_ROSTER: Tuple[Dict[str, Any], ...] = (
        {"name": "Imp Echo", "type": "demon", "power_mod": 1},
        {"name": "Stalker Unit", "type": "autonomous", "power_mod": 2},
        {"name": "Plasma Revenant", "type": "demon", "power_mod": 3},
        {"name": "Bulwark Drone", "type": "autonomous", "power_mod": 2},
    )

    _CAMERA_STEP = 1.5

    def enter(
        self,
        *,
        seed: int,
        options: Mapping[str, Any],
        rng: random.Random,
        context: Mapping[str, Any],
    ) -> Tuple[MutableMapping[str, Any], Mapping[str, Any]]:
        sector_count = self._coerce_sector_count(options.get("sectors"))
        state: MutableMapping[str, Any] = {
            "seed": int(seed),
            "sectors": [self._sector_profile(seed, idx) for idx in range(sector_count)],
            "sector_index": 0,
            "camera": {
                "position": [0.0, 1.6, 0.0],
                "rotation": [0.0, 0.0, 0.0],
                "fov": 75.0,
            },
            "player": {
                "position": [0.0, 0.0, 0.0],
                "heading": 0.0,
            },
            "resolved_hazards": {},
            "collected_loot": [],
            "active_encounter": None,
            "steps": 0,
            "created_at": time.time(),
        }
        room = self.describe_room(state)
        return state, room

    # ------------------------------------------------------------------ room helpers
    def describe_room(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        index = int(state.get("sector_index", 0))
        sectors: List[Mapping[str, Any]] = state.get("sectors", [])
        if not sectors:
            sectors = [self._sector_profile(int(state["seed"]), 0)]
        sector = sectors[index]
        anchor = self._sector_anchor(index)
        resolved = state.get("resolved_hazards", {})
        collected = set(state.get("collected_loot", ()))

        hazards: List[Dict[str, Any]] = []
        for idx, hazard in enumerate(sector["hazards"]):
            hazard_id = f"{anchor}hazard/{idx}"
            resolution = resolved.get(hazard_id)
            status = resolution.get("status") if resolution else "active"
            outcome = resolution.get("outcome") if resolution else None
            hazards.append(
                {
                    "id": hazard_id,
                    "name": hazard["name"],
                    "type": hazard["type"],
                    "severity": hazard["severity"],
                    "status": status,
                    "outcome": outcome,
                    "anchor": hazard_id,
                    "reward": hazard.get("reward"),
                }
            )

        loot: List[Dict[str, Any]] = []
        for idx, entry in enumerate(sector["loot"]):
            loot_id = f"{anchor}loot/{idx}"
            loot.append(
                {
                    "id": loot_id,
                    "name": entry["name"],
                    "rarity": entry["rarity"],
                    "collected": loot_id in collected,
                }
            )

        exits = []
        if index < len(sectors) - 1:
            exits.append("forward")
        if index > 0:
            exits.append("back")
        exits.extend(["left", "right"])

        return {
            "coords": [index, 0],
            "anchor": anchor,
            "desc": sector["desc"],
            "exits": exits,
            "hazards": hazards,
            "loot": loot,
            "lights": sector["lights"],
        }

    # ------------------------------------------------------------------ state transitions
    def step(
        self,
        state: MutableMapping[str, Any],
        *,
        direction: str,
        rng: random.Random,
    ) -> Tuple[MutableMapping[str, Any], Mapping[str, Any], Dict[str, Any]]:
        key = direction.lower().strip()
        index = int(state.get("sector_index", 0))
        sectors = state.get("sectors", [])
        max_index = len(sectors) - 1
        movement = {
            "from": [index, 0],
            "to": [index, 0],
            "blocked": False,
            "direction": key,
        }
        if key in {"forward", "north", "advance"}:
            if index >= max_index:
                movement["blocked"] = True
                movement["reason"] = "end_of_corridor"
            else:
                index += 1
                movement["to"] = [index, 0]
                state["sector_index"] = index
                state["steps"] = int(state.get("steps", 0)) + 1
                state["active_encounter"] = None
                camera = state.setdefault("camera", {})
                position = list(camera.get("position", [0.0, 1.6, 0.0]))
                position[2] -= self._CAMERA_STEP
                camera["position"] = position
        elif key in {"back", "south", "retreat"}:
            if index <= 0:
                movement["blocked"] = True
                movement["reason"] = "start_of_corridor"
            else:
                index -= 1
                movement["to"] = [index, 0]
                state["sector_index"] = index
                state["steps"] = int(state.get("steps", 0)) + 1
                state["active_encounter"] = None
                camera = state.setdefault("camera", {})
                position = list(camera.get("position", [0.0, 1.6, 0.0]))
                position[2] += self._CAMERA_STEP
                camera["position"] = position
        elif key in {"left", "strafe_left", "west"}:
            camera = state.setdefault("camera", {})
            position = list(camera.get("position", [0.0, 1.6, 0.0]))
            position[0] -= self._CAMERA_STEP / 2.0
            camera["position"] = position
            rotation = list(camera.get("rotation", [0.0, 0.0, 0.0]))
            rotation[1] -= 10.0
            camera["rotation"] = rotation
        elif key in {"right", "strafe_right", "east"}:
            camera = state.setdefault("camera", {})
            position = list(camera.get("position", [0.0, 1.6, 0.0]))
            position[0] += self._CAMERA_STEP / 2.0
            camera["position"] = position
            rotation = list(camera.get("rotation", [0.0, 0.0, 0.0]))
            rotation[1] += 10.0
            camera["rotation"] = rotation
        else:
            raise ValueError(f"Unsupported direction '{direction}'")

        room = self.describe_room(state)
        return state, room, movement

    def collect_loot(
        self, state: MutableMapping[str, Any], loot_ids: Iterable[str]
    ) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        room = self.describe_room(state)
        wanted = {loot_id for loot_id in loot_ids}
        inventory = state.setdefault("collected_loot", [])
        for item in room["loot"]:
            if item["id"] not in wanted:
                continue
            if item["id"] in inventory:
                continue
            inventory.append(item["id"])
            result = dict(item)
            result["collected"] = True
            payload.append(result)
        return payload

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
        target = hazard_id
        hazard_payload = None
        for entry in room["hazards"]:
            if entry["status"] != "active":
                continue
            if target and entry["id"] != target:
                continue
            hazard_payload = entry
            break
        if not hazard_payload:
            raise ValueError("No active hazard available in this sector")

        encounter_seed = self._hash_int(
            int(state["seed"]), hazard_payload["id"], "encounter"
        )
        roster = self._ENEMY_ROSTER[encounter_seed % len(self._ENEMY_ROSTER)]
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
        xp = int(encounter["difficulty"] * 12)
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
        resolved = state.get("resolved_hazards", {})
        loot_ids = state.get("collected_loot", [])
        remaining = 0
        sectors = state.get("sectors", [])
        for index, sector in enumerate(sectors):
            for idx, _ in enumerate(sector["hazards"]):
                hazard_id = f"{self._sector_anchor(index)}hazard/{idx}"
                if hazard_id not in resolved:
                    remaining += 1
        return {
            "sectors_traversed": int(state.get("sector_index", 0)) + 1,
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
        index = int(state.get("sector_index", 0))
        sectors = state.get("sectors", [])
        if not sectors:
            sectors = [self._sector_profile(int(state["seed"]), 0)]
        sector = sectors[index]
        return {
            "mode": self.name,
            "version": self.version,
            "sector_index": index,
            "camera": dict(state.get("camera", {})),
            "player": dict(state.get("player", {})),
            "sector": {
                "anchor": self._sector_anchor(index),
                "desc": sector["desc"],
                "lights": sector["lights"],
                "hazards": sector["hazards"],
                "loot": sector["loot"],
            },
            "path": list(path),
            "context": dict(context),
        }

    # ------------------------------------------------------------------ helpers
    def _sector_anchor(self, index: int) -> str:
        return f"{self.anchor_prefix}{index}"

    def _hash_int(self, *parts: Any) -> int:
        text = ":".join(str(part) for part in parts).encode("utf-8")
        digest = hashlib.sha256(text).digest()
        return int.from_bytes(digest[:8], "big")

    def _coerce_sector_count(self, value: Any) -> int:
        try:
            count = int(value)
        except Exception:
            count = 6
        return max(3, min(12, count))

    def _sector_profile(self, seed: int, index: int) -> Dict[str, Any]:
        rng = random.Random(self._hash_int(seed, "sector", index))
        desc = self._SECTOR_DESCRIPTORS[
            int(rng.random() * len(self._SECTOR_DESCRIPTORS))
        ]
        hazards: List[Dict[str, Any]] = []
        hazard_rolls = int(rng.random() * 100)
        hazard_count = 1 if hazard_rolls % 4 else 0
        if hazard_rolls % 13 == 0:
            hazard_count += 1
        for idx in range(hazard_count):
            template = self._HAZARD_ARCHETYPES[
                (hazard_rolls + idx) % len(self._HAZARD_ARCHETYPES)
            ]
            name = template["names"][(hazard_rolls + idx) % len(template["names"])]
            severity = 1 + (hazard_rolls + idx) % 4
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
        if loot_roll % 5 == 0:
            template = self._LOOT_TABLE[loot_roll % len(self._LOOT_TABLE)]
            loot.append(dict(template))
        if loot_roll % 11 == 0:
            template = self._LOOT_TABLE[(loot_roll + 3) % len(self._LOOT_TABLE)]
            loot.append(dict(template))

        lights = {
            "ambient": 0.35 + (loot_roll % 20) / 100.0,
            "accent": ["amber", "cyan"][loot_roll % 2],
        }

        return {"desc": desc, "hazards": hazards, "loot": loot, "lights": lights}
