from __future__ import annotations

from comfyvn.workflows import templates
from comfyvn.workflows.runtime import WorkflowRuntime


def test_sprite_workflows_present():
    names = {entry["name"] for entry in templates.list_templates()}
    assert "sprite_composite_basic" in names
    assert "pose_blend_basic" in names


def test_instantiate_pose_blend_handles_params():
    spec = templates.instantiate(
        "pose_blend_basic",
        {"pose_a": "pose_a.json", "pose_b": "pose_b.json", "blend": 0.25},
    )
    node_types = {node["type"] for node in spec["nodes"]}
    assert {"LoadPose", "PoseDelta", "PoseInterpolator"}.issubset(node_types)


def test_runtime_sprite_composite_handles_missing_layers(tmp_path):
    spec = templates.instantiate(
        "sprite_composite_basic",
        {
            "background": "bg.png",
            "sprite_left": "",
            "sprite_center": "hero.png",
            "sprite_right": "",
        },
    )
    runtime = WorkflowRuntime(spec, "sprite-test")
    result = runtime.run()
    assert result["ok"]
    assert "image" in result["outputs"]
