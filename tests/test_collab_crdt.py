from __future__ import annotations

import json

from comfyvn.collab import CRDTDocument, CRDTOperation


def _op(op_id: str, actor: str, clock: int, kind: str, payload: dict) -> CRDTOperation:
    return CRDTOperation(
        op_id=op_id,
        actor=actor,
        clock=clock,
        kind=kind,
        payload=payload,
    )


def test_operations_converge_and_deduplicate() -> None:
    doc = CRDTDocument(
        "intro",
        initial={
            "scene_id": "intro",
            "title": "Intro",
            "nodes": [{"id": "start", "text": "Begin"}],
            "lines": [],
        },
    )

    op_title = _op(
        "alice:1",
        "alice",
        clock=1,
        kind="scene.field.set",
        payload={"field": "title", "value": "Collaborative Intro"},
    )
    result_title = doc.apply_operation(op_title)
    assert result_title.applied is True
    assert result_title.duplicate is False
    assert doc.snapshot()["title"] == "Collaborative Intro"

    # Duplicate op_id should not change the document or version.
    duplicate = doc.apply_operation(op_title)
    assert duplicate.applied is False
    assert duplicate.duplicate is True
    assert doc.version == result_title.version

    op_node_a = _op(
        "alice:2",
        "alice",
        clock=2,
        kind="graph.node.upsert",
        payload={"node": {"id": "branch_a", "text": "Path A"}},
    )
    op_node_b = _op(
        "bob:1",
        "bob",
        clock=2,
        kind="graph.node.upsert",
        payload={"node": {"id": "branch_b", "text": "Path B"}},
    )
    res_a = doc.apply_operation(op_node_a)
    res_b = doc.apply_operation(op_node_b)
    assert res_a.applied and res_b.applied
    snap = doc.snapshot()
    node_ids = [n["id"] for n in snap["nodes"]]
    assert {"branch_a", "branch_b"}.issubset(set(node_ids))
    assert doc.version > result_title.version

    # Removing a node should leave only the remaining entry.
    op_remove = _op(
        "alice:3",
        "alice",
        clock=3,
        kind="graph.node.remove",
        payload={"node_id": "branch_a"},
    )
    doc.apply_operation(op_remove)
    snap_after = doc.snapshot()
    node_ids_after = [n["id"] for n in snap_after["nodes"]]
    assert "branch_a" not in node_ids_after
    assert "branch_b" in node_ids_after

    # Persistable payload carries lamport clock & version.
    persistable = doc.persistable()
    assert persistable["lamport"] >= doc.clock
    assert persistable["version"] == doc.version

    operations = doc.operations_since(0)
    assert len(operations) >= 4  # title set + upserts + removal
    assert operations[-1].operation.op_id == op_remove.op_id


def test_script_line_order_merges() -> None:
    doc = CRDTDocument("scene")

    line_one = _op(
        "client:1",
        "client",
        1,
        "script.line.upsert",
        payload={"line": {"line_id": "l1", "speaker": "Alice", "text": "Hi"}},
    )
    line_two = _op(
        "client:2",
        "client",
        2,
        "script.line.upsert",
        payload={
            "line": {"line_id": "l2", "speaker": "Bob", "text": "Welcome"},
            "after": "l1",
        },
    )
    order_replace = _op(
        "client:3",
        "client",
        3,
        "script.order.replace",
        payload={"order": ["l2", "l1"]},
    )

    doc.apply_operation(line_one)
    doc.apply_operation(line_two)
    doc.apply_operation(order_replace)

    snapshot = doc.snapshot()
    assert snapshot["order"] == ["l2", "l1"]
    lines = snapshot["lines"]
    assert [ln["line_id"] for ln in lines] == ["l2", "l1"]
    assert json.dumps(lines[0], sort_keys=True)
