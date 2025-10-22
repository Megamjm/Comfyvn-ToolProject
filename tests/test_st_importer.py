from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from comfyvn.importers.st_chat import map_to_scenes, parse_st_payload
from comfyvn.server.routes import import_st


def test_parse_st_payload_normalises_entries():
    payload = {
        "title": "Aurora Run",
        "entries": [
            {
                "name": "Aurora",
                "mes": "Hello there :)",
                "timestamp": "2024-01-01T10:00:00Z",
                "role": "assistant",
            },
            {
                "name": "You",
                "mes": "> Ask about the forest\nChoice: Retreat",
                "is_user": True,
                "created": 1704103422,
            },
        ],
    }
    turns = parse_st_payload(payload)
    assert len(turns) == 2
    first, second = turns
    assert first["speaker"] == "Aurora"
    assert first["text"] == "Hello there :)"
    assert first["meta"]["conversation_title"] == "Aurora Run"
    assert not first["meta"]["is_user"]
    assert second["meta"]["is_user"] is True
    assert second["text"].startswith("> Ask about the forest")


def test_map_to_scenes_infers_choices_and_expression():
    turns = [
        {
            "speaker": "Aurora",
            "text": "Welcome [smile] traveller",
            "ts": 1.0,
            "meta": {"is_user": False, "session": "session-1"},
        },
        {
            "speaker": "You",
            "text": "Choice: Ask about the relic\n> Leave",
            "ts": 2.0,
            "meta": {"is_user": True},
        },
        {
            "speaker": "Aurora",
            "text": "*sigh* It was lost ages ago.",
            "ts": 3.0,
            "meta": {"is_user": False},
        },
    ]
    scenes = map_to_scenes(
        "demo_project",
        turns,
        persona_aliases={"aurora": "npc_aurora", "you": "player"},
        default_player_persona="player",
    )
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene["id"].startswith("demo-project")
    nodes = scene["nodes"]
    assert nodes[0]["type"] == "line"
    assert nodes[0]["speaker"] == "npc_aurora"
    assert nodes[0]["expression"] == "smile"
    assert nodes[1]["type"] == "choice"
    assert len(nodes[1]["choices"]) == 2
    assert nodes[1]["choices"][0]["id"].endswith("01")
    assert scene["meta"]["annotations"]
    # Ensure unresolved persona warnings not present for mapped participants.
    assert "Aurora" not in scene["meta"]["unresolved_personas"]


@pytest.fixture()
def st_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Enable feature flag for the importer.
    def _is_enabled(name: str, *, default: bool | None = None, refresh: bool = False):
        if name == import_st.FEATURE_FLAG:
            return True
        return bool(default)

    monkeypatch.setattr(import_st.feature_flags, "is_enabled", _is_enabled)

    # Redirect storage roots to the tmp_path sandbox.
    imports_root = tmp_path / "imports"
    scenes_root = tmp_path / "scenes"
    imports_root.mkdir(parents=True, exist_ok=True)
    scenes_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(import_st, "IMPORT_ROOT", imports_root, raising=False)
    monkeypatch.setattr(import_st, "_SCENE_STORE", import_st.SceneStore(scenes_root))

    class _StubPersonaManager:
        def __init__(self) -> None:
            self.state: Dict[str, Any] = {"active_persona": "player"}

        def list_personas(self) -> list[dict[str, Any]]:
            return [
                {"id": "player", "name": "You"},
                {"id": "npc_aurora", "name": "Aurora"},
            ]

    monkeypatch.setattr(import_st, "_PERSONA_MANAGER", _StubPersonaManager())

    app = FastAPI()
    app.include_router(import_st.router)
    return TestClient(app)


def test_import_start_endpoint_generates_artifacts(st_app: TestClient, tmp_path: Path):
    transcript = "\n".join(
        [
            "Aurora: Welcome back!",
            "You: Choice: Ask about the relic",
            "You: > Leave camp",
            "Aurora: [smile] Safe travels.",
        ]
    )
    response = st_app.post(
        "/api/import/st/start",
        data={"projectId": "demo", "text": transcript},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    run_id = payload["runId"]
    assert payload["sceneCount"] >= 1
    # Ensure status endpoint reflects completion.
    status = st_app.get(f"/api/import/st/status/{run_id}")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["phase"] == "completed"
    assert status_payload["scenes"]
    # Stored artifacts should exist under the patched imports directory.
    run_dir = import_st.IMPORT_ROOT / run_id
    assert (run_dir / import_st.TURN_FILE).exists()
    assert (run_dir / import_st.SCENES_FILE).exists()
    scene_snapshot = json.loads(
        (run_dir / import_st.SCENES_FILE).read_text(encoding="utf-8")
    )
    assert scene_snapshot["scenes"]
