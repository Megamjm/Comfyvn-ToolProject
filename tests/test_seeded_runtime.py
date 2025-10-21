from __future__ import annotations

import sys
import types

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient

# Minimal PySide6 stub for modules that import QAction
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QAction = type("QAction", (), {})
    pyside6.QtGui = qtgui
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtGui"] = qtgui


from comfyvn.server.app import create_app
from comfyvn.workflows.runtime import WorkflowRuntime


@pytest.mark.parametrize(
    "branches,seed",
    [
        ([["a", "b"], ["x", "y", "z"]], 42),
        ([["k1", "k2", "k3"], ["p"], ["Q", "R"]], 7),
    ],
)
def test_replay_auto_same_seed_same_path(branches, seed):
    client = TestClient(create_app())
    r1 = client.post("/replay/auto", json={"branches": branches, "seed_choice": seed})
    r2 = client.post("/replay/auto", json={"branches": branches, "seed_choice": seed})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["path"] == r2.json()["path"]


@pytest.mark.xfail(reason="Workflow runtime has no seed parameter yet", strict=False)
def test_workflow_seeded_runs_identical_outputs():
    wf = {
        "name": "seeded-echo",
        "nodes": [
            {
                "id": "n1",
                "type": "echo",
                "params": {"message": "${input.msg}"},
                "inputs": {},
                "outputs": {"out": "$output.result"},
            }
        ],
        "outputs": {"final": "n1.out"},
        "inputs": {"msg": {"type": "string"}},
    }
    r1 = WorkflowRuntime(wf, run_id="A", inputs={"msg": "hello"}).run()
    r2 = WorkflowRuntime(wf, run_id="B", inputs={"msg": "hello"}).run()
    assert r1["outputs"] == r2["outputs"]


def test_workflow_failure_on_bad_source_reference():
    wf = {
        "name": "bad-source",
        "nodes": [
            {"id": "n1", "type": "echo", "params": {"message": "ok"}},
            # n2 incorrectly references missing port on n1
            {
                "id": "n2",
                "type": "concat",
                "params": {"a": "x"},
                "inputs": {"b": "n1.missing"},
            },
        ],
        "outputs": {"final": "n2.out"},
    }
    rt = WorkflowRuntime(wf, run_id="E2E")
    with pytest.raises(Exception):
        rt.run()
