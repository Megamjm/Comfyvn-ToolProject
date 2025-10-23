from __future__ import annotations

from comfyvn.core import advisory
from comfyvn.core.content_filter import ContentFilter
from comfyvn.core.policy_gate import PolicyGate
from comfyvn.core.settings_manager import SettingsManager


def test_policy_gate_acknowledgement_flow(tmp_path, monkeypatch):
    settings_path = tmp_path / "config.json"
    db_path = tmp_path / "settings.db"
    settings = SettingsManager(path=settings_path, db_path=db_path)
    gate = PolicyGate(settings)

    status = gate.status()
    assert status.requires_ack is True
    assert status.ack_legal_v1 is False

    result = gate.evaluate_action("export.bundle")
    assert result["allow"] is True
    assert result["requires_ack"] is True
    assert any(
        "disclaimer" in warning.lower() for warning in result.get("warnings", [])
    )

    updated = gate.acknowledge(user="tester")
    assert updated.ack_legal_v1 is True
    assert updated.requires_ack is False
    assert updated.ack_timestamp

    result_after = gate.evaluate_action("export.bundle")
    assert result_after["allow"] is True
    assert result_after["requires_ack"] is False
    assert result_after.get("warnings") == []

    gate.reset()
    reset_status = gate.status()
    assert reset_status.requires_ack is True
    config = settings.load()
    assert config["ack_disclaimer_v1"] is False
    assert config["policy"]["ack_legal_v1"] is False


def test_content_filter_modes_persist_in_settings(tmp_path):
    settings_path = tmp_path / "config.json"
    db_path = tmp_path / "settings.db"
    settings = SettingsManager(path=settings_path, db_path=db_path)
    filt = ContentFilter(settings)

    items = [
        {"id": "asset:1", "meta": {"nsfw": True}},
        {"id": "asset:2", "meta": {"tags": ["safe"]}},
    ]

    result_sfw = filt.filter_items(items)
    assert result_sfw["mode"] == "sfw"
    assert len(result_sfw["allowed"]) == 1
    assert len(result_sfw["flagged"]) == 1

    filt.set_mode("warn")
    config = settings.load()
    assert config["filters"]["content_mode"] == "warn"

    result_warn = filt.filter_items(items)
    assert result_warn["mode"] == "warn"
    assert len(result_warn["allowed"]) == 2
    assert len(result_warn["warnings"]) >= 1


def test_advisory_scan_and_resolve(monkeypatch):
    monkeypatch.setattr(advisory, "advisory_logs", [])

    issues = advisory.scan_text(
        "scene:test",
        "This demo references 18+ material and © copyright text.",
        license_scan=True,
    )
    assert issues
    issue_id = issues[0]["issue_id"]

    unresolved = advisory.list_logs(resolved=False)
    assert any(item["issue_id"] == issue_id for item in unresolved)

    assert advisory.resolve_issue(issue_id, "Reviewed and cleared") is True
    resolved = advisory.list_logs(resolved=True)
    assert any(item["issue_id"] == issue_id for item in resolved)
