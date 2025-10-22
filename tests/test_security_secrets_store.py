from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from comfyvn.security.secrets_store import SecretStore


def _store(tmp_path: Path) -> SecretStore:
    data_path = tmp_path / "config" / "comfyvn.secrets.json"
    key_path = tmp_path / "config" / "comfyvn.secrets.key"
    return SecretStore(
        data_paths=[data_path],
        key_paths=[key_path],
    )


def test_secret_store_encrypts_and_logs_access(tmp_path, caplog):
    store = _store(tmp_path)
    store.write({"demo": {"token": "super-secret"}})

    data_file = tmp_path / "config" / "comfyvn.secrets.json"
    raw = data_file.read_text(encoding="utf-8")
    assert "super-secret" not in raw
    assert '"ciphertext"' in raw

    with caplog.at_level(logging.INFO, logger="comfyvn.security.secrets"):
        payload = store.get("demo")
    assert payload["token"] == "super-secret"
    assert any(
        '"event": "secrets.read"' in record.getMessage() for record in caplog.records
    )


def test_secret_store_environment_overrides(tmp_path, monkeypatch, caplog):
    store = _store(tmp_path)
    store.write({"demo": {"token": "value", "api_key": "base"}})

    monkeypatch.setenv("COMFYVN_SECRET_DEMO_API_KEY", "override")
    with caplog.at_level(logging.INFO, logger="comfyvn.security.secrets"):
        payload = store.get("demo")

    assert payload["api_key"] == "override"
    assert payload["token"] == "value"
    assert any(
        '"overrides": ["api_key"]' in record.getMessage() for record in caplog.records
    )


def test_secret_store_rotate_key(tmp_path):
    store = _store(tmp_path)
    store.write({"demo": {"token": "rotate-me"}})

    key_file = tmp_path / "config" / "comfyvn.secrets.key"
    original_key = key_file.read_text(encoding="utf-8").strip()
    original_blob = (tmp_path / "config" / "comfyvn.secrets.json").read_text(
        encoding="utf-8"
    )

    new_key = store.rotate_key()
    assert new_key != original_key
    assert key_file.read_text(encoding="utf-8").strip() == new_key
    new_blob = (tmp_path / "config" / "comfyvn.secrets.json").read_text(
        encoding="utf-8"
    )
    assert new_blob != original_blob
    assert store.get("demo")["token"] == "rotate-me"


def test_secret_store_upgrades_plaintext(tmp_path, monkeypatch):
    data_path = tmp_path / "config" / "comfyvn.secrets.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps({"demo": {"token": "plaintext"}}), encoding="utf-8")

    key = SecretStore.generate_key()
    monkeypatch.setenv("COMFYVN_SECRETS_KEY", key)

    store = SecretStore(
        data_paths=[data_path],
        key_paths=[tmp_path / "config" / "comfyvn.secrets.key"],
        persist_keys=False,
    )

    data = store.load()
    assert data["demo"]["token"] == "plaintext"
    raw = data_path.read_text(encoding="utf-8")
    assert "plaintext" not in raw
    assert '"ciphertext"' in raw
