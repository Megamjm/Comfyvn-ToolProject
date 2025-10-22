"""
Cloud sync adapters expose manifest generation, delta planning, and execution hooks.

The package provides provider-specific clients (S3, Google Drive) alongside a shared
manifest utility and an encrypted secrets vault helper that keeps credentials
sealed at rest.
"""

from __future__ import annotations

from .gdrive import GoogleDriveSyncClient, GoogleDriveSyncConfig
from .manifest import (
    Manifest,
    ManifestEntry,
    ManifestSnapshot,
    ManifestStore,
    SyncChange,
    SyncPlan,
    build_manifest,
    diff_manifests,
)
from .s3 import S3SyncClient, S3SyncConfig
from .secrets import SecretsVault, SecretsVaultError

__all__ = [
    "Manifest",
    "ManifestEntry",
    "ManifestSnapshot",
    "ManifestStore",
    "SyncChange",
    "SyncPlan",
    "build_manifest",
    "diff_manifests",
    "SecretsVault",
    "SecretsVaultError",
    "S3SyncClient",
    "S3SyncConfig",
    "GoogleDriveSyncClient",
    "GoogleDriveSyncConfig",
]
