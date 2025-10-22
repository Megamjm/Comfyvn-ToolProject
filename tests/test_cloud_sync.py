from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from comfyvn.sync.cloud.manifest import (
    Manifest,
    ManifestEntry,
    ManifestStore,
    build_manifest,
    diff_manifests,
)
from comfyvn.sync.cloud.secrets import SecretsVault, SecretsVaultError


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_manifest_build_and_diff(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    config_dir = tmp_path / "config"
    _write_file(assets_dir / "sprite.png", "sprite")
    _write_file(config_dir / "settings.json", '{"volume": 0.8}')

    local_manifest = build_manifest(
        ["assets", "config"],
        name="nightly",
        root=tmp_path,
    )
    assert len(local_manifest.entries) == 2

    remote_entries = dict(local_manifest.entries)
    sprite_entry = remote_entries["assets/sprite.png"]
    remote_entries["assets/sprite.png"] = ManifestEntry(
        path=sprite_entry.path,
        size=sprite_entry.size,
        mtime=sprite_entry.mtime,
        sha256="deadbeef",
    )
    remote_entries.pop("config/settings.json")
    remote_manifest = Manifest(
        name="nightly",
        root=str(tmp_path),
        created_at=local_manifest.created_at,
        entries=remote_entries,
    )

    plan = diff_manifests("s3", "nightly", local_manifest, remote_manifest)
    assert len(plan.uploads) == 2
    paths = sorted(change.path for change in plan.uploads)
    assert paths == ["assets/sprite.png", "config/settings.json"]
    assert plan.bytes_to_upload > 0

    store = ManifestStore(base_dir=tmp_path / "cache")
    snapshot = store.save("s3", "nightly", local_manifest)
    loaded = store.load("s3", "nightly")
    assert loaded is not None
    assert len(loaded.entries) == len(local_manifest.entries)
    assert snapshot.manifest.name == "nightly"


def test_secrets_vault_roundtrip_and_backups(tmp_path: Path) -> None:
    vault_path = tmp_path / "comfyvn.secrets.json"
    vault = SecretsVault(path=vault_path, env_var="TEST_SECRETS_KEY", max_backups=3)

    os.environ["TEST_SECRETS_KEY"] = "test-pass"

    payload = {"cloud_sync": {"default": {"bucket": "example"}}}
    vault.store(payload, passphrase="test-pass")
    loaded = vault.unlock(passphrase="test-pass")
    assert loaded["cloud_sync"]["default"]["bucket"] == "example"

    vault.set("cloud_sync", {"default": {"bucket": "next"}}, passphrase="test-pass")
    updated = vault.get("cloud_sync", passphrase="test-pass")
    assert updated["default"]["bucket"] == "next"

    data = json.loads(vault_path.read_text(encoding="utf-8"))
    backups = data.get("backups", [])
    assert len(backups) == 1
    assert backups[0]["version"] == 1

    with pytest.raises(SecretsVaultError):
        vault.unlock(passphrase="wrong-pass")
    os.environ.pop("TEST_SECRETS_KEY", None)
