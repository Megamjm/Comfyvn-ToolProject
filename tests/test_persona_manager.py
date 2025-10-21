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

    manager = PersonaManager(data_path=str(tmp_path / "personas"), sprite_root=str(tmp_path / "sprites"))
    manager.register_persona("hero", {"sprite_folder": str(sprite_dir)})
    manager.set_expression("hero", "neutral")
    result = manager.set_pose("hero", str(pose_path))
    assert result["status"] == "ok"
    pose = manager.get_current_pose("hero")
    assert pose is not None
    assert pose["path"].endswith("hero_pose.json")
