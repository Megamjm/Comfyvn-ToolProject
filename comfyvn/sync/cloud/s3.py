from __future__ import annotations

"""
Amazon S3 sync helper.

This module intentionally keeps dependencies optional so developers can run dry
runs without installing ``boto3``.  When uploads/deletes are requested the code
tries to import ``boto3`` and raises a helpful error if the package is missing.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from .manifest import Manifest, SyncPlan

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import boto3
    from botocore.exceptions import ClientError  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    boto3 = None
    ClientError = Exception  # type: ignore[assignment]


@dataclass(slots=True)
class S3SyncConfig:
    bucket: str
    prefix: str = ""
    region: str | None = None
    profile: str | None = None
    endpoint_url: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "S3SyncConfig":
        bucket = data.get("bucket")
        if not isinstance(bucket, str) or not bucket:
            raise ValueError("S3 config requires a bucket name")
        return cls(
            bucket=bucket,
            prefix=str(data.get("prefix", "")).rstrip("/"),
            region=str(data["region"]) if isinstance(data.get("region"), str) else None,
            profile=(
                str(data["profile"]) if isinstance(data.get("profile"), str) else None
            ),
            endpoint_url=(
                str(data["endpoint_url"])
                if isinstance(data.get("endpoint_url"), str)
                else None
            ),
        )

    def manifest_key(self, snapshot: str) -> str:
        base = f"{self.prefix}/manifests" if self.prefix else "manifests"
        return f"{base}/{snapshot}.json"

    def object_key(self, snapshot: str, rel_path: str) -> str:
        base = f"{self.prefix}/{snapshot}" if self.prefix else snapshot
        return f"{base}/{rel_path}"


class S3SyncClient:
    """Wrapper around ``boto3`` that applies sync plans."""

    def __init__(
        self,
        config: S3SyncConfig,
        *,
        credentials: Mapping[str, Any] | None = None,
        session: Any | None = None,
    ) -> None:
        if session is None:
            if boto3 is None:
                raise RuntimeError("boto3 is required to run S3 sync operations")
            session_kwargs: Dict[str, Any] = {}
            if credentials:
                for field in (
                    "aws_access_key_id",
                    "aws_secret_access_key",
                    "aws_session_token",
                ):
                    if field in credentials and credentials[field]:
                        session_kwargs[field] = credentials[field]
            if config.profile:
                session_kwargs["profile_name"] = config.profile
            if config.region:
                session_kwargs["region_name"] = config.region
            session = boto3.session.Session(**session_kwargs)
        self._client = session.client("s3", endpoint_url=config.endpoint_url)
        self.config = config

    # -- Remote manifest -----------------------------------------------------------

    def fetch_remote_manifest(self, snapshot: str) -> Manifest | None:
        key = self.config.manifest_key(snapshot)
        try:
            response = self._client.get_object(Bucket=self.config.bucket, Key=key)
        except ClientError as exc:  # pragma: no cover - depends on botocore
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                return None
            raise
        data = response["Body"].read()
        payload = json.loads(data.decode("utf-8"))
        manifest_payload = (
            payload.get("manifest") if isinstance(payload, dict) else payload
        )
        if not isinstance(manifest_payload, dict):
            logger.warning(
                "Remote manifest payload malformed at s3://%s/%s",
                self.config.bucket,
                key,
            )
            return None
        manifest = Manifest.from_dict(manifest_payload)
        return manifest

    def upload_manifest(self, snapshot: str, manifest: Manifest) -> None:
        key = self.config.manifest_key(snapshot)
        payload = json.dumps({"manifest": manifest.to_dict()}, indent=2)
        self._client.put_object(
            Bucket=self.config.bucket,
            Key=key,
            Body=payload.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info(
            "Uploaded manifest to S3",
            extra={
                "bucket": self.config.bucket,
                "key": key,
                "entries": len(manifest.entries),
            },
        )

    # -- Plan execution ------------------------------------------------------------

    def apply_plan(
        self, plan: SyncPlan, manifest: Manifest, *, dry_run: bool = False
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "service": "s3",
            "snapshot": plan.snapshot,
            "uploads": [],
            "deletes": [],
            "skipped": [],
        }

        if dry_run:
            summary["uploads"] = [change.to_dict() for change in plan.uploads]
            summary["deletes"] = [change.to_dict() for change in plan.deletes]
            summary["skipped"] = [change.to_dict() for change in plan.unchanged]
            logger.info(
                "S3 dry-run computed",
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

        for change in plan.uploads:
            local_path = root / change.path
            key = self.config.object_key(plan.snapshot, change.path)
            self._client.upload_file(str(local_path), self.config.bucket, key)
            uploaded.append(change.path)

        for change in plan.deletes:
            key = self.config.object_key(plan.snapshot, change.path)
            self._client.delete_object(Bucket=self.config.bucket, Key=key)
            deleted.append(change.path)

        summary["uploads"] = uploaded
        summary["deletes"] = deleted
        summary["skipped"] = [change.path for change in plan.unchanged]

        logger.info(
            "S3 sync applied",
            extra={
                "uploads": len(uploaded),
                "deletes": len(deleted),
                "snapshot": plan.snapshot,
            },
        )

        self.upload_manifest(plan.snapshot, manifest)
        return summary


__all__ = ["S3SyncClient", "S3SyncConfig"]
