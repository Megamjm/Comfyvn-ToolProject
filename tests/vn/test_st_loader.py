from __future__ import annotations

import json
import re
import sys
import types
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _ensure_pyside6() -> None:
    """Install a lightweight PySide6 stub so router imports do not fail."""
    if "PySide6" in sys.modules:
        return
    pyside = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside.QtGui = qtgui
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtGui"] = qtgui


_ensure_pyside6()

from comfyvn.qa.playtest import HeadlessPlaytestRunner, compare_traces
from comfyvn.server.routes import import_st, playtest, vn_loader

BREAK_MARKERS: set[str] = {"---", "***", "==="}
DEFAULT_SEED = 1337
GOLDEN_CASES: Sequence[Tuple[str, str]] = (
    ("trace_mc.json", "mc"),
    ("trace_antagonist.json", "antagonist"),
)


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text or "persona"


def _is_break_marker(node: Mapping[str, Any]) -> bool:
    if node.get("type") != "line":
        return False
    text = str(node.get("text") or "").strip()
    return text in BREAK_MARKERS


def _resolve_next_id(
    nodes: Sequence[Mapping[str, Any]],
    current_index: int,
    skip_ids: set[str],
    default_end_id: str,
) -> str:
    """Return the next reachable node id, ignoring any breakers."""
    explicit = nodes[current_index].get("next")
    if isinstance(explicit, str) and explicit.strip():
        candidate = explicit.strip()
        if candidate not in skip_ids:
            return candidate
    for later in nodes[current_index + 1 :]:
        candidate = str(later.get("id") or "").strip()
        if not candidate or candidate in skip_ids:
            continue
        return candidate
    return default_end_id


def _canonicalize_choice(
    choice: Mapping[str, Any],
    *,
    target_id: str,
    fallback_label: str,
    fallback_index: int,
) -> Dict[str, Any]:
    label = str(choice.get("text") or fallback_label or "Continue").strip()
    if not label:
        label = f"Option {fallback_index}"
    payload: Dict[str, Any] = {
        "id": str(choice.get("id") or f"choice_{fallback_index}"),
        "label": label,
        "target": target_id,
        "weight": float(choice.get("weight") or 1.0),
    }
    actions = choice.get("set") or choice.get("actions")
    if isinstance(actions, list):
        payload["actions"] = actions
    return payload


def _convert_spec_to_canonical(scene_spec: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert Story Tavern mapper output into ScenarioRunner canonical schema."""
    nodes = list(scene_spec.get("nodes") or [])
    if not nodes:
        raise ValueError("scene contains no nodes")

    skip_ids: set[str] = {
        str(node.get("id")) for node in nodes if _is_break_marker(node)
    }
    end_node_id = str(nodes[-1].get("id") or f"{scene_spec.get('id')}_end")

    valid_nodes: List[Tuple[int, Mapping[str, Any]]] = []
    for index, node in enumerate(nodes):
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        if node_id in skip_ids:
            continue
        valid_nodes.append((index, node))

    if not valid_nodes:
        raise ValueError("no usable nodes after filtering break markers")

    canonical_nodes: List[Dict[str, Any]] = []
    for ordinal, (original_index, node) in enumerate(valid_nodes):
        node_id = str(node.get("id"))
        node_type = str(node.get("type") or "line").lower()
        if node_type == "end":
            canonical_nodes.append(
                {
                    "id": node_id,
                    "type": "end",
                    "choices": [],
                    "end": True,
                }
            )
            continue

        if node_type == "choice":
            entries: List[Dict[str, Any]] = []
            for idx, option in enumerate(node.get("choices") or []):
                target = _resolve_next_id(
                    nodes,
                    original_index,
                    skip_ids,
                    default_end_id=end_node_id,
                )
                explicit_next = option.get("next")
                if isinstance(explicit_next, str) and explicit_next.strip():
                    explicit_target = explicit_next.strip()
                    if explicit_target not in skip_ids:
                        target = explicit_target
                entries.append(
                    _canonicalize_choice(
                        option,
                        target_id=target,
                        fallback_label=node.get("prompt") or "",
                        fallback_index=idx + 1,
                    )
                )
            canonical_nodes.append(
                {
                    "id": node_id,
                    "type": "choice",
                    "text": node.get("prompt"),
                    "choices": entries,
                }
            )
            continue

        # Default: treat as dialogue node.
        target = _resolve_next_id(
            nodes, original_index, skip_ids, default_end_id=end_node_id
        )
        text = str(node.get("text") or "").strip()
        speaker = node.get("speaker")
        choice_label = text or f"Continue {ordinal+1}"
        canonical_nodes.append(
            {
                "id": node_id,
                "type": "dialogue",
                "speaker": speaker,
                "text": text or "...",
                "choices": [
                    {
                        "id": f"{node_id}_auto",
                        "label": choice_label,
                        "target": target,
                        "weight": 1.0,
                    }
                ],
            }
        )

    start_id = str(scene_spec.get("start") or valid_nodes[0][1].get("id"))
    if start_id in skip_ids:
        # shift start to first non-break node
        start_id = canonical_nodes[0]["id"]

    metadata = dict(scene_spec.get("meta") or {})
    variables = scene_spec.get("variables")
    if not isinstance(variables, Mapping):
        variables = {}

    return {
        "id": str(scene_spec.get("id")),
        "title": scene_spec.get("title"),
        "metadata": metadata,
        "variables": dict(variables),
        "start": start_id,
        "nodes": canonical_nodes,
    }


def _canonical_to_builder_scene(scene: Mapping[str, Any]) -> Dict[str, Any]:
    """Prepare a canonical scene for the VN builder."""
    nodes = []
    for node in scene.get("nodes") or []:
        builder_node: Dict[str, Any] = {
            "id": node["id"],
            "text": node.get("text"),
            "speaker": node.get("speaker"),
            "choices": [],
        }
        actions = node.get("actions")
        if isinstance(actions, list) and actions:
            builder_node["actions"] = actions
        for choice in node.get("choices") or []:
            builder_node["choices"].append(
                {
                    "id": choice.get("id"),
                    "text": choice.get("label"),
                    "to": choice.get("target"),
                    "weight": choice.get("weight", 1.0),
                }
            )
        if node.get("type") == "end":
            builder_node["choices"] = []
            builder_node["result"] = node.get("result") or "Imported from SillyTavern"
        nodes.append(builder_node)
    payload = {
        "id": scene["id"],
        "title": scene.get("title"),
        "nodes": nodes,
        "variables": scene.get("variables") or {},
        "meta": scene.get("metadata") or {},
    }
    return payload


def _builder_to_canonical_scene(
    builder_scene: Mapping[str, Any],
    reference_scene: Mapping[str, Any],
) -> Dict[str, Any]:
    """Normalize builder output back into the canonical schema."""
    ref_nodes = list(reference_scene.get("nodes") or [])
    builder_nodes = list(builder_scene.get("nodes") or [])
    id_map: Dict[str, str] = {}
    for ref_node, built_node in zip(ref_nodes, builder_nodes):
        ref_id = str(ref_node.get("id"))
        built_id = str(built_node.get("id"))
        id_map[ref_id] = built_id

    canonical_nodes: List[Dict[str, Any]] = []
    for built_node in builder_nodes:
        node_id = str(built_node.get("id"))
        choices_payload: List[Dict[str, Any]] = []
        for idx, choice in enumerate(built_node.get("choices") or []):
            target = choice.get("to") or choice.get("target")
            if isinstance(target, str) and target in id_map:
                target = id_map[target]
            elif isinstance(target, str):
                target = target
            else:
                target = node_id
            label = str(choice.get("text") or "").strip()
            if not label:
                label = f"Option {idx+1}"
            choices_payload.append(
                {
                    "id": choice.get("id") or f"{node_id}_choice_{idx+1}",
                    "label": label,
                    "target": target,
                    "weight": float(choice.get("weight", 1.0)),
                }
            )
        node_payload: Dict[str, Any] = {
            "id": node_id,
            "text": built_node.get("text"),
            "speaker": built_node.get("speaker"),
            "choices": choices_payload,
        }
        actions = built_node.get("actions")
        if isinstance(actions, list) and actions:
            node_payload["actions"] = actions
        if not choices_payload:
            node_payload["type"] = "end"
            node_payload["choices"] = []
            node_payload["end"] = True
        else:
            node_payload.setdefault("type", "dialogue")
        canonical_nodes.append(node_payload)

    start_original = str(reference_scene.get("start") or canonical_nodes[0]["id"])
    start_id = id_map.get(start_original, canonical_nodes[0]["id"])

    metadata = builder_scene.get("meta") or builder_scene.get("metadata") or {}
    variables = builder_scene.get("variables") or {}

    return {
        "id": str(builder_scene.get("id")),
        "title": builder_scene.get("title"),
        "metadata": dict(metadata),
        "variables": dict(variables),
        "start": start_id,
        "nodes": canonical_nodes,
    }


def _collect_personas(scenes: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    speakers: Dict[str, str] = {}
    for scene in scenes:
        metadata = scene.get("metadata") or {}
        persona_map = metadata.get("persona_map") or {}
        for speaker_name, persona_id in persona_map.items():
            if persona_id in speakers:
                continue
            speakers[persona_id] = speaker_name
        for node in scene.get("nodes") or []:
            speaker = node.get("speaker")
            if not speaker:
                continue
            persona_id = _slugify(str(speaker))
            speakers.setdefault(persona_id, str(speaker))
    personas = [
        {"id": persona_id, "displayName": display}
        for persona_id, display in sorted(speakers.items())
    ]
    if not personas:
        personas.append({"id": "narrator", "displayName": "Narrator"})
    return personas


def _infer_pov(scene: Mapping[str, Any]) -> str:
    for node in scene.get("nodes") or []:
        speaker = node.get("speaker")
        if speaker:
            return _slugify(str(speaker))
    return "narrator"


def _sanitize_scene_for_runner(scene: Mapping[str, Any]) -> Dict[str, Any]:
    """Drop unsupported keys so the ScenarioRunner schema validates."""
    allowed_root = {
        "id",
        "title",
        "description",
        "metadata",
        "variables",
        "start",
        "nodes",
    }
    sanitized: Dict[str, Any] = {
        key: deepcopy(value) for key, value in scene.items() if key in allowed_root
    }
    sanitized.setdefault("variables", {})
    nodes: List[Dict[str, Any]] = []
    for node in scene.get("nodes") or []:
        payload: Dict[str, Any] = {
            "id": node["id"],
            "choices": [],
        }
        if node.get("text"):
            payload["text"] = node["text"]
        if node.get("speaker"):
            payload["speaker"] = node["speaker"]
        if node.get("type"):
            payload["type"] = node["type"]
        if node.get("end"):
            payload["end"] = True
        actions = node.get("actions")
        if isinstance(actions, list) and actions:
            payload["actions"] = deepcopy(actions)
        choices: List[Dict[str, Any]] = []
        for choice in node.get("choices") or []:
            entry = {
                "id": choice.get("id"),
                "label": choice.get("label") or "Continue",
                "target": choice.get("target"),
                "weight": float(choice.get("weight", 1.0)),
            }
            actions = choice.get("actions")
            if isinstance(actions, list) and actions:
                entry["actions"] = deepcopy(actions)
            choices.append(entry)
        payload["choices"] = choices
        nodes.append(payload)
    sanitized["nodes"] = nodes
    return sanitized


def _execute_pipeline(
    client: TestClient,
    workspace: Path,
    sample_path: Path,
) -> Dict[str, Dict[str, Any]]:
    sample_payload = sample_path.read_text(encoding="utf-8")
    response = client.post(
        "/api/import/st/start",
        data={"projectId": "vn_st_sample", "text": sample_payload},
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["runId"]

    status = client.get(f"/api/import/st/status/{run_id}")
    assert status.status_code == 200, status.text
    status_payload = status.json()
    assert status_payload["phase"] == "completed"
    scenes_payload = status_payload["scenes"]
    if isinstance(scenes_payload, dict) and "scenes" in scenes_payload:
        scene_specs = scenes_payload["scenes"]
    elif isinstance(scenes_payload, list):
        scene_specs = scenes_payload
    else:
        raise AssertionError("Unexpected scenes payload shape")

    canonical_specs = [_convert_spec_to_canonical(spec) for spec in scene_specs]
    personas = _collect_personas(canonical_specs)

    builder_bundle = {
        "kind": "inline",
        "label": "st_sample_bundle",
        "data": {
            "personas": personas,
            "scenes": [_canonical_to_builder_scene(scene) for scene in canonical_specs],
        },
    }

    build_workspace = workspace / "builder"
    build_workspace.mkdir(parents=True, exist_ok=True)
    build_resp = client.post(
        "/api/vn/build",
        json={
            "projectId": "vn_st_sample",
            "workspace": str(build_workspace),
            "sources": [builder_bundle],
        },
    )
    assert build_resp.status_code == 200, build_resp.text
    build_payload = build_resp.json()
    built_scenes = build_payload["scenes"]

    canonical_scenes = [
        _builder_to_canonical_scene(built, reference)
        for built, reference in zip(built_scenes, canonical_specs)
    ]

    traces: Dict[str, Dict[str, Any]] = {}
    for scene in canonical_scenes:
        pov = _infer_pov(scene)
        sanitized_scene = _sanitize_scene_for_runner(scene)
        playtest_resp = client.post(
            "/api/playtest/run",
            json={
                "scene": sanitized_scene,
                "seed": DEFAULT_SEED,
                "pov": pov,
                "persist": False,
            },
        )
        assert playtest_resp.status_code == 200, playtest_resp.text
        payload = playtest_resp.json()
        traces[pov] = {
            "digest": payload["digest"],
            "trace": payload["trace"],
        }
    return traces


@pytest.fixture()
def st_test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _ensure_pyside6()

    def _is_enabled(
        name: str,
        *,
        default: bool | None = None,
        refresh: bool = False,
    ) -> bool:
        if name in {import_st.FEATURE_FLAG, "enable_playtest_harness"}:
            return True
        return bool(default)

    monkeypatch.setattr(
        import_st.feature_flags, "is_enabled", _is_enabled, raising=False
    )
    monkeypatch.setattr(
        playtest.feature_flags, "is_enabled", _is_enabled, raising=False
    )

    imports_root = tmp_path / "imports"
    scenes_root = tmp_path / "scene_store"
    imports_root.mkdir(parents=True, exist_ok=True)
    scenes_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(import_st, "IMPORT_ROOT", imports_root, raising=False)
    monkeypatch.setattr(
        import_st, "_SCENE_STORE", import_st.SceneStore(scenes_root), raising=False
    )

    class _StubPersonaManager:
        def __init__(self) -> None:
            self.state: Dict[str, Any] = {"active_persona": "mc"}

        def list_personas(self) -> List[Dict[str, Any]]:
            return [
                {"id": "mc", "name": "MC"},
                {"id": "antagonist", "name": "Antagonist"},
            ]

    monkeypatch.setattr(
        import_st, "_PERSONA_MANAGER", _StubPersonaManager(), raising=False
    )

    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vn_loader, "PROJECTS_ROOT", projects_root, raising=False)

    runner = HeadlessPlaytestRunner(log_dir=tmp_path / "playtest_logs")
    monkeypatch.setattr(playtest, "_RUNNER", runner, raising=False)

    app = FastAPI()
    app.include_router(import_st.router)
    app.include_router(vn_loader.router)
    app.include_router(playtest.router)

    with TestClient(app) as client:
        yield {
            "client": client,
            "workspace": tmp_path,
            "golden_dir": Path("qa/goldens/vn_st_sample"),
            "fixture_path": Path("qa/fixtures/st_sample.json"),
        }


def test_st_import_build_play_golden(st_test_env: Mapping[str, Any]) -> None:
    client: TestClient = st_test_env["client"]
    workspace: Path = st_test_env["workspace"]
    sample_path: Path = st_test_env["fixture_path"]
    golden_dir: Path = st_test_env["golden_dir"]

    traces = _execute_pipeline(client, workspace, sample_path)

    for filename, pov in GOLDEN_CASES:
        golden_path = golden_dir / filename
        assert golden_path.exists(), f"Missing golden: {golden_path}"
        expected_trace = json.loads(golden_path.read_text(encoding="utf-8"))
        produced = traces[pov]["trace"]
        result = compare_traces(expected_trace, produced)
        assert result.ok, f"Trace mismatch for {filename}: {result.mismatches}"

        repeat = traces[pov]["trace"]
        repeat_result = compare_traces(produced, repeat)
        assert repeat_result.ok, f"Repeat run diverged for {pov}"


def regenerate_goldens() -> None:
    """Regenerate golden traces for the ST loader pipeline."""
    _ensure_pyside6()
    from contextlib import ExitStack
    from tempfile import TemporaryDirectory
    from unittest.mock import patch

    sample_path = Path("qa/fixtures/st_sample.json")
    golden_dir = Path("qa/goldens/vn_st_sample")
    golden_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        imports_root = tmp_path / "imports"
        scenes_root = tmp_path / "scene_store"
        projects_root = tmp_path / "projects"
        imports_root.mkdir(parents=True, exist_ok=True)
        scenes_root.mkdir(parents=True, exist_ok=True)
        projects_root.mkdir(parents=True, exist_ok=True)

        runner = HeadlessPlaytestRunner(log_dir=tmp_path / "playtest_logs")

        with ExitStack() as stack:

            def _patch(obj: Any, name: str, value: Any) -> None:
                stack.enter_context(patch.object(obj, name, value, create=True))

            def _flag(
                name: str, *, default: bool | None = None, refresh: bool = False
            ) -> bool:
                if name in {import_st.FEATURE_FLAG, "enable_playtest_harness"}:
                    return True
                return bool(default)

            _patch(import_st.feature_flags, "is_enabled", _flag)
            _patch(playtest.feature_flags, "is_enabled", _flag)
            _patch(import_st, "IMPORT_ROOT", imports_root)
            _patch(import_st, "_SCENE_STORE", import_st.SceneStore(scenes_root))

            class _StubPersonaManager:
                def __init__(self) -> None:
                    self.state: Dict[str, Any] = {"active_persona": "mc"}

                def list_personas(self) -> List[Dict[str, Any]]:
                    return [
                        {"id": "mc", "name": "MC"},
                        {"id": "antagonist", "name": "Antagonist"},
                    ]

            _patch(import_st, "_PERSONA_MANAGER", _StubPersonaManager())
            _patch(vn_loader, "PROJECTS_ROOT", projects_root)
            _patch(playtest, "_RUNNER", runner)

            app = FastAPI()
            app.include_router(import_st.router)
            app.include_router(vn_loader.router)
            app.include_router(playtest.router)

            with TestClient(app) as client:
                traces = _execute_pipeline(client, tmp_path, sample_path)

    for filename, pov in GOLDEN_CASES:
        golden_path = golden_dir / filename
        golden_path.write_text(
            json.dumps(traces[pov]["trace"], indent=2, sort_keys=True),
            encoding="utf-8",
        )


if __name__ == "__main__":
    regenerate_goldens()
