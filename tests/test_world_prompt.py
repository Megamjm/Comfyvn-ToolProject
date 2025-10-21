from __future__ import annotations

import json
from pathlib import Path

from comfyvn.core.world_prompt import build_world_prompt


def test_build_world_prompt_auroragate():
    world_path = Path("defaults/worlds/auroragate.json")
    payload = json.loads(world_path.read_text(encoding="utf-8"))

    result = build_world_prompt(payload, location_id="concourse")
    assert "Main Concourse" in result.prompt
    assert "Hopeful science-fantasy" in result.prompt
    assert "glass promenades" in result.prompt

    trace_paths = {entry.path for entry in result.trace}
    assert any(path.startswith("locations.") for path in trace_paths)
    assert "rules" in trace_paths
