from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import comfyvn.config.runtime_paths as runtime_paths

ISO_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
DYNAMIC_STRING_KEYS = {"generated_at", "saved_at_iso", "created_at"}
DYNAMIC_NUM_KEYS = {"saved_at", "timestamp"}
GOLDEN_PATH = Path(__file__).parent / "golden" / "phase4_payloads.json"


def _normalize(runtime_root: Path, value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _normalize(runtime_root, value[k], k) for k in sorted(value)}
    if isinstance(value, list):
        return [_normalize(runtime_root, item, key) for item in value]
    if isinstance(value, str):
        value = value.replace(str(runtime_root), "<runtime>")
        value = value.replace(str(Path.cwd()), "<repo>")
        if key in DYNAMIC_STRING_KEYS or ISO_REGEX.match(value or ""):
            return "<timestamp>"
        if key == "bundle":
            return "<repo>/exports/bundles/<bundle>.zip"
        if key == "issue_id":
            return "<issue-id>"
        if key == "script_sha256":
            return "<sha256>"
        if key == "renpy_project":
            return "<repo>/renpy_project"
        return value
    if isinstance(value, (int, float)):
        if key in DYNAMIC_NUM_KEYS:
            return "<timestamp>"
        if key == "size_bytes":
            return "<size>"
    return value


def _load_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.mark.skipif(not GOLDEN_PATH.exists(), reason="missing golden payloads")
def test_scenario_flow_with_exports(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("COMFYVN_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("COMFYVN_LOG_DIR", str(runtime_root / "logs"))
    monkeypatch.setenv("COMFYVN_SERVER_LOG_DIR", str(runtime_root / "logs"))

    runtime_paths._runtime_roots.cache_clear()

    import comfyvn.server.app as app_module

    app_module = importlib.reload(app_module)
    client = TestClient(app_module.create_app())

    scene = {
        "id": "phase4-demo",
        "start": "intro",
        "variables": {"score": 0},
        "nodes": [
            {
                "id": "intro",
                "type": "dialogue",
                "text": "Welcome to Phase 4",
                "choices": [
                    {
                        "id": "path_left",
                        "label": "Take the left path",
                        "target": "left_path",
                        "actions": [{"type": "set", "key": "score", "value": 1}],
                    },
                    {
                        "id": "path_right",
                        "label": "Take the right path",
                        "target": "right_path",
                        "actions": [{"type": "set", "key": "score", "value": 5}],
                    },
                ],
            },
            {
                "id": "left_path",
                "type": "dialogue",
                "text": "Left it is",
                "choices": [
                    {
                        "id": "finish_left",
                        "label": "Finish",
                        "target": "ending",
                        "actions": [{"type": "increment", "key": "score", "amount": 2}],
                    }
                ],
            },
            {
                "id": "right_path",
                "type": "dialogue",
                "text": "Right it is",
                "choices": [
                    {
                        "id": "finish_right",
                        "label": "Finish",
                        "target": "ending",
                        "actions": [{"type": "increment", "key": "score", "amount": 3}],
                    }
                ],
            },
            {"id": "ending", "type": "dialogue", "text": "The end", "end": True},
        ],
    }

    responses: dict[str, dict] = {}
    responses["scenario_validate"] = client.post(
        "/api/scenario/validate", json={"scene": scene}
    ).json()

    step1 = client.post(
        "/api/scenario/run/step", json={"scene": scene, "seed": 7}
    ).json()
    responses["scenario_step_1"] = step1

    choice_id = step1["choices"][0]["id"]
    step2 = client.post(
        "/api/scenario/run/step",
        json={
            "scene": scene,
            "state": step1["state"],
            "choice_id": choice_id,
            "seed": 7,
        },
    ).json()
    responses["scenario_step_2"] = step2

    step3 = client.post(
        "/api/scenario/run/step",
        json={"scene": scene, "state": step2["state"], "seed": 7},
    ).json()
    responses["scenario_step_3"] = step3

    save_payload = {
        "vars": step2["state"]["variables"],
        "node_pointer": step2["state"]["current_node"],
        "seed": 7,
        "pov": step2["state"].get("pov"),
    }
    responses["save_store"] = client.post("/api/save/phase4", json=save_payload).json()
    responses["save_list"] = client.get("/api/save/list").json()
    responses["save_load"] = client.get("/api/save/phase4").json()

    scene_state = {
        "scene_id": "phase4-demo",
        "characters": [
            {
                "id": "hero",
                "display_name": "Hero",
                "slot": "center",
                "portrait": {"asset": "hero.png"},
                "default_expression": "neutral",
            }
        ],
        "camera": {"shot": "medium"},
        "timing": {"enter": 0.2, "hold": 2.0, "exit": 0.1},
    }
    node_payload = {
        "id": "left_path",
        "type": "dialogue",
        "speaker": "Hero",
        "directives": {"expression": "smile", "sfx": ["chime"]},
    }
    responses["presentation_plan"] = client.post(
        "/api/presentation/plan",
        json={"scene_state": scene_state, "node": node_payload},
    ).json()

    for part in ["projects", "timelines", "scenes", "characters"]:
        runtime_paths.data_dir(part).mkdir(parents=True, exist_ok=True)
    runtime_paths.data_dir("assets", "backgrounds").mkdir(parents=True, exist_ok=True)

    (runtime_paths.data_dir("scenes") / "intro.json").write_text(
        json.dumps({"scene_id": "intro", "title": "Intro", "lines": []}),
        encoding="utf-8",
    )
    (runtime_paths.data_dir("scenes") / "ending.json").write_text(
        json.dumps({"scene_id": "ending", "title": "Ending", "lines": []}),
        encoding="utf-8",
    )
    (runtime_paths.data_dir("characters") / "hero.json").write_text(
        json.dumps({"character_id": "hero", "name": "Hero"}), encoding="utf-8"
    )
    (runtime_paths.data_dir("timelines") / "main.json").write_text(
        json.dumps(
            {
                "timeline_id": "main",
                "title": "Main",
                "scene_order": [{"scene_id": "intro"}, {"scene_id": "ending"}],
                "project_id": "phase4",
            }
        ),
        encoding="utf-8",
    )
    (runtime_paths.data_dir("projects") / "phase4.json").write_text(
        json.dumps(
            {
                "name": "phase4",
                "title": "Phase 4",
                "scenes": ["intro", "ending"],
                "characters": ["hero"],
                "assets": ["backgrounds/bg.png"],
                "licenses": [],
            }
        ),
        encoding="utf-8",
    )
    (runtime_paths.data_dir("assets", "backgrounds") / "bg.png").write_bytes(b"fake")

    client.post("/api/advisory/ack", json={"user": "phase4-test"})
    responses["export_renpy"] = client.post(
        "/api/export/renpy", params={"project_id": "phase4", "timeline_id": "main"}
    ).json()
    responses["export_bundle"] = client.post(
        "/api/export/bundle", params={"project_id": "phase4", "timeline_id": "main"}
    ).json()

    normalized = {k: _normalize(runtime_root, v, k) for k, v in responses.items()}
    golden = _load_golden()

    assert normalized == golden
