from __future__ import annotations

import json
import logging
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from comfyvn.config import feature_flags
from comfyvn.config.sync_settings import load_sync_settings
from comfyvn.core import modder_hooks
from comfyvn.sync.cloud import (
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_INCLUDE_FOLDERS,
    GoogleDriveSyncClient,
    GoogleDriveSyncConfig,
    Manifest,
    ManifestStore,
    S3SyncClient,
    S3SyncConfig,
    SecretsVault,
    SecretsVaultError,
    SyncApplyError,
    SyncPlan,
    build_manifest,
    checksum_manifest,
    diff_manifests,
)

logger = logging.getLogger(__name__)

sync_api = APIRouter(prefix="/api/sync", tags=["Cloud Sync"])
backup_api = APIRouter(prefix="/api/backup", tags=["Backups"])
router = APIRouter()
router.include_router(sync_api)
router.include_router(backup_api)

DEFAULT_BACKUP_PATHS: tuple[str, ...] = ("data", "data/scenes", "assets", "config")
DEFAULT_BACKUP_ROTATION: int = 5
BACKUP_META_PREFIX = "__meta__/cloud_sync"


class SyncRequestBase(BaseModel):
    service: str = Field(pattern="^(s3|gdrive)$")
    snapshot: str = Field(default="default", min_length=1, max_length=64)
    paths: Sequence[str] | None = Field(
        default=None, description="Relative paths to include in the manifest"
    )
    exclude: Sequence[str] | None = Field(
        default=None,
        description="Optional glob patterns to exclude from the manifest",
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


class ManifestResponse(BaseModel):
    manifest: Dict[str, Any]
    include: Sequence[str]
    exclude: Sequence[str]
    checksum: str


class SyncDryRunResponse(BaseModel):
    manifest: Dict[str, Any]
    plan: Dict[str, Any]
    summary: Dict[str, Any]
    remote_manifest: Optional[Dict[str, Any]] = None


class SyncRunResponse(BaseModel):
    manifest: Dict[str, Any]
    plan: Dict[str, Any]
    summary: Dict[str, Any]
    committed: bool
    remote_manifest: Optional[Dict[str, Any]] = None


class BackupCreateRequest(BaseModel):
    include: Sequence[str] | None = Field(
        default=None,
        description="Paths to backup relative to project root; defaults to data/scenes/assets/config",
    )
    exclude: Sequence[str] | None = Field(
        default=None,
        description="Additional glob patterns to exclude from the archive",
    )
    label: str | None = Field(
        default=None,
        max_length=48,
        description="Friendly label appended to the archive",
    )
    max_backups: int | None = Field(
        default=None, ge=1, le=50, description="Override for backup rotation limit"
    )


class BackupCreateResponse(BaseModel):
    backup: Dict[str, Any]


class BackupRestoreRequest(BaseModel):
    name: str = Field(description="Backup archive filename (under backups/cloud/)")
    replace_existing: bool = Field(
        default=True,
        description="Replace files on disk when already present; skipped when false",
    )


class BackupRestoreResponse(BaseModel):
    name: str
    restored: int
    skipped: int


class BackupError(RuntimeError):
    """Raised when backup operations fail."""


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
            "status": "dry_run",
            "errors": [],
            "bytes_uploaded": 0,
        }


def _ensure_enabled(service: str | None = None) -> None:
    if not feature_flags.is_enabled("enable_cloud_sync", default=False):
        raise HTTPException(
            status_code=403, detail="enable_cloud_sync feature flag is disabled"
        )
    if service:
        flag = f"enable_cloud_sync_{service}"
        if not feature_flags.is_enabled(flag, default=False):
            raise HTTPException(
                status_code=403, detail=f"{flag} feature flag is disabled"
            )


def _resolve_paths(paths: Sequence[str] | None, *, default: Sequence[str]) -> List[str]:
    candidates = list(paths) if paths else list(default)
    cleaned: list[str] = []
    for value in candidates:
        token = (value or "").strip()
        if not token:
            continue
        token = token.lstrip("./")
        if ".." in token.split("/"):
            raise HTTPException(
                status_code=400, detail=f"invalid path component: {value}"
            )
        if token not in cleaned:
            cleaned.append(token)
    return cleaned or list(default)


def _resolve_exclude(
    patterns: Sequence[str] | None, *, default: Sequence[str]
) -> List[str]:
    if not patterns:
        return list(default)
    cleaned: list[str] = []
    for pattern in patterns:
        token = (pattern or "").strip()
        if not token:
            continue
        if token not in cleaned:
            cleaned.append(token)
    return cleaned or list(default)


def _load_settings() -> Dict[str, Any]:
    settings = load_sync_settings()
    include = settings.get("include") or list(DEFAULT_INCLUDE_FOLDERS)
    exclude = settings.get("exclude") or list(DEFAULT_EXCLUDE_PATTERNS)
    default_root = settings.get("default_root") or "."
    snapshot_prefix = settings.get("snapshot_prefix") or "snapshots"
    return {
        "include": include,
        "exclude": exclude,
        "default_root": default_root,
        "snapshot_prefix": snapshot_prefix,
    }


def _serialise_manifest(manifest: Manifest) -> Dict[str, Any]:
    return {
        "name": manifest.name,
        "root": manifest.root,
        "created_at": manifest.created_at,
        "entries": len(manifest.entries),
        "checksum": checksum_manifest(manifest),
    }


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
            continue
        if segment != segments[-1]:
            logger.warning("Secrets entry %s has non-mapping segment %s", key, segment)
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
    except Exception as exc:  # pragma: no cover - remote failures
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
            "status": summary.get("status", "unknown"),
            "timestamp": time.time(),
        },
    )


class BackupManager:
    def __init__(
        self,
        *,
        base_dir: str | Path = "backups/cloud",
        rotation: int = DEFAULT_BACKUP_ROTATION,
        project_root: str | Path = ".",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.rotation = max(1, int(rotation))
        self.project_root = Path(project_root).resolve()

    def _archive_path(self, timestamp: str, label: str | None) -> Path:
        safe_label = ""
        if label:
            safe_label = "".join(
                ch
                for ch in label.lower().replace(" ", "-")
                if ch.isalnum() or ch in {"-", "_"}
            )
            safe_label = safe_label.strip("-_")
        suffix = f"-{safe_label}" if safe_label else ""
        return self.base_dir / f"{timestamp}{suffix}.zip"

    def _rotate(self) -> list[str]:
        archives = sorted(
            (path for path in self.base_dir.glob("*.zip") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        removed: list[str] = []
        for idx, path in enumerate(archives):
            if idx < self.rotation:
                continue
            try:
                path.unlink()
                removed.append(path.name)
            except OSError as exc:
                logger.warning("Failed to remove old backup %s: %s", path, exc)
        return removed

    def create_backup(
        self,
        include: Sequence[str],
        exclude: Sequence[str],
        *,
        label: str | None = None,
    ) -> Dict[str, Any]:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = self._archive_path(timestamp, label)
        manifest = build_manifest(
            include,
            name=f"backup-{timestamp}",
            root=self.project_root,
            exclude_patterns=exclude,
            follow_symlinks=False,
        )
        checksum = checksum_manifest(manifest)
        bytes_total = sum(entry.size for entry in manifest.entries.values())

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel_path in sorted(manifest.entries):
                source = self.project_root / rel_path
                if not source.exists():
                    logger.debug("Skipping vanished path during backup: %s", source)
                    continue
                zf.write(source, rel_path)
            zf.writestr(
                f"{BACKUP_META_PREFIX}/manifest.json",
                json.dumps(
                    {
                        "created_at": timestamp,
                        "paths": list(include),
                        "exclude": list(exclude),
                        "manifest": manifest.to_dict(),
                        "checksum": checksum,
                    },
                    indent=2,
                ),
            )

        removed = self._rotate()

        logger.info(
            "Created backup archive",
            extra={
                "path": str(archive_path),
                "files": len(manifest.entries),
                "bytes": bytes_total,
                "removed": removed,
            },
        )
        return {
            "name": archive_path.name,
            "path": str(archive_path),
            "files": len(manifest.entries),
            "bytes": bytes_total,
            "checksum": checksum,
            "removed": removed,
        }

    def restore_backup(
        self, name: str, *, replace_existing: bool = True
    ) -> Dict[str, Any]:
        archive_path = self.base_dir / name
        if not archive_path.exists():
            raise BackupError(f"backup archive not found: {archive_path}")

        restored = 0
        skipped = 0

        with zipfile.ZipFile(archive_path, "r") as zf:
            members = zf.infolist()
            for member in members:
                filename = member.filename
                if filename.endswith("/"):
                    continue
                if filename.startswith(f"{BACKUP_META_PREFIX}/"):
                    continue

                destination = (self.project_root / filename).resolve()
                if not str(destination).startswith(str(self.project_root)):
                    raise BackupError(
                        f"refusing to extract outside project root: {filename}"
                    )

                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() and not replace_existing:
                    skipped += 1
                    continue

                with zf.open(member, "r") as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored += 1

        logger.info(
            "Restored backup archive",
            extra={
                "path": str(archive_path),
                "restored": restored,
                "skipped": skipped,
                "replace_existing": replace_existing,
            },
        )
        return {"name": name, "restored": restored, "skipped": skipped}


@sync_api.get("/manifest", response_model=ManifestResponse)
async def sync_manifest(
    snapshot: str = Query("default", min_length=1, max_length=64),
    include: str | None = Query(
        default=None,
        description="Comma separated list of relative paths to include in the manifest",
    ),
    exclude: str | None = Query(
        default=None,
        description="Comma separated list of glob patterns to exclude",
    ),
    follow_symlinks: bool = Query(
        default=False, description="Follow symlinks when walking include paths"
    ),
) -> ManifestResponse:
    _ensure_enabled()
    settings = _load_settings()
    include_paths = _resolve_paths(
        include.split(",") if include else None, default=settings["include"]
    )
    exclude_patterns = _resolve_exclude(
        exclude.split(",") if exclude else None, default=settings["exclude"]
    )
    manifest = build_manifest(
        include_paths,
        name=snapshot,
        root=settings["default_root"],
        exclude_patterns=exclude_patterns,
        follow_symlinks=follow_symlinks,
    )
    return ManifestResponse(
        manifest=_serialise_manifest(manifest),
        include=include_paths,
        exclude=exclude_patterns,
        checksum=checksum_manifest(manifest),
    )


@sync_api.post("/dry_run", response_model=SyncDryRunResponse)
async def sync_dry_run(payload: SyncDryRunRequest) -> SyncDryRunResponse:
    _ensure_enabled(payload.service)
    settings = _load_settings()
    include_paths = _resolve_paths(payload.paths, default=settings["include"])
    exclude_patterns = _resolve_exclude(payload.exclude, default=settings["exclude"])
    manifest = build_manifest(
        include_paths,
        name=payload.snapshot,
        root=settings["default_root"],
        exclude_patterns=exclude_patterns,
        follow_symlinks=payload.follow_symlinks,
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
    remote_summary = _serialise_manifest(remote_manifest) if remote_manifest else None
    return SyncDryRunResponse(
        manifest=_serialise_manifest(manifest),
        plan=plan.to_dict(),
        summary=summary,
        remote_manifest=remote_summary,
    )


@sync_api.post("/run", response_model=SyncRunResponse)
async def sync_run(payload: SyncRunRequest) -> SyncRunResponse:
    _ensure_enabled(payload.service)
    settings = _load_settings()
    include_paths = _resolve_paths(payload.paths, default=settings["include"])
    exclude_patterns = _resolve_exclude(payload.exclude, default=settings["exclude"])
    manifest = build_manifest(
        include_paths,
        name=payload.snapshot,
        root=settings["default_root"],
        exclude_patterns=exclude_patterns,
        follow_symlinks=payload.follow_symlinks,
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

    summary: Dict[str, Any]
    committed = False
    try:
        summary = client.apply_plan(plan, manifest, dry_run=False)
    except SyncApplyError as exc:
        summary = dict(exc.summary)
        summary.setdefault("status", "partial")
        summary.setdefault("errors", exc.errors)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"sync failed: {exc}") from exc
    else:
        if payload.commit_manifest:
            store.save(payload.service, payload.snapshot, manifest)
            committed = True

    _emit_complete_hook(plan, summary)
    remote_summary = _serialise_manifest(remote_manifest) if remote_manifest else None
    return SyncRunResponse(
        manifest=_serialise_manifest(manifest),
        plan=plan.to_dict(),
        summary=summary,
        committed=committed,
        remote_manifest=remote_summary,
    )


@backup_api.post("/create", response_model=BackupCreateResponse)
async def backup_create(payload: BackupCreateRequest) -> BackupCreateResponse:
    _ensure_enabled()
    settings = _load_settings()
    include_paths = _resolve_paths(payload.include, default=DEFAULT_BACKUP_PATHS)
    exclude_patterns = _resolve_exclude(payload.exclude, default=settings["exclude"])
    manager = BackupManager(
        rotation=payload.max_backups or DEFAULT_BACKUP_ROTATION,
        project_root=settings["default_root"],
    )
    backup_info = manager.create_backup(
        include_paths,
        exclude_patterns,
        label=payload.label,
    )
    return BackupCreateResponse(backup=backup_info)


@backup_api.post("/restore", response_model=BackupRestoreResponse)
async def backup_restore(payload: BackupRestoreRequest) -> BackupRestoreResponse:
    _ensure_enabled()
    settings = _load_settings()
    manager = BackupManager(project_root=settings["default_root"])
    try:
        result = manager.restore_backup(
            payload.name, replace_existing=payload.replace_existing
        )
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BackupRestoreResponse(**result)


__all__ = [
    "router",
    "sync_api",
    "backup_api",
    "sync_manifest",
    "sync_dry_run",
    "sync_run",
    "backup_create",
    "backup_restore",
]
