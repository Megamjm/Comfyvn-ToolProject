from __future__ import annotations

from comfyvn.studio.core.timeline_registry import TimelineRegistry


def _ensure_table(registry: TimelineRegistry) -> None:
    with registry.connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timelines (
                id INTEGER PRIMARY KEY,
                project_id TEXT DEFAULT 'default',
                name TEXT,
                scene_order JSON,
                meta JSON,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def test_save_and_list_timelines(tmp_path):
    db_path = tmp_path / "studio.db"
    registry = TimelineRegistry(db_path=db_path, project_id="demo")
    _ensure_table(registry)

    timeline_id = registry.save_timeline(
        name="Chapter 1",
        scene_order=[{"scene_id": "intro", "title": "Intro", "notes": " Establish tone"}],
        meta={"notes": "opening arc"},
    )

    timelines = registry.list_timelines()
    assert len(timelines) == 1
    record = timelines[0]
    assert record["id"] == timeline_id
    assert record["name"] == "Chapter 1"
    assert record["scene_order"][0]["scene_id"] == "intro"

    # Update timeline and ensure the change persists
    registry.save_timeline(
        name="Chapter 1",
        scene_order=[{"scene_id": "intro", "title": "Intro", "notes": "start"}, {"scene_id": "scene-2", "title": "Dock", "notes": " Add conflict"}],
        meta={"notes": "expanded"},
        timeline_id=timeline_id,
    )

    updated = registry.get_timeline(timeline_id)
    assert updated is not None
    assert len(updated["scene_order"]) == 2
    assert updated["scene_order"][1]["scene_id"] == "scene-2"
