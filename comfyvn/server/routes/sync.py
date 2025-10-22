from __future__ import annotations

import logging
import time
from typing import Any, Dict, Mapping, Sequence

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.core import modder_hooks
from comfyvn.sync.cloud import (
    GoogleDriveSyncClient,
    GoogleDriveSyncConfig,
    Manifest,
    ManifestStore,
    S3SyncClient,
    S3SyncConfig,
    SecretsVault,
    SecretsVaultError,
    SyncPlan,
    build_manifest,
    diff_manifests,
)

router = APIRouter(prefix="/api/sync", tags=["Sync"])
logger = logging.getLogger(__name__)

DEFAULT_PATHS: tuple[str, ...] = ("assets", "config", "defaults", "docs")
MAX_PATHS: int = 32


class SyncRequestBase(BaseModel):
    service: str = Field(pattern="^(s3|gdrive)$")
    snapshot: str = Field(default="default", min_length=1, max_length=64)
    paths: Sequence[str] | None = Field(
        default=None, description="Relative paths to include in the manifest"
    )
    follow_symlinks: bool = Field(default=False)
    credentials_key: str | None = Field(
        default="cloud_sync.default",
        description="Secrets vault key resolving to provider credentials/config.",
    )
    service_config: Dict[str, Any] | None = Field(
        default=None,
        description="Optional inline overrides merged into the provider config",
    )

    model_config = ConfigDict(extra="forbid")


class SyncDryRunRequest(SyncRequestBase):
    model_config = ConfigDict(extra="forbid")


class SyncRunRequest(SyncRequestBase):
    commit_manifest: bool = Field(
        default=True,
        description="Persist the generated manifest locally after a successful sync",
    )

    model_config = ConfigDict(extra="forbid")


class SyncDryRunResponse(BaseModel):
    plan: Dict[str, Any]
    manifest: Dict[str, Any]
    summary: Dict[str, Any]


class SyncRunResponse(BaseModel):
    plan: Dict[str, Any]
    manifest: Dict[str, Any]
    summary: Dict[str, Any]
    committed: bool


class _DryRunOnlyClient:
    def __init__(self, service: str, reason: str) -> None:
        self.service = service
        self._reason = reason

    def fetch_remote_manifest(
        self, snapshot: str
    ) -> None:  # pragma: no cover - simple stub
        return None

    def apply_plan(
        self, plan: SyncPlan, manifest: Manifest, *, dry_run: bool = False
    ) -> Dict[str, Any]:
        if not dry_run:
            raise RuntimeError(self._reason)
        logger.warning(
            "Provider SDK missing for %s; returning dry-run summary only",
            self.service,
            extra={"service": self.service, "snapshot": plan.snapshot},
        )
        return {
            "service": plan.service,
            "snapshot": plan.snapshot,
            "uploads": [change.to_dict() for change in plan.uploads],
            "deletes": [change.to_dict() for change in plan.deletes],
            "skipped": [change.to_dict() for change in plan.unchanged],
        }


def _ensure_enabled(service: str) -> None:
    if not feature_flags.is_enabled("enable_cloud_sync", default=False):
        raise HTTPException(
            status_code=403, detail="enable_cloud_sync feature flag is disabled"
        )
    flag = f"enable_cloud_sync_{service}"
    if not feature_flags.is_enabled(flag, default=False):
        raise HTTPException(status_code=403, detail=f"{flag} feature flag is disabled")


def _resolve_paths(paths: Sequence[str] | None) -> Sequence[str]:
    if not paths:
        return DEFAULT_PATHS
    if len(paths) > MAX_PATHS:
        raise HTTPException(
            status_code=400, detail=f"at most {MAX_PATHS} paths may be provided"
        )
    cleaned: list[str] = []
    for value in paths:
        token = value.strip().lstrip("./")
        if not token:
            continue
        if ".." in token.split("/"):
            raise HTTPException(
                status_code=400, detail=f"invalid path component: {value}"
            )
        cleaned.append(token)
    return cleaned or DEFAULT_PATHS


def _load_secrets_entry(vault: SecretsVault, key: str | None) -> Mapping[str, Any]:
    if not key:
        return {}
    segments = [segment for segment in key.split(".") if segment]
    if not segments:
        return {}
    try:
        payload = vault.unlock()
    except SecretsVaultError as exc:
        raise HTTPException(
            status_code=500, detail=f"secrets vault error: {exc}"
        ) from exc
    current: Mapping[str, Any] = payload
    for segment in segments:
        value = current.get(segment) if isinstance(current, Mapping) else None
        if value is None:
            logger.warning("Secrets entry %s missing segment %s", key, segment)
            return {}
        if isinstance(value, Mapping):
            current = value
        else:
            if segment != segments[-1]:
                logger.warning(
                    "Secrets entry %s has non-mapping segment %s", key, segment
                )
                return {}
            return {segment: value}
    return current


def _merge_config(
    base: Mapping[str, Any], override: Mapping[str, Any] | None
) -> Dict[str, Any]:
    merged = dict(base)
    if override:
        for key, value in override.items():
            merged[key] = value
    return merged


def _split_s3_config(config: Mapping[str, Any]) -> tuple[S3SyncConfig, Dict[str, Any]]:
    credential_keys = {
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
    }
    config_map = dict(config)
    credentials = {
        key: config_map.pop(key)
        for key in list(config_map.keys())
        if key in credential_keys
    }
    try:
        provider_config = S3SyncConfig.from_mapping(config_map)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid s3 config: {exc}"
        ) from exc
    return provider_config, credentials


def _build_s3_client(
    config: Mapping[str, Any], *, allow_stub: bool
) -> S3SyncClient | _DryRunOnlyClient:
    provider_config, credentials = _split_s3_config(config)
    try:
        return S3SyncClient(provider_config, credentials=credentials)
    except RuntimeError as exc:
        if allow_stub:
            return _DryRunOnlyClient("s3", reason=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _build_drive_client(
    config: Mapping[str, Any], *, allow_stub: bool
) -> GoogleDriveSyncClient | _DryRunOnlyClient:
    if "credentials" in config:
        credentials_info = config["credentials"]
    elif "service_account" in config:
        credentials_info = config["service_account"]
    else:
        raise HTTPException(
            status_code=400, detail="gdrive config requires credentials/service_account"
        )
    if not isinstance(credentials_info, Mapping):
        raise HTTPException(
            status_code=400, detail="gdrive credentials must be an object"
        )
    try:
        provider_config = GoogleDriveSyncConfig.from_mapping(config)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid gdrive config: {exc}"
        ) from exc
    try:
        return GoogleDriveSyncClient(provider_config, credentials_info=credentials_info)
    except RuntimeError as exc:
        if allow_stub:
            return _DryRunOnlyClient("gdrive", reason=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _build_client(service: str, config: Mapping[str, Any], *, allow_stub: bool):
    if not config:
        raise HTTPException(
            status_code=400,
            detail="service config is empty - populate the secrets vault",
        )
    if service == "s3":
        return _build_s3_client(config, allow_stub=allow_stub)
    if service == "gdrive":
        return _build_drive_client(config, allow_stub=allow_stub)
    raise HTTPException(status_code=400, detail=f"unsupported service: {service}")


def _load_remote_manifest(
    client: Any, service: str, snapshot: str, store: ManifestStore
) -> Manifest | None:
    try:
        remote_manifest = client.fetch_remote_manifest(snapshot)
        if remote_manifest:
            return remote_manifest
    except Exception as exc:
        logger.warning(
            "Remote manifest fetch failed",
            extra={"service": service, "snapshot": snapshot, "error": str(exc)},
        )
    cached = store.load(service, snapshot)
    if cached:
        logger.info(
            "Using cached manifest for %s/%s",
            service,
            snapshot,
            extra={
                "service": service,
                "snapshot": snapshot,
                "entries": len(cached.entries),
            },
        )
    return cached


def _serialise_manifest(manifest: Manifest) -> Dict[str, Any]:
    return {
        "name": manifest.name,
        "root": manifest.root,
        "created_at": manifest.created_at,
        "entries": len(manifest.entries),
    }


def _emit_plan_hook(plan: SyncPlan) -> None:
    modder_hooks.emit(
        "on_cloud_sync_plan",
        {
            "service": plan.service,
            "snapshot": plan.snapshot,
            "uploads": len(plan.uploads),
            "deletes": len(plan.deletes),
            "bytes": plan.bytes_to_upload,
            "timestamp": time.time(),
        },
    )


def _emit_complete_hook(plan: SyncPlan, summary: Mapping[str, Any]) -> None:
    modder_hooks.emit(
        "on_cloud_sync_complete",
        {
            "service": plan.service,
            "snapshot": plan.snapshot,
            "uploads": len(summary.get("uploads", [])),
            "deletes": len(summary.get("deletes", [])),
            "skipped": len(summary.get("skipped", [])),
            "timestamp": time.time(),
        },
    )


@router.post("/dry-run", response_model=SyncDryRunResponse)
async def sync_dry_run(payload: SyncDryRunRequest) -> SyncDryRunResponse:
    _ensure_enabled(payload.service)
    include_paths = _resolve_paths(payload.paths)
    manifest = build_manifest(
        include_paths, name=payload.snapshot, follow_symlinks=payload.follow_symlinks
    )
    vault = SecretsVault()
    secrets_entry = _load_secrets_entry(vault, payload.credentials_key)
    merged_config = _merge_config(secrets_entry, payload.service_config)

    client = _build_client(payload.service, merged_config, allow_stub=True)
    store = ManifestStore()
    remote_manifest = _load_remote_manifest(
        client, payload.service, payload.snapshot, store
    )
    plan = diff_manifests(payload.service, payload.snapshot, manifest, remote_manifest)
    try:
        summary = client.apply_plan(plan, manifest, dry_run=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"dry-run failed: {exc}") from exc
    _emit_plan_hook(plan)

    return SyncDryRunResponse(
        plan=plan.to_dict(),
        manifest=_serialise_manifest(manifest),
        summary=summary,
    )


@router.post("/run", response_model=SyncRunResponse)
async def sync_run(payload: SyncRunRequest) -> SyncRunResponse:
    _ensure_enabled(payload.service)
    include_paths = _resolve_paths(payload.paths)
    manifest = build_manifest(
        include_paths, name=payload.snapshot, follow_symlinks=payload.follow_symlinks
    )
    vault = SecretsVault()
    secrets_entry = _load_secrets_entry(vault, payload.credentials_key)
    merged_config = _merge_config(secrets_entry, payload.service_config)
    client = _build_client(payload.service, merged_config, allow_stub=False)

    store = ManifestStore()
    remote_manifest = _load_remote_manifest(
        client, payload.service, payload.snapshot, store
    )
    plan = diff_manifests(payload.service, payload.snapshot, manifest, remote_manifest)

    try:
        summary = client.apply_plan(plan, manifest, dry_run=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"sync failed: {exc}") from exc

    committed = False
    if payload.commit_manifest:
        store.save(payload.service, payload.snapshot, manifest)
        committed = True

    _emit_complete_hook(plan, summary)
    return SyncRunResponse(
        plan=plan.to_dict(),
        manifest=_serialise_manifest(manifest),
        summary=summary,
        committed=committed,
    )


__all__ = [
    "router",
    "sync_dry_run",
    "sync_run",
    "SyncDryRunRequest",
    "SyncRunRequest",
    "SyncDryRunResponse",
    "SyncRunResponse",
]
