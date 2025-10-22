from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from comfyvn.config import feature_flags
from comfyvn.security import secrets_store
from comfyvn.server.app import create_app


def test_security_api_requires_feature_flag(monkeypatch):
    monkeypatch.setattr(feature_flags, "is_enabled", lambda name, **kw: False)
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/security/secrets/providers")
        assert resp.status_code == 403


def test_security_api_endpoints(monkeypatch, tmp_path: Path):
    original_is_enabled = feature_flags.is_enabled

    def _is_enabled(name: str, **kwargs) -> bool:
        if name == "enable_security_api":
            return True
        return original_is_enabled(name, **kwargs)

    monkeypatch.setattr(feature_flags, "is_enabled", _is_enabled)

    data_path = tmp_path / "config" / "comfyvn.secrets.json"
    key_path = tmp_path / "config" / "comfyvn.secrets.key"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        secrets_store, "DEFAULT_SECRET_PATHS", (data_path,), raising=False
    )
    monkeypatch.setattr(secrets_store, "DEFAULT_KEY_PATHS", (key_path,), raising=False)
    secrets_store._DEFAULT_STORE = None

    store = secrets_store.default_store()
    store.write({"demo": {"token": "abc123", "api_key": "value"}})

    audit_path = tmp_path / "audit.log"
    audit_path.write_text(
        '{"event":"secrets.read","timestamp":"2024-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("COMFYVN_SECURITY_LOG_FILE", str(audit_path))
    monkeypatch.setenv("SANDBOX_NETWORK_ALLOW", "localhost:8080")

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/security/secrets/providers")
        assert resp.status_code == 200
        payload = resp.json()
        providers = {entry["provider"]: entry for entry in payload["providers"]}
        assert "demo" in providers
        assert providers["demo"]["stored_keys"] == ["api_key", "token"]
        assert payload["log_path"] == str(audit_path)

        rotate = client.post("/api/security/secrets/rotate", json={})
        assert rotate.status_code == 200
        rotate_payload = rotate.json()
        assert "fingerprint" in rotate_payload
        assert rotate_payload["providers"]

        audit = client.get("/api/security/audit")
        assert audit.status_code == 200
        audit_payload = audit.json()
        assert audit_payload["items"]
        assert audit_payload["log_path"] == str(audit_path)

        defaults = client.get("/api/security/sandbox/defaults")
        assert defaults.status_code == 200
        defaults_payload = defaults.json()
        assert defaults_payload["network_allow"] == ["localhost:8080"]

        allow_resp = client.post(
            "/api/security/sandbox/check", json={"host": "127.0.0.1", "port": 8080}
        )
        assert allow_resp.status_code == 200
        assert allow_resp.json()["allowed"] is True

        deny_resp = client.post(
            "/api/security/sandbox/check", json={"host": "example.com", "port": 443}
        )
        assert deny_resp.status_code == 200
        assert deny_resp.json()["allowed"] is False
