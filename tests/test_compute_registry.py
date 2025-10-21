from __future__ import annotations

from pathlib import Path

import pytest

from comfyvn.core.compute_registry import ComputeProviderRegistry


def _registry(tmp_path: Path) -> ComputeProviderRegistry:
    path = tmp_path / "providers.json"
    if path.exists():
        path.unlink()
    return ComputeProviderRegistry(path=path)


def test_create_from_template_generates_unique_id(tmp_path: Path):
    registry = _registry(tmp_path)
    entry = registry.create_from_template(
        "runpod",
        provider_id="runpod-custom",
        name="RunPod Custom",
        config={"api_key": "SECRET"},
    )
    assert entry["id"] == "runpod-custom"
    stored = registry.get("runpod-custom")
    assert stored and stored["config"]["api_key"] == "SECRET"

    with pytest.raises(ValueError):
        registry.create_from_template("runpod", provider_id="runpod-custom")

    second = registry.create_from_template("runpod", name="RunPod Custom")
    assert second["id"] != "runpod-custom"
    assert second["id"].startswith("runpod")


def test_export_masks_secrets(tmp_path: Path):
    registry = _registry(tmp_path)
    registry.register(
        {
            "id": "custom",
            "name": "Custom Provider",
            "kind": "remote",
            "service": "lan",
            "base_url": "http://example.com",
            "config": {"api_key": "SECRET", "region": "us-west"},
        }
    )

    exported_masked = registry.export_all()
    provider = next(
        row for row in exported_masked["providers"] if row["id"] == "custom"
    )
    assert "api_key" not in provider["config"]
    assert provider["config"]["region"] == "us-west"

    exported_full = registry.export_all(mask_secrets=False)
    provider_full = next(
        row for row in exported_full["providers"] if row["id"] == "custom"
    )
    assert provider_full["config"]["api_key"] == "SECRET"


def test_import_replace_and_overwrite(tmp_path: Path):
    registry = _registry(tmp_path)
    registry.register(
        {
            "id": "alpha",
            "name": "Alpha",
            "kind": "remote",
            "service": "lan",
            "base_url": "http://alpha.local",
            "config": {},
            "priority": 30,
        }
    )

    payload = {
        "providers": [
            {
                "id": "beta",
                "name": "Beta",
                "kind": "remote",
                "service": "lan",
                "base_url": "http://beta.local",
                "config": {},
                "meta": {},
                "priority": 40,
                "active": True,
            }
        ]
    }

    imported = registry.import_data(payload, replace=False, overwrite=True)
    assert any(row["id"] == "beta" for row in imported)
    assert registry.get("alpha")
    assert registry.get("beta")

    payload_overwrite = {
        "providers": [
            {
                "id": "beta",
                "name": "Beta Updated",
                "kind": "remote",
                "service": "lan",
                "base_url": "http://beta.local",
                "config": {"note": "updated"},
            }
        ]
    }
    skipped = registry.import_data(payload_overwrite, overwrite=False)
    assert skipped == []
    assert registry.get("beta")["name"] == "Beta"

    registry.import_data(
        {
            "providers": [
                {
                    "id": "gamma",
                    "name": "Gamma",
                    "kind": "remote",
                    "service": "lan",
                    "base_url": "http://gamma.local",
                    "config": {},
                }
            ]
        },
        replace=True,
    )

    assert registry.get("gamma")
    assert registry.get("alpha") is None
    assert registry.get("beta") is None
    assert registry.get("local")


def test_export_import_roundtrip(tmp_path: Path):
    source = _registry(tmp_path / "src")
    source.register(
        {
            "id": "delta",
            "name": "Delta",
            "kind": "remote",
            "service": "lan",
            "base_url": "http://delta.local",
            "config": {"api_key": "SECRET"},
        }
    )

    exported = source.export_all(mask_secrets=False)

    target = _registry(tmp_path / "dest")
    imported = target.import_data(exported, replace=True)
    assert any(row["id"] == "delta" for row in imported)
    stored = target.get("delta")
    assert stored and stored["config"]["api_key"] == "SECRET"
