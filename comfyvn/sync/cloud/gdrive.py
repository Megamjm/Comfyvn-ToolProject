from __future__ import annotations

"""
Google Drive sync helper built on top of the Drive v3 API.

The implementation favours deterministic object metadata so delta syncs remain
idempotent; each uploaded file carries an ``appProperties`` entry that stores the
logical project-relative path.  Deletions look up records via this property so Drive
folder layout may stay flat or be organised manually by administrators.
"""

import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from .manifest import Manifest, SyncApplyError, SyncPlan

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import (
        MediaFileUpload,
        MediaIoBaseDownload,
        MediaIoBaseUpload,
    )
except Exception:  # pragma: no cover - optional dependency
    ServiceAccountCredentials = None  # type: ignore
    build = None  # type: ignore
    HttpError = Exception  # type: ignore[assignment]
    MediaFileUpload = None  # type: ignore
    MediaIoBaseDownload = None  # type: ignore
    MediaIoBaseUpload = None  # type: ignore


@dataclass(slots=True)
class GoogleDriveSyncConfig:
    parent_id: str
    manifest_parent_id: str
    scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/drive.file",)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GoogleDriveSyncConfig":
        parent_id = data.get("parent_id")
        manifest_parent_id = data.get("manifest_parent_id") or parent_id
        if not isinstance(parent_id, str) or not parent_id:
            raise ValueError("Google Drive sync config requires parent_id")
        if not isinstance(manifest_parent_id, str) or not manifest_parent_id:
            raise ValueError("Google Drive sync config requires manifest_parent_id")
        scopes = data.get("scopes")
        if isinstance(scopes, (list, tuple)) and scopes:
            scopes_tuple = tuple(str(scope) for scope in scopes)
        else:
            scopes_tuple = ("https://www.googleapis.com/auth/drive.file",)
        return cls(
            parent_id=parent_id,
            manifest_parent_id=manifest_parent_id,
            scopes=scopes_tuple,
        )


class GoogleDriveSyncClient:
    PATH_PROPERTY = "comfyvn_path"

    def __init__(
        self, config: GoogleDriveSyncConfig, *, credentials_info: Mapping[str, Any]
    ) -> None:
        if build is None or ServiceAccountCredentials is None:
            raise RuntimeError(
                "google-api-python-client is required for Drive sync operations"
            )

        credentials = ServiceAccountCredentials.from_service_account_info(
            dict(credentials_info),
            scopes=list(config.scopes),
        )
        self.service = build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )
        self.config = config

    # -- Manifest management -------------------------------------------------------

    def fetch_remote_manifest(self, snapshot: str) -> Manifest | None:
        file_meta = self._find_manifest_file(snapshot)
        if not file_meta:
            return None
        file_id = file_meta["id"]
        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:  # pragma: no branch - simple loop
            _, done = downloader.next_chunk()
        buffer.seek(0)
        payload = json.loads(buffer.read().decode("utf-8"))
        manifest_payload = (
            payload.get("manifest") if isinstance(payload, dict) else payload
        )
        if not isinstance(manifest_payload, dict):
            logger.warning("Remote manifest payload malformed on Drive: %s", file_id)
            return None
        manifest = Manifest.from_dict(manifest_payload)
        return manifest

    def upload_manifest(self, snapshot: str, manifest: Manifest) -> None:
        payload = json.dumps({"manifest": manifest.to_dict()}, indent=2).encode("utf-8")
        metadata = {
            "name": f"{snapshot}.json",
            "parents": [self.config.manifest_parent_id],
        }
        upload = MediaIoBaseUpload(
            io.BytesIO(payload), mimetype="application/json", resumable=False
        )
        existing = self._find_manifest_file(snapshot)
        if existing:
            self.service.files().update(
                fileId=existing["id"], media_body=upload
            ).execute()
        else:
            self.service.files().create(body=metadata, media_body=upload).execute()
        logger.info(
            "Uploaded Drive manifest",
            extra={"snapshot": snapshot, "entries": len(manifest.entries)},
        )

    # -- Plan execution ------------------------------------------------------------

    def apply_plan(
        self, plan: SyncPlan, manifest: Manifest, *, dry_run: bool = False
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "service": "gdrive",
            "snapshot": plan.snapshot,
            "root": manifest.root,
            "uploads": [],
            "deletes": [],
            "skipped": [],
            "status": "dry_run" if dry_run else "pending",
        }
        if dry_run:
            summary["uploads"] = [change.to_dict() for change in plan.uploads]
            summary["deletes"] = [change.to_dict() for change in plan.deletes]
            summary["skipped"] = [change.to_dict() for change in plan.unchanged]
            summary["errors"] = []
            summary["bytes_uploaded"] = 0
            logger.info(
                "Drive dry-run computed",
                extra={
                    "uploads": len(plan.uploads),
                    "deletes": len(plan.deletes),
                    "unchanged": len(plan.unchanged),
                    "snapshot": plan.snapshot,
                },
            )
            return summary

        root = Path(manifest.root)
        uploaded: list[str] = []
        deleted: list[str] = []
        errors: list[Dict[str, Any]] = []
        bytes_uploaded = 0

        for change in plan.uploads:
            local_path = root / change.path
            metadata = {
                "name": change.path.split("/")[-1],
                "parents": [self.config.parent_id],
                "appProperties": {self.PATH_PROPERTY: change.path},
            }
            try:
                if not local_path.exists():
                    raise FileNotFoundError(f"local file missing: {local_path}")
                media = MediaFileUpload(str(local_path), resumable=True)
                existing = self._find_file_by_path(change.path)
                if existing:
                    self.service.files().update(
                        fileId=existing["id"],
                        body={"appProperties": metadata["appProperties"]},
                        media_body=media,
                    ).execute()
                else:
                    self.service.files().create(
                        body=metadata, media_body=media
                    ).execute()
                uploaded.append(change.path)
                bytes_uploaded += local_path.stat().st_size
            except HttpError as exc:  # pragma: no cover - API failure path
                logger.warning(
                    "Drive upload failed",
                    extra={
                        "path": change.path,
                        "snapshot": plan.snapshot,
                        "error": str(exc),
                    },
                )
                errors.append(
                    {"action": "upload", "path": change.path, "error": str(exc)}
                )
            except Exception as exc:
                logger.warning(
                    "Drive upload failed",
                    extra={
                        "path": change.path,
                        "snapshot": plan.snapshot,
                        "error": str(exc),
                    },
                )
                errors.append(
                    {"action": "upload", "path": change.path, "error": str(exc)}
                )

        for change in plan.deletes:
            existing = self._find_file_by_path(change.path)
            if existing:
                try:
                    self.service.files().delete(fileId=existing["id"]).execute()
                    deleted.append(change.path)
                except HttpError as exc:  # pragma: no cover - API failure path
                    logger.warning(
                        "Failed to delete %s from Drive: %s", change.path, exc
                    )
                    errors.append(
                        {"action": "delete", "path": change.path, "error": str(exc)}
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to delete %s from Drive: %s", change.path, exc
                    )
                    errors.append(
                        {"action": "delete", "path": change.path, "error": str(exc)}
                    )

        summary["uploads"] = uploaded
        summary["deletes"] = deleted
        summary["skipped"] = [change.path for change in plan.unchanged]
        summary["errors"] = errors
        summary["bytes_uploaded"] = bytes_uploaded
        summary["status"] = "ok" if not errors else "partial"

        logger.info(
            "Drive sync applied",
            extra={
                "uploads": len(uploaded),
                "deletes": len(deleted),
                "snapshot": plan.snapshot,
                "errors": len(errors),
            },
        )
        if errors:
            raise SyncApplyError(
                f"Drive sync failed for {len(errors)} operations",
                summary=summary,
                errors=errors,
            )
        self.upload_manifest(plan.snapshot, manifest)
        summary["status"] = "ok"
        return summary

    # -- Helpers -------------------------------------------------------------------

    def _find_file_by_path(self, rel_path: str) -> Dict[str, Any] | None:
        query = (
            f"'{self.config.parent_id}' in parents and "
            f"appProperties has {{ key='{self.PATH_PROPERTY}' and value='{rel_path}' }} "
            "and trashed = false"
        )
        response = (
            self.service.files()
            .list(
                q=query,
                fields="files(id, name, appProperties)",
                spaces="drive",
                pageSize=10,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0] if files else None

    def _find_manifest_file(self, snapshot: str) -> Dict[str, Any] | None:
        query = (
            f"'{self.config.manifest_parent_id}' in parents and "
            f"name = '{snapshot}.json' and trashed = false"
        )
        response = (
            self.service.files()
            .list(
                q=query,
                fields="files(id, name)",
                spaces="drive",
                pageSize=10,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0] if files else None


__all__ = ["GoogleDriveSyncClient", "GoogleDriveSyncConfig"]
