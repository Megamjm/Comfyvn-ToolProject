from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/modules/persona_manager.py
# 🫂 Persona & Group Production Chat — Phase 3.2
# [Persona_ComfyUI_Bridge]

import os, json, glob, random
from pathlib import Path

from comfyvn.assets.pose_utils import load_pose
from comfyvn.assets.pose_manager import PoseManager


class PersonaManager:
    """Handles persona profiles, sprite binding, positioning, and ComfyUI export."""

    def __init__(self, data_path="./data/personas", sprite_root="./assets/sprites"):
        self.data_path = data_path
        self.sprite_root = sprite_root
        os.makedirs(self.data_path, exist_ok=True)
        os.makedirs(self.sprite_root, exist_ok=True)

        self.personas = {}
        self.group_layouts = {}
        self.positions = ["left", "center", "right", "offscreen"]
        self.pose_manager = PoseManager()

        # ComfyUI coordinate presets (x, y positions on stage)
        self.stage_coords = {
            "left": (-300, 0),
            "center": (0, 0),
            "right": (300, 0),
            "offscreen": (9999, 9999),
        }
        self._load_existing()

    # ------------------------------
    # Persona CRUD
    # ------------------------------
    def register_persona(self, persona_id: str, profile: dict):
        profile.setdefault("sprite_folder", os.path.join(self.sprite_root, persona_id))
        profile.setdefault("expression", "neutral")
        profile.setdefault("poses", {})
        self.personas[persona_id] = profile
        self._save_profile(persona_id, profile)

    def _save_profile(self, persona_id: str, profile: dict):
        path = os.path.join(self.data_path, f"{persona_id}.json")
        with open(path, "w") as f:
            json.dump(profile, f, indent=2)

    def load_persona(self, persona_id: str):
        path = os.path.join(self.data_path, f"{persona_id}.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                profile = json.load(f)
                self.personas[persona_id] = profile
                return profile
        return None

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
        if not os.path.exists(folder):
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
                "metadata": {"pose": persona.get("poses", {}).get("current")},
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
        for file in Path(self.data_path).glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                self.personas[file.stem] = data
            except Exception:
                continue
