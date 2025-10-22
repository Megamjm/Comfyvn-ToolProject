"""
Marketplace utilities for ComfyVN extensions.

This package exposes helpers for reading and validating extension manifests,
building distributable archives, and orchestrating install/uninstall flows.
It intentionally avoids importing heavy dependencies at module import time so
that lightweight tooling (schema inspection, docs generation) can reuse it.
"""

from __future__ import annotations

from .manifest import (
    DEFAULT_GLOBAL_ROUTE_ALLOWLIST,
    KNOWN_PERMISSION_SCOPES,
    MANIFEST_FILE_NAMES,
    MANIFEST_VERSION,
    ExtensionManifest,
    ManifestError,
    TrustInfo,
    find_manifest_path,
    load_manifest,
    validate_manifest_payload,
)
from .packaging import PackageBuildResult, build_extension_package
from .service import ExtensionMarket, InstallResult, MarketCatalog, MarketEntry

__all__ = [
    "DEFAULT_GLOBAL_ROUTE_ALLOWLIST",
    "ExtensionManifest",
    "find_manifest_path",
    "InstallResult",
    "KNOWN_PERMISSION_SCOPES",
    "MANIFEST_FILE_NAMES",
    "MANIFEST_VERSION",
    "ManifestError",
    "TrustInfo",
    "ExtensionMarket",
    "MarketCatalog",
    "MarketEntry",
    "PackageBuildResult",
    "build_extension_package",
    "load_manifest",
    "validate_manifest_payload",
]
