from __future__ import annotations

import pytest

from comfyvn.market.manifest import (
    DEFAULT_GLOBAL_ROUTE_ALLOWLIST,
    ManifestError,
    validate_manifest_payload,
)


def _base_manifest(**overrides):
    payload = {
        "id": "demo.extension",
        "name": "Demo Extension",
        "version": "1.0.0",
        "description": "Demo manifest for tests",
    }
    payload.update(overrides)
    return payload


def test_manifest_summary_falls_back_to_description():
    manifest = validate_manifest_payload(_base_manifest())
    assert manifest.summary == "Demo manifest for tests"


def test_manifest_blocks_global_route_for_unverified():
    payload = _base_manifest(
        routes=[
            {
                "path": "/api/private",
                "entry": "handlers.py",
                "callable": "handlers.endpoint",
                "expose": "global",
            }
        ]
    )
    with pytest.raises(ManifestError):
        validate_manifest_payload(payload, trust_level="unverified")


def test_manifest_allows_trusted_routes_when_allowlisted():
    payload = _base_manifest(
        routes=[
            {
                "path": "/api/modder/tools",
                "entry": "handlers.py",
                "callable": "handlers.endpoint",
                "expose": "global",
            }
        ]
    )
    manifest = validate_manifest_payload(payload, trust_level="verified")
    assert manifest.routes[0].path == "/api/modder/tools"


def test_manifest_unknown_permission_rejected():
    payload = _base_manifest(permissions=[{"scope": "does.not.exist"}])
    with pytest.raises(ManifestError):
        validate_manifest_payload(payload)
