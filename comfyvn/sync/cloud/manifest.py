from __future__ import annotations

"""
Manifest helpers for cloud sync providers.

The manifest format is intentionally simple and records enough metadata to
detect drift even when timestamps diverge:

```
{
    "name": "nightly",
    "root": "/abs/path",
    "created_at": "2025-11-18T04:05:06Z",
    "entries": {
        "assets/sprite.png": {
            "size": 1024,
            "mtime": 1731912306.123,
            "sha256": "..."
        }
    }
}
```
"""

import fnmatch
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Sequence

logger = logging.getLogger(__name__)

DEFAULT_INCLUDE_FOLDERS: tuple[str, ...] = (
    "assets",
    "config",
    "defaults",
    "docs",
    "extensions",
    "models",
    "scripts",
    "studio",
)

DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "*.pyc",
    "*.pyo",
    "*.swp",
    "*.tmp",
    "cache",
    "cache/*",
    "logs",
    "logs/*",
    "tmp",
    "tmp/*",
)


@dataclass(slots=True)
class ManifestEntry:
    path: str
    size: int
    mtime: float
    sha256: str

    def to_dict(self) -> Dict[str, float | int | str]:
        return {
            "path": self.path,
            "size": self.size,
            "mtime": self.mtime,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ManifestEntry":
        return cls(
            path=str(data["path"]),
            size=int(data["size"]),
            mtime=float(data["mtime"]),
            sha256=str(data["sha256"]),
        )


@dataclass(slots=True)
class Manifest:
    name: str
    root: str
    created_at: str
    entries: Dict[str, ManifestEntry] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "root": self.root,
            "created_at": self.created_at,
            "entries": {path: entry.to_dict() for path, entry in self.entries.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Manifest":
        raw_entries = data.get("entries") or {}
        entries: Dict[str, ManifestEntry] = {}
        if isinstance(raw_entries, Mapping):
            for path, payload in raw_entries.items():
                if isinstance(payload, Mapping):
                    entries[str(path)] = ManifestEntry.from_dict(payload)
        return cls(
            name=str(data.get("name", "default")),
            root=str(data.get("root", ".")),
            created_at=str(data.get("created_at", "")),
            entries=entries,
        )


@dataclass(slots=True)
class ManifestSnapshot:
    service: str
    name: str
    manifest: Manifest
    checksum: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "service": self.service,
            "name": self.name,
            "checksum": self.checksum,
            "manifest": self.manifest.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ManifestSnapshot":
        manifest_data = data.get("manifest")
        manifest = (
            Manifest.from_dict(manifest_data)
            if isinstance(manifest_data, Mapping)
            else Manifest(
                name=str(data.get("name", "default")),
                root=str(data.get("manifest_root", ".")),
                created_at=str(data.get("manifest_created_at", "")),
                entries={},
            )
        )
        return cls(
            service=str(data.get("service", "")),
            name=manifest.name,
            manifest=manifest,
            checksum=str(data.get("checksum", "")),
        )


@dataclass(slots=True)
class SyncChange:
    action: str
    path: str
    size: int = 0
    sha256: str | None = None
    reason: str | None = None

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {"action": self.action, "path": self.path}
        if self.size:
            payload["size"] = self.size
        if self.sha256:
            payload["sha256"] = self.sha256
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(slots=True)
class SyncPlan:
    service: str
    snapshot: str
    uploads: list[SyncChange]
    deletes: list[SyncChange]
    unchanged: list[SyncChange]
    bytes_to_upload: int = 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "service": self.service,
            "snapshot": self.snapshot,
            "uploads": [change.to_dict() for change in self.uploads],
            "deletes": [change.to_dict() for change in self.deletes],
            "unchanged": [change.to_dict() for change in self.unchanged],
            "bytes_to_upload": self.bytes_to_upload,
            "files_to_upload": len(self.uploads),
            "files_to_delete": len(self.deletes),
            "files_unchanged": len(self.unchanged),
        }


class SyncApplyError(RuntimeError):
    """Raised when a sync plan could not be applied completely."""

    def __init__(
        self,
        message: str,
        *,
        summary: Mapping[str, Any],
        errors: Sequence[Mapping[str, Any]],
    ) -> None:
        super().__init__(message)
        self.summary: Dict[str, Any] = dict(summary)
        self.errors: list[Dict[str, Any]] = [
            dict(error) for error in errors if isinstance(error, Mapping)
        ]


def _normalise_path(path: Path, *, root: Path) -> str:
    return str(path.relative_to(root).as_posix())


def _iter_files(
    paths: Sequence[Path],
    *,
    follow_symlinks: bool = False,
    root: Path,
    exclude_patterns: Sequence[str],
) -> Iterator[Path]:
    exclude_patterns = tuple(exclude_patterns)

    def _is_excluded(candidate: Path) -> bool:
        rel = _normalise_path(candidate, root=root)
        for pattern in exclude_patterns:
            if not pattern:
                continue
            simple = pattern.rstrip("/")
            if simple and not any(ch in pattern for ch in "*?[]"):
                if rel == simple or rel.startswith(f"{simple}/"):
                    return True
            if fnmatch.fnmatch(rel, pattern):
                return True
        return False

    for base in paths:
        if not follow_symlinks and base.is_symlink():
            continue
        if not base.exists():
            logger.debug("Skipping missing path during manifest iteration: %s", base)
            continue
        stack: list[Path] = [base]
        while stack:
            current = stack.pop()
            if not follow_symlinks and current.is_symlink():
                continue
            if _is_excluded(current):
                continue
            if current.is_dir():
                try:
                    children = sorted(current.iterdir())
                except (OSError, PermissionError) as exc:
                    logger.warning("Cannot list %s: %s", current, exc)
                    continue
                stack.extend(children)
                continue
            if current.is_file():
                yield current


def _hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    paths: Sequence[str | os.PathLike[str]],
    *,
    name: str = "default",
    root: str | os.PathLike[str] | None = None,
    exclude_patterns: Sequence[str] | None = None,
    follow_symlinks: bool = False,
) -> Manifest:
    root_path = Path(root or ".").resolve()
    exclusions: Sequence[str] = (
        tuple(exclude_patterns)
        if exclude_patterns is not None
        else DEFAULT_EXCLUDE_PATTERNS
    )
    resolved_paths: list[Path] = []
    for entry in paths:
        candidate = Path(entry)
        resolved = (
            candidate if candidate.is_absolute() else root_path.joinpath(candidate)
        )
        if resolved.exists():
            resolved_paths.append(resolved)
        else:
            logger.debug("Skipping missing path during manifest build: %s", entry)

    entries: Dict[str, ManifestEntry] = {}
    for file_path in _iter_files(
        resolved_paths,
        follow_symlinks=follow_symlinks,
        root=root_path,
        exclude_patterns=exclusions,
    ):
        try:
            stat_result = file_path.stat()
            rel_path = _normalise_path(file_path, root=root_path)
            entries[rel_path] = ManifestEntry(
                path=rel_path,
                size=int(stat_result.st_size),
                mtime=float(stat_result.st_mtime),
                sha256=_hash_file(file_path),
            )
        except (OSError, PermissionError) as exc:
            logger.warning("Failed to add %s to manifest: %s", file_path, exc)

    created_at = datetime.now(tz=timezone.utc).isoformat()
    manifest = Manifest(
        name=name, root=str(root_path), created_at=created_at, entries=entries
    )
    logger.info(
        "Built manifest %s with %d entries",
        name,
        len(entries),
        extra={"manifest_name": name, "manifest_entries": len(entries)},
    )
    return manifest


def checksum_manifest(manifest: Manifest) -> str:
    return _checksum_manifest(manifest.entries)


def _checksum_manifest(entries: Mapping[str, ManifestEntry]) -> str:
    digest = hashlib.sha256()
    for path, entry in sorted(entries.items()):
        digest.update(path.encode("utf-8"))
        digest.update(str(entry.size).encode("utf-8"))
        digest.update(str(entry.mtime).encode("utf-8"))
        digest.update(entry.sha256.encode("utf-8"))
    return digest.hexdigest()


def diff_manifests(
    service: str,
    snapshot: str,
    local: Manifest,
    remote: Manifest | None,
) -> SyncPlan:
    remote_entries = remote.entries if remote else {}
    uploads: list[SyncChange] = []
    deletes: list[SyncChange] = []
    unchanged: list[SyncChange] = []

    for path, entry in local.entries.items():
        remote_entry = remote_entries.get(path)
        if remote_entry is None:
            uploads.append(
                SyncChange(
                    "upload",
                    path=path,
                    size=entry.size,
                    sha256=entry.sha256,
                    reason="missing_remote",
                )
            )
        elif remote_entry.sha256 != entry.sha256:
            uploads.append(
                SyncChange(
                    "upload",
                    path=path,
                    size=entry.size,
                    sha256=entry.sha256,
                    reason="content_mismatch",
                )
            )
        else:
            unchanged.append(
                SyncChange("skip", path=path, size=entry.size, sha256=entry.sha256)
            )

    for path, entry in remote_entries.items():
        if path not in local.entries:
            deletes.append(
                SyncChange(
                    "delete",
                    path=path,
                    size=entry.size,
                    sha256=entry.sha256,
                    reason="missing_local",
                )
            )

    plan = SyncPlan(
        service=service,
        snapshot=snapshot,
        uploads=uploads,
        deletes=deletes,
        unchanged=unchanged,
        bytes_to_upload=sum(change.size for change in uploads),
    )
    logger.info(
        "Computed sync plan",
        extra={
            "service": service,
            "snapshot": snapshot,
            "uploads": len(plan.uploads),
            "deletes": len(plan.deletes),
            "unchanged": len(plan.unchanged),
        },
    )
    return plan


class ManifestStore:
    """Persist manifests locally so delta syncs can remain idempotent between runs."""

    def __init__(
        self, base_dir: str | os.PathLike[str] = "cache/cloud/manifests"
    ) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, service: str, snapshot: str) -> Path:
        return self.base_dir / service / f"{snapshot}.json"

    def load(self, service: str, snapshot: str) -> Manifest | None:
        path = self._path_for(service, snapshot)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Manifest decode failed for %s: %s", path, exc)
            return None
        manifest_data = (
            payload.get("manifest") if isinstance(payload, Mapping) else payload
        )
        if not isinstance(manifest_data, Mapping):
            logger.warning("Manifest payload missing mapping for %s", path)
            return None
        return Manifest.from_dict(manifest_data)

    def save(self, service: str, snapshot: str, manifest: Manifest) -> ManifestSnapshot:
        path = self._path_for(service, snapshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        checksum = _checksum_manifest(manifest.entries)
        snapshot_payload = ManifestSnapshot(
            service=service, name=snapshot, manifest=manifest, checksum=checksum
        )
        path.write_text(
            json.dumps(snapshot_payload.to_dict(), indent=2), encoding="utf-8"
        )
        logger.info(
            "Persisted manifest",
            extra={
                "service": service,
                "snapshot": snapshot,
                "entries": len(manifest.entries),
                "checksum": checksum,
            },
        )
        return snapshot_payload


__all__ = [
    "DEFAULT_INCLUDE_FOLDERS",
    "DEFAULT_EXCLUDE_PATTERNS",
    "Manifest",
    "ManifestEntry",
    "ManifestSnapshot",
    "ManifestStore",
    "SyncChange",
    "SyncPlan",
    "SyncApplyError",
    "build_manifest",
    "checksum_manifest",
    "diff_manifests",
]
