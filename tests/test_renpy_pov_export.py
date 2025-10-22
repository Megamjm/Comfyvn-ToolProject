from __future__ import annotations

from comfyvn.exporters.renpy_orchestrator import (
    POVRoute,
    _collect_scene_povs,
    _render_script,
    _timeline_scene_entries,
)


def test_collect_scene_povs_detects_nested_entries() -> None:
    scene = {
        "title": "Test Scene",
        "meta": {"pov": "alice", "pov_name": "Alice POV"},
        "nodes": [
            {
                "pov": "bob",
                "pov_name": "Bob POV",
                "content": {"pov": "charlie", "pov_name": "Charlie POV"},
            },
            {
                "meta": {"pov": "dana", "pov_name": "Dana POV"},
            },
        ],
        "dialogue": [
            {"text": "hello", "pov": "eve", "pov_name": "Eve POV"},
            {"text": "bye"},
        ],
    }
    result = _collect_scene_povs(scene)
    assert result == {
        "alice": "Alice POV",
        "bob": "Bob POV",
        "charlie": "Charlie POV",
        "dana": "Dana POV",
        "eve": "Eve POV",
    }


def test_timeline_scene_entries_includes_pov_metadata() -> None:
    timeline = {
        "scene_order": [
            {"scene_id": "scene_a", "pov": "alice", "pov_name": "Alice POV"},
            {
                "scene_id": "scene_b",
                "povs": [{"id": "bob", "name": "Bob POV"}, "charlie"],
            },
        ]
    }
    entries = _timeline_scene_entries(timeline, project_data=None)
    assert len(entries) == 2
    assert entries[0]["scene_id"] == "scene_a"
    assert entries[0]["pov_values"] == ["alice"]
    assert entries[1]["scene_id"] == "scene_b"
    assert set(entries[1]["pov_values"]) == {"bob", "charlie"}
    assert entries[1]["pov_names"]["bob"] == "Bob POV"


def test_render_script_builds_switch_menu_for_multiple_routes() -> None:
    label_map = [
        {"scene_id": "scene_a", "label": "scene_a"},
        {"scene_id": "scene_b", "label": "scene_b"},
    ]
    scenes = {
        "scene_a": {"nodes": [{"type": "text", "content": {"text": "Scene A"}}]},
        "scene_b": {"nodes": [{"type": "text", "content": {"text": "Scene B"}}]},
    }
    routes = [
        POVRoute(
            pov="alice",
            name="Alice POV",
            slug="alice",
            entry_label="comfyvn_pov_alice",
            labels=["scene_a"],
            scenes=["scene_a"],
        ),
        POVRoute(
            pov="bob",
            name="Bob POV",
            slug="bob",
            entry_label="comfyvn_pov_bob",
            labels=["scene_b"],
            scenes=["scene_b"],
        ),
    ]
    script = _render_script(
        project_id="demo",
        timeline_id="main",
        generated_at="2025-01-01T00:00:00Z",
        backgrounds={},
        portraits={},
        label_map=label_map,
        scenes=scenes,
        alias_lookup={},
        pov_routes=routes,
        include_switch_menu=True,
    )
    assert "label comfyvn_pov_menu" in script
    assert "call comfyvn_pov_alice" in script
    assert "call comfyvn_pov_bob" in script
    # Ensure branch label renders sequence for active POV.
    assert "label comfyvn_pov_alice:" in script
    assert "label comfyvn_pov_bob:" in script
