from __future__ import annotations

import json
from pathlib import Path

from comfyvn.assets.persona_manager import PersonaManager


def test_persona_manager_pose(tmp_path):
    sprite_dir = tmp_path / "sprites" / "hero"
    sprite_dir.mkdir(parents=True)
    neutral = sprite_dir / "neutral.png"
    neutral.write_bytes(b"fake")

    pose_dir = tmp_path / "poses"
    pose_dir.mkdir(parents=True)
    pose_path = pose_dir / "hero_pose.json"
    pose_path.write_text(json.dumps({"pose_id": "hero", "skeleton": {"root": {"x": 0, "y": 0}}}))

    manager = PersonaManager(
        data_path=tmp_path / "personas",
        sprite_root=tmp_path / "sprites",
        characters_path=tmp_path / "characters",
        character_sprite_root=tmp_path / "assets" / "characters",
        state_path=tmp_path / "persona_state.json",
    )
    manager.register_persona("hero", {"sprite_folder": str(sprite_dir)})
    manager.set_expression("hero", "neutral")
    result = manager.set_pose("hero", str(pose_path))
    assert result["status"] == "ok"
    pose = manager.get_current_pose("hero")
    assert pose is not None
    assert pose["path"].endswith("hero_pose.json")


def test_persona_manager_active_selection(tmp_path):
    sprite_dir = tmp_path / "sprites" / "hero"
    sprite_dir.mkdir(parents=True, exist_ok=True)
    (sprite_dir / "neutral.png").write_bytes(b"fake")

    manager = PersonaManager(
        data_path=tmp_path / "personas",
        sprite_root=tmp_path / "sprites",
        characters_path=tmp_path / "characters",
        character_sprite_root=tmp_path / "assets" / "characters",
        state_path=tmp_path / "persona_state.json",
    )

    manager.register_persona("hero", {"sprite_folder": str(sprite_dir)}, role="player")
    state = manager.get_active_selection()
    assert state["persona_id"] == "hero"
    assert state["character_id"] is None

    manager.set_active_persona("hero", mode="vn", reason="test")
    refreshed = manager.get_active_selection()
    assert refreshed["persona_id"] == "hero"
    assert refreshed["mode"] == "vn"


def test_persona_manager_import_character(tmp_path):
    sprite_dir = tmp_path / "sprites" / "hero"
    sprite_dir.mkdir(parents=True, exist_ok=True)
    (sprite_dir / "neutral.png").write_bytes(b"fake")

    manager = PersonaManager(
        data_path=tmp_path / "personas",
        sprite_root=tmp_path / "sprites",
        characters_path=tmp_path / "characters",
        character_sprite_root=tmp_path / "assets" / "characters",
        state_path=tmp_path / "persona_state.json",
    )

    payload = {
        "id": "hero",
        "name": "Hero",
        "persona": {
            "sprite_folder": str(sprite_dir),
            "expression": "neutral",
        },
        "traits": {"courage": 5},
    }

    result = manager.import_character(payload, auto_select=True)
    assert result["character"]["id"] == "hero"
    persona = result["persona"]
    assert persona["character_id"] == "hero"
    state = manager.get_active_selection()
    assert state["character_id"] == "hero"
    assert state["persona_id"] == "hero"
