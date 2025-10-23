from __future__ import annotations

from pathlib import Path

from comfyvn.core import modder_hooks
from comfyvn.core.policy_gate import PolicyGate
from comfyvn.core.settings_manager import SettingsManager
from comfyvn.policy.audit import PolicyAudit
from comfyvn.policy.enforcer import PolicyEnforcer


def _test_gate(tmp_path: Path) -> PolicyGate:
    settings = SettingsManager(
        path=tmp_path / "config.json", db_path=tmp_path / "settings.db"
    )
    gate = PolicyGate(settings)
    gate.acknowledge(user="tester")
    return gate


def test_policy_enforcer_persists_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(modder_hooks, "emit", lambda *args, **kwargs: None)
    gate = _test_gate(tmp_path)
    log_dir = tmp_path / "logs"
    enforcer = PolicyEnforcer(log_dir=log_dir, gate=gate, enabled=True)

    result = enforcer.enforce(
        "export.bundle",
        {
            "metadata": {"source": "test"},
            "scenes": {},
            "assets": [],
            "licenses": [],
        },
    )

    assert result.allow is True
    assert result.log_path is not None
    log_path = Path(result.log_path)
    assert log_path.exists()
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1


def test_policy_enforcer_blocks_on_block_findings(tmp_path, monkeypatch):
    monkeypatch.setattr(modder_hooks, "emit", lambda *args, **kwargs: None)
    gate = _test_gate(tmp_path)
    log_dir = tmp_path / "logs"
    enforcer = PolicyEnforcer(log_dir=log_dir, gate=gate, enabled=True)

    result = enforcer.enforce(
        "export.bundle",
        {"metadata": {"source": "test.block"}},
        findings=[
            {
                "level": "block",
                "message": "Forbidden license",
                "detail": {"reason": "no redistribution"},
            }
        ],
    )

    assert result.allow is True
    assert result.counts["block"] == 1
    assert any(entry["level"] == "block" for entry in result.blocked)
    log_path = Path(result.log_path)
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1


def test_policy_audit_exports_report(tmp_path, monkeypatch):
    monkeypatch.setattr(modder_hooks, "emit", lambda *args, **kwargs: None)
    gate = _test_gate(tmp_path)
    log_dir = tmp_path / "logs"
    enforcer = PolicyEnforcer(log_dir=log_dir, gate=gate, enabled=True)
    enforcer.enforce("export.bundle", {"metadata": {"source": "audit"}})
    enforcer.enforce(
        "import.bundle",
        {"metadata": {"source": "audit"}},
        findings=[{"level": "block", "message": "nsfw"}],
    )

    audit = PolicyAudit(log_dir=log_dir)
    events = audit.list_events(limit=10)
    assert len(events) == 2
    summary = audit.summary()
    assert summary["events"] == 2
    report_path = audit.export_report()
    assert report_path.exists()
    payload = report_path.read_text(encoding="utf-8")
    assert "generated_at" in payload
