from __future__ import annotations

import glob
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from comfyvn.assets.character_manager import CharacterManager
from comfyvn.assets.pose_manager import PoseManager
from comfyvn.assets.pose_utils import load_pose
from comfyvn.config.runtime_paths import data_dir
from comfyvn.core.memory_engine import remember_event

LOGGER = logging.getLogger(__name__)

DEFAULT_POSITIONS = ["left", "center", "right", "offscreen"]
STAGE_COORDS = {
    "left": (-300, 0),
    "center": (0, 0),
    "right": (300, 0),
    "offscreen": (9999, 9999),
}
DEFAULT_LLM_PROFILE = {
    "provider": "local_llm",
    "model": "dialogue-default",
    "mode": "offline",
    "temperature": 0.8,
}


class PersonaManager:
    """Handles persona, player character linkage, and ComfyUI export metadata."""

    def __init__(
        self,
        data_path: str | Path | None = None,
        sprite_root: str | Path | None = None,
        *,
        characters_path: str | Path | None = None,
        character_sprite_root: str | Path | None = None,
        state_path: str | Path | None = None,
        character_manager: Optional[CharacterManager] = None,
    ) -> None:
        self.data_path = Path(data_path) if data_path else data_dir("personas")
        self.data_path.mkdir(parents=True, exist_ok=True)

        self.sprite_root = Path(sprite_root) if sprite_root else Path("./assets/sprites")
        self.sprite_root.mkdir(parents=True, exist_ok=True)
        self.character_sprite_root = (
            Path(character_sprite_root) if character_sprite_root else Path("./assets/characters")
        )
        self.character_sprite_root.mkdir(parents=True, exist_ok=True)

        self.character_manager = character_manager or CharacterManager(characters_path)
        self.state_path = Path(state_path) if state_path else data_dir("persona", "state.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        self.pose_manager = PoseManager()
        self.personas: Dict[str, Dict[str, Any]] = {}
        self.group_layouts: Dict[str, Dict[str, str]] = {}
        self.positions: List[str] = list(DEFAULT_POSITIONS)
        self.stage_coords = dict(STAGE_COORDS)

        self.state = self._load_state()
        self._load_existing()

    # ------------------------------
    # Persona CRUD
    # ------------------------------
    def register_persona(
        self,
        persona_id: str,
        profile: Dict[str, Any],
        *,
        character_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register or update a persona profile."""
        persona_id = str(persona_id).strip()
        if not persona_id:
            raise ValueError("persona_id is required")

        full_profile = self._ensure_profile_defaults(
            persona_id,
            dict(profile or {}),
            character_id=character_id,
            role=role,
        )
        self.personas[persona_id] = full_profile
        self._save_profile(persona_id, full_profile)

        remember_event(
            "persona.register",
            {
                "id": persona_id,
                "character": full_profile.get("character_id"),
                "role": full_profile.get("role"),
            },
        )

        # Auto-select the first player persona if none active.
        if (
            full_profile.get("is_player")
            and not self.state.get("active_persona")
            and not self.state.get("active_character")
        ):
            self.set_active_persona(persona_id, character_id=full_profile.get("character_id"), reason="auto")
        return dict(full_profile)

    def _save_profile(self, persona_id: str, profile: dict):
        path = self.data_path / f"{persona_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_persona(self, persona_id: str) -> Optional[Dict[str, Any]]:
        path = self.data_path / f"{persona_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to load persona %s: %s", persona_id, exc)
            return None
        profile = self._ensure_profile_defaults(persona_id, data)
        self.personas[persona_id] = profile
        return dict(profile)

    def list_personas(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        target_role = role.lower() if isinstance(role, str) else None
        items: List[Dict[str, Any]] = []
        for persona_id, data in sorted(self.personas.items()):
            if target_role and data.get("role") != target_role:
                continue
            entry = dict(data)
            entry["id"] = persona_id
            items.append(entry)
        return items

    def get_persona(self, persona_id: str) -> Optional[Dict[str, Any]]:
        record = self.personas.get(persona_id)
        return dict(record) if record else None

    def reload(self) -> None:
        """Refresh personas, characters, and state from disk."""
        self.character_manager.reload()
        self.state = self._load_state()
        self._load_existing()

    # ------------------------------
    # Expression & Sprite Binding
    # ------------------------------
    def set_expression(self, persona_id: str, expression: str):
        if persona_id not in self.personas:
            return {"status": "error", "reason": "Persona not found"}

        self.personas[persona_id]["expression"] = expression
        sprite_path = self._resolve_sprite(persona_id, expression)
        self.personas[persona_id]["current_sprite"] = sprite_path
        self._save_profile(persona_id, self.personas[persona_id])
        return {"status": "ok", "expression": expression, "sprite": sprite_path}

    def _resolve_sprite(self, persona_id: str, expression: str):
        persona = self.personas.get(persona_id)
        if not persona:
            return None
        folder = persona.get("sprite_folder")
        if not os.path.exists(folder):
            return None
        pattern = os.path.join(folder, f"{expression}.*")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
        fallback = glob.glob(os.path.join(folder, "neutral.*"))
        return fallback[0] if fallback else (matches[0] if matches else None)

    def random_expression(self, persona_id: str):
        persona = self.personas.get(persona_id)
        if not persona:
            return None
        folder = persona.get("sprite_folder")
        if not folder or not os.path.exists(folder):
            return None
        files = [os.path.basename(f) for f in glob.glob(os.path.join(folder, "*.*"))]
        expressions = [os.path.splitext(f)[0] for f in files]
        if not expressions:
            return None
        expr = random.choice(expressions)
        return self.set_expression(persona_id, expr)

    def list_expressions(self, persona_id: str) -> list[str]:
        persona = self.personas.get(persona_id)
        if not persona:
            return []
        folder = persona.get("sprite_folder")
        if not folder or not os.path.exists(folder):
            return []
        files = [os.path.basename(f) for f in glob.glob(os.path.join(folder, "*.*"))]
        return sorted({os.path.splitext(f)[0] for f in files})

    def set_pose(self, persona_id: str, pose_path: str):
        if persona_id not in self.personas:
            return {"status": "error", "reason": "Persona not found"}
        try:
            pose_data = load_pose(pose_path)
        except Exception as exc:
            return {"status": "error", "reason": str(exc)}
        profile = self.personas[persona_id]
        profile.setdefault("poses", {})
        profile["poses"]["current"] = {
            "path": pose_path,
            "data": pose_data,
        }
        self._save_profile(persona_id, profile)
        return {"status": "ok", "pose": pose_path}

    def get_current_pose(self, persona_id: str):
        persona = self.personas.get(persona_id, {})
        return persona.get("poses", {}).get("current")

    # ------------------------------
    # Player & character linkage
    # ------------------------------
    def import_character(
        self,
        source: str | Path | Dict[str, Any],
        *,
        role: str = "player",
        overwrite: bool = False,
        auto_select: bool = False,
    ) -> Dict[str, Any]:
        """Import a character payload and auto-create a linked persona."""
        character = self.character_manager.import_character(source, overwrite=overwrite)
        persona_payload = dict(character.get("persona") or character.get("persona_profile") or {})
        persona_id = persona_payload.get("id") or character.get("persona_id") or character.get("id")
        if not persona_id:
            persona_id = character["id"]
        persona_payload.setdefault("display_name", character.get("display_name") or character.get("name"))
        persona_payload.setdefault("sprite_folder", persona_payload.get("sprite_folder"))
        persona_payload.setdefault("llm_profile", character.get("llm_profile"))
        persona_payload.setdefault("traits", character.get("traits"))
        persona_payload.setdefault("role", persona_payload.get("role") or role)
        persona = self.register_persona(persona_id, persona_payload, character_id=character["id"])
        remember_event(
            "persona.import_character",
            {"persona": persona_id, "character": character["id"], "role": persona.get("role")},
        )
        if auto_select:
            self.set_active_persona(persona_id, character_id=character["id"], reason="import")
        return {"character": character, "persona": persona}

    def set_active_persona(
        self,
        persona_id: str,
        *,
        character_id: Optional[str] = None,
        mode: Optional[str] = None,
        reason: str = "manual",
    ) -> Dict[str, Any]:
        if persona_id not in self.personas:
            raise KeyError(f"persona '{persona_id}' not found")
        persona = self.personas[persona_id]
        character_id = character_id or persona.get("character_id")
        if character_id:
            persona.setdefault("character_id", character_id)
            char = self.character_manager.get_character(character_id)
            if char:
                persona.setdefault(
                    "character",
                    {
                        "id": char.get("id"),
                        "name": char.get("name"),
                        "display_name": char.get("display_name") or char.get("name"),
                        "avatar": char.get("avatar"),
                    },
                )
        if mode:
            self.state["mode"] = mode
        self.state["active_persona"] = persona_id
        self.state["active_character"] = character_id
        history_entry = {
            "ts": time.time(),
            "persona": persona_id,
            "character": character_id,
            "reason": reason,
        }
        self.state.setdefault("history", []).append(history_entry)
        self._save_state()
        remember_event("persona.active", history_entry)
        return self.get_active_selection()

    def set_active_character(
        self,
        character_id: str,
        *,
        mode: Optional[str] = None,
        reason: str = "manual",
    ) -> Dict[str, Any]:
        character_id = str(character_id).strip()
        if not character_id:
            raise ValueError("character_id is required")
        persona_id = self._persona_for_character(character_id)
        if not persona_id:
            raise KeyError(f"No persona linked to character '{character_id}'")
        return self.set_active_persona(persona_id, character_id=character_id, mode=mode, reason=reason)

    def get_active_selection(self) -> Dict[str, Any]:
        persona_id = self.state.get("active_persona")
        character_id = self.state.get("active_character")
        persona = self.personas.get(persona_id) if persona_id else None
        character = self.character_manager.get_character(character_id) if character_id else None
        return {
            "persona_id": persona_id,
            "character_id": character_id,
            "persona": dict(persona) if persona else None,
            "character": character,
            "mode": self.state.get("mode", "vn"),
        }

    def process_persona(
        self,
        persona_id: Optional[str] = None,
        *,
        scene_id: Optional[str] = None,
        detail_level: Optional[str] = None,
        export: bool = False,
    ) -> Dict[str, Any]:
        persona_id = persona_id or self.state.get("active_persona")
        if not persona_id:
            raise ValueError("persona_id required")
        if persona_id not in self.personas:
            raise KeyError(f"persona '{persona_id}' not found")

        persona = self.personas[persona_id]
        expressions = self.list_expressions(persona_id)
        sprites = {
            expr: self._resolve_sprite(persona_id, expr)
            for expr in expressions
        }

        persona.setdefault("sprites", {})
        persona["sprites"]["expressions"] = sprites
        if detail_level:
            persona["detail_level"] = detail_level
        persona["processed_at"] = time.time()
        self._save_profile(persona_id, persona)

        summary: Dict[str, Any] = {
            "id": persona_id,
            "detail_level": persona.get("detail_level"),
            "persona": persona,
            "expressions": expressions,
            "sprites": sprites,
            "poses": persona.get("poses", {}),
        }

        if scene_id:
            if scene_id not in self.group_layouts:
                self.group_layouts[scene_id] = {persona_id: "center"}
            summary["comfyui_graph"] = self.generate_comfyui_graph(scene_id)

        export_path: Optional[Path] = None
        if export:
            export_dir = data_dir("persona", "exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            export_path = Path(export_dir) / f"{persona_id}_summary.json"
            export_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            summary["export_path"] = str(export_path)

        remember_event(
            "persona.process",
            {
                "persona": persona_id,
                "scene": scene_id,
                "detail_level": summary.get("detail_level"),
                "export_path": str(export_path) if export_path else None,
            },
        )
        return summary

    def _persona_for_character(self, character_id: str) -> Optional[str]:
        for pid, profile in self.personas.items():
            if profile.get("character_id") == character_id:
                return pid
        if character_id in self.personas:
            return character_id
        return None

    # ------------------------------
    # Group Layout Logic
    # ------------------------------
    def arrange_characters(self, scene_id: str, persona_ids: list):
        layout = {}
        for i, pid in enumerate(persona_ids):
            layout[pid] = self.positions[i % len(self.positions)]
        self.group_layouts[scene_id] = layout
        return layout

    def get_layout(self, scene_id: str):
        return self.group_layouts.get(scene_id, {})

    # ------------------------------
    # ComfyUI Node Export
    # ------------------------------
    def generate_comfyui_graph(self, scene_id: str):
        """
        Build a node graph dict for ComfyUI to composite persona sprites
        according to their positions.
        """
        layout = self.group_layouts.get(scene_id)
        if not layout:
            return None

        # Base ComfyUI node chain
        graph = {"nodes": [], "connections": []}
        node_id = 0

        # Load and position nodes
        for pid, pos in layout.items():
            persona = self.personas.get(pid)
            if not persona:
                continue
            sprite = persona.get("current_sprite")
            if not sprite or not os.path.exists(sprite):
                continue

            x, y = self.stage_coords.get(pos, (0, 0))
            load_node = {
                "id": node_id,
                "type": "LoadImage",
                "inputs": {"filename": sprite},
                "position": {"x": x, "y": y},
                "persona": pid,
                "metadata": {
                    "pose": persona.get("poses", {}).get("current"),
                    "llm_profile": persona.get("llm_profile"),
                    "character": persona.get("character"),
                },
            }
            graph["nodes"].append(load_node)
            node_id += 1

        # Add a composite output node
        graph["nodes"].append(
            {
                "id": node_id,
                "type": "CompositeImage",
                "inputs": {"images": [n["id"] for n in graph["nodes"][:-1]]},
                "output": True,
            }
        )

        return graph

    # ------------------------------
    # Serialization
    # ------------------------------
    def export_state(self, scene_id: str, export_path="./exports/persona_state.json"):
        data = {
            "scene_id": scene_id,
            "active": self.get_active_selection(),
            "layout": self.group_layouts.get(scene_id, {}),
            "personas": {
                pid: self.personas[pid]
                for pid in self.group_layouts.get(scene_id, {})
                if pid in self.personas
            },
            "comfyui_graph": self.generate_comfyui_graph(scene_id),
        }
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        with open(export_path, "w") as f:
            json.dump(data, f, indent=2)
        return {"status": "exported", "path": export_path}

    # ------------------------------
    # Internal helpers
    # ------------------------------
    def _load_existing(self) -> None:
        self.personas.clear()
        for file in self.data_path.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except Exception as exc:
                LOGGER.warning("Skipping persona %s (invalid json): %s", file, exc)
                continue
            persona_id = file.stem
            profile = self._ensure_profile_defaults(persona_id, data)
            self.personas[persona_id] = profile

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {
                "active_persona": None,
                "active_character": None,
                "mode": "vn",
                "history": [],
            }
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Persona state corrupted (%s); resetting", exc)
            return {
                "active_persona": None,
                "active_character": None,
                "mode": "vn",
                "history": [],
            }
        data.setdefault("history", [])
        data.setdefault("mode", "vn")
        data.setdefault("active_persona", None)
        data.setdefault("active_character", None)
        data["history"] = [row for row in data["history"] if isinstance(row, dict)][-50:]
        return data

    def _save_state(self) -> None:
        payload = dict(self.state)
        payload["updated_at"] = time.time()
        payload["history"] = payload.get("history", [])[-50:]
        self.state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _ensure_profile_defaults(
        self,
        persona_id: str,
        profile: Dict[str, Any],
        *,
        character_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        persona_id = str(persona_id)
        combined = dict(profile or {})
        combined["id"] = persona_id
        if character_id:
            combined["character_id"] = character_id
        role_value = role or combined.get("role") or ("player" if combined.get("is_player") else "npc")
        role_value = str(role_value).lower()
        if role_value not in {"player", "npc", "support", "companion"}:
            role_value = "npc"
        combined["role"] = role_value
        combined["is_player"] = bool(combined.get("is_player") or role_value == "player")
        combined.setdefault("expression", combined.get("expression") or "neutral")
        combined.setdefault("poses", combined.get("poses") or {})
        combined.setdefault("metadata", combined.get("metadata") or {})
        combined.setdefault("llm_profile", combined.get("llm_profile") or dict(DEFAULT_LLM_PROFILE))
        cid = combined.get("character_id")

        if cid:
            char = self.character_manager.get_character(cid)
            if char:
                combined.setdefault(
                    "character",
                    {
                        "id": char.get("id"),
                        "name": char.get("name"),
                        "display_name": char.get("display_name") or char.get("name"),
                        "avatar": char.get("avatar"),
                    },
                )

        folder_hint = combined.get("sprite_folder")
        if not folder_hint:
            folder_hint = self._default_sprite_folder(persona_id, cid)
        combined["sprite_folder"] = folder_hint

        return combined

    def _default_sprite_folder(self, persona_id: str, character_id: Optional[str]) -> str:
        candidates: List[Path] = []
        if character_id:
            candidates.append(self.character_sprite_root / character_id / "sprites")
            candidates.append(self.character_sprite_root / character_id)
        candidates.append(self.sprite_root / persona_id)

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        target = candidates[0] if candidates else (self.sprite_root / persona_id)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception:
            # If creation fails, fallback to sprite_root/persona_id
            fallback = self.sprite_root / persona_id
            fallback.mkdir(parents=True, exist_ok=True)
            return str(fallback)
        return str(target)


__all__ = ["PersonaManager"]
