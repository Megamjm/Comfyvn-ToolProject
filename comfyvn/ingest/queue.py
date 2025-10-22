from __future__ import annotations

"""
Asset ingest queue with staging, deduplication, and registry integration.

The queue is primarily exercised through the REST API located at
``/api/ingest`` but can be reused by internal tooling or studio scripts.

Workflow summary:
  1. ``enqueue`` copies (or downloads) a submitted asset into a staging folder.
  2. The staged file is hashed and registered with :class:`CacheManager` so the
     dedup cache can apply LRU/pinning policies.
  3. Metadata is normalised via :mod:`comfyvn.ingest.mappers`.
  4. ``apply`` moves staged entries into the persistent asset registry, writing
     sidecars and thumbnails via :class:`AssetRegistry`.
"""

import json
import logging
import os
import shutil
import threading
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from comfyvn.cache.cache_manager import CacheManager
from comfyvn.config import feature_flags
from comfyvn.config.runtime_paths import cache_dir, data_dir
from comfyvn.ingest.mappers import (
    NormalisedAssetMetadata,
    build_provenance_payload,
    guess_asset_type,
    normalise_metadata,
)
from comfyvn.studio.core.asset_registry import AssetRegistry

LOGGER = logging.getLogger(__name__)

STATE_VERSION = 1
MAX_REMOTE_BYTES = 200 * 1024 * 1024  # 200 MiB guard for remote pulls
REMOTE_TIMEOUT = 45.0
DEFAULT_RATE_LIMIT = 0.33  # ~1 request every 3 seconds

_REMOTE_ALLOWLIST: Dict[str, set[str]] = {
    "civitai": {"civitai.com", "www.civitai.com"},
    "huggingface": {
        "huggingface.co",
        "www.huggingface.co",
        "huggingfaceusercontent.com",
    },
}


class IngestError(RuntimeError):
    """Base error raised for ingest queue issues."""


class RateLimitExceeded(IngestError):
    """Raised when provider-specific rate limits are exceeded."""


@dataclass
class IngestRecord:
    id: str
    provider: str
    source_kind: str
    source: str
    staged_path: Optional[str]
    digest: Optional[str]
    size: int
    status: str
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    normalised_metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    asset_type_hint: Optional[str] = None
    dest_relative: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    error: Optional[str] = None
    dedup_of: Optional[str] = None
    existing_uid: Optional[str] = None
    asset_uid: Optional[str] = None
    asset_path: Optional[str] = None
    thumb_path: Optional[str] = None
    attempts: int = 0
    pinned: bool = True
    terms_acknowledged: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at
        payload["updated_at"] = self.updated_at
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IngestRecord":
        kwargs = dict(data)
        return cls(
            id=str(kwargs.get("id")),
            provider=str(kwargs.get("provider", "generic")),
            source_kind=str(kwargs.get("source_kind", "local")),
            source=str(kwargs.get("source", "")),
            staged_path=kwargs.get("staged_path"),
            digest=kwargs.get("digest"),
            size=int(kwargs.get("size", 0)),
            status=str(kwargs.get("status", "queued")),
            raw_metadata=dict(kwargs.get("raw_metadata") or {}),
            normalised_metadata=dict(kwargs.get("normalised_metadata") or {}),
            provenance=dict(kwargs.get("provenance") or {}),
            created_at=float(kwargs.get("created_at", time.time())),
            updated_at=float(kwargs.get("updated_at", time.time())),
            asset_type_hint=kwargs.get("asset_type_hint"),
            dest_relative=kwargs.get("dest_relative"),
            notes=list(kwargs.get("notes") or []),
            error=kwargs.get("error"),
            dedup_of=kwargs.get("dedup_of"),
            existing_uid=kwargs.get("existing_uid"),
            asset_uid=kwargs.get("asset_uid"),
            asset_path=kwargs.get("asset_path"),
            thumb_path=kwargs.get("thumb_path"),
            attempts=int(kwargs.get("attempts", 0)),
            pinned=bool(kwargs.get("pinned", True)),
            terms_acknowledged=kwargs.get("terms_acknowledged"),
        )


class RateLimiter:
    """Simple token bucket used to guard provider requests."""

    def __init__(
        self, rate_per_sec: float, *, capacity: Optional[float] = None
    ) -> None:
        self.rate = max(rate_per_sec, 0.01)
        self.capacity = capacity if capacity is not None else max(1.0, self.rate * 4)
        self.tokens = self.capacity
        self.last = time.time()
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            now = time.time()
            elapsed = now - self.last
            self.last = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class AssetIngestQueue:
    """Coordinator for staged asset ingestion."""

    def __init__(
        self,
        *,
        staging_root: Optional[Path | str] = None,
        state_path: Optional[Path | str] = None,
        cache_path: Optional[Path | str] = None,
        registry: Optional[AssetRegistry] = None,
    ) -> None:
        root = Path(staging_root) if staging_root else data_dir("ingest", "staging")
        self.staging_root = root.expanduser().resolve()
        self.staging_root.mkdir(parents=True, exist_ok=True)
        if state_path:
            self.state_path = Path(state_path).expanduser().resolve()
        else:
            self.state_path = data_dir("ingest", "queue_state.json").resolve()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path:
            cache_index = Path(cache_path).expanduser().resolve()
        else:
            cache_index = cache_dir("ingest", "dedup_cache.json").resolve()
        cache_index.parent.mkdir(parents=True, exist_ok=True)
        self.cache = CacheManager(
            index_path=cache_index,
            max_entries=512,
            max_bytes=5 * 1024 * 1024 * 1024,  # 5 GiB
        )
        self.registry = registry or AssetRegistry()
        self._lock = threading.RLock()
        self._records: Dict[str, IngestRecord] = {}
        self._digest_index: Dict[str, str] = {}
        self._rate_limits: Dict[str, RateLimiter] = {}
        self._load_state()

    # ------------------------------------------------------------------ Internals
    def _get_rate_limiter(self, key: str) -> RateLimiter:
        with self._lock:
            limiter = self._rate_limits.get(key)
            if limiter is None:
                limiter = RateLimiter(DEFAULT_RATE_LIMIT)
                self._rate_limits[key] = limiter
            return limiter

    def _register_cache(self, record: IngestRecord) -> None:
        if not record.staged_path or not record.digest:
            return
        staged = Path(record.staged_path)
        if not staged.exists():
            record.staged_path = None
            record.pinned = False
            return
        try:
            self.cache.register_path(
                staged,
                pinned=record.pinned,
                digest=record.digest,
                size=record.size,
                persist=True,
            )
        except FileNotFoundError:
            record.staged_path = None
            record.pinned = False

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to load ingest queue state: %s", exc)
            return
        if not isinstance(payload, dict):
            return
        if int(payload.get("version", 0)) != STATE_VERSION:
            LOGGER.info("Ignoring ingest queue state with mismatched version.")
            return
        records = payload.get("records")
        if not isinstance(records, list):
            return
        for item in records:
            if not isinstance(item, Mapping):
                continue
            record = IngestRecord.from_dict(item)
            self._records[record.id] = record
            if record.status == "staged" and record.digest:
                self._digest_index[record.digest] = record.id
                self._register_cache(record)

    def _persist(self) -> None:
        snapshot = {
            "version": STATE_VERSION,
            "records": [record.as_dict() for record in self._records.values()],
        }
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        tmp_path.replace(self.state_path)

    def _allowed_remote(self, provider: str, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        allow = _REMOTE_ALLOWLIST.get(provider, set())
        hostname = host.lower()
        for domain in allow:
            domain = domain.lower()
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True
        return False

    def _download_remote(self, provider: str, url: str, dest: Path) -> int:
        limiter = self._get_rate_limiter(provider)
        if not limiter.allow():
            raise RateLimitExceeded(f"{provider} rate limit exceeded; retry shortly.")
        if not self._allowed_remote(provider, url):
            raise IngestError(
                f"Remote pulls for {provider} must target approved hosts."
            )
        headers = {
            "User-Agent": "ComfyVN-AssetIngest/1.0 (+https://comfyvn.dev)",
            "Accept": "*/*",
        }
        request = urllib.request.Request(url, headers=headers)
        total = 0
        try:
            with urllib.request.urlopen(request, timeout=REMOTE_TIMEOUT) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_REMOTE_BYTES:
                    raise IngestError("Remote asset exceeds size limit.")
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 128)
                        if not chunk:
                            break
                        handle.write(chunk)
                        total += len(chunk)
                        if total > MAX_REMOTE_BYTES:
                            raise IngestError("Remote asset exceeded size limit.")
        except RateLimitExceeded:
            raise
        except Exception as exc:
            raise IngestError(f"Failed to download remote asset: {exc}") from exc
        return total

    def _resolve_staging_path(self, suffix: str) -> Path:
        return self.staging_root / f"{uuid.uuid4().hex}{suffix}"

    def _compute_digest(self, path: Path) -> str:
        return self.cache.compute_digest(path)

    def _existing_asset_for_digest(self, digest: str) -> Optional[Dict[str, Any]]:
        assets = self.registry.list_assets(hash_value=digest)
        if not assets:
            return None
        # Latest matching asset preferred
        asset = assets[0]
        return {
            "uid": asset.get("uid"),
            "path": asset.get("path_full") or asset.get("path"),
            "hash": asset.get("hash"),
            "bytes": asset.get("bytes"),
            "type": asset.get("type"),
        }

    def _cleanup_staging(self, record: IngestRecord) -> None:
        staged = record.staged_path
        record.pinned = False
        if staged:
            try:
                self.cache.release_path(staged, persist=True)
            except Exception:
                pass
            try:
                Path(staged).unlink(missing_ok=True)
            except Exception:
                LOGGER.debug("Failed to remove staging file %s", staged, exc_info=True)
        record.staged_path = None

    # ------------------------------------------------------------------ Public API
    def enqueue(
        self,
        *,
        provider: str,
        raw_metadata: Optional[Dict[str, Any]] = None,
        source_path: Optional[str | os.PathLike[str]] = None,
        remote_url: Optional[str] = None,
        dest_relative: Optional[str] = None,
        asset_type_hint: Optional[str] = None,
        pin: bool = True,
        terms_acknowledged: Optional[bool] = None,
    ) -> IngestRecord:
        """
        Stage an asset for ingestion.

        ``provider`` identifies the metadata mapper to use.  Callers must supply
        either ``source_path`` (local file) or ``remote_url`` for supported remote
        pulls (currently Civitai / HuggingFace when terms are acknowledged).
        """

        provider_key = (provider or "generic").strip().lower()
        if not source_path and not remote_url:
            raise IngestError("source_path or remote_url required.")
        if remote_url:
            if provider_key in {"furaffinity", "fa"}:
                raise IngestError("FurAffinity submissions must be uploaded as files.")
            if provider_key not in _REMOTE_ALLOWLIST:
                raise IngestError(f"Remote pulls are not supported for {provider_key}.")
            if not terms_acknowledged and feature_flags.is_enabled(
                "require_remote_terms_ack", default=True
            ):
                raise IngestError(
                    "Provider terms must be acknowledged for remote pulls."
                )
        metadata_payload = raw_metadata or {}
        source_kind = "local" if source_path else "remote"
        if source_path:
            resolved = Path(source_path).expanduser().resolve()
            if not resolved.exists():
                raise IngestError(f"Source path does not exist: {resolved}")
            suffix = resolved.suffix
            staged = self._resolve_staging_path(suffix)
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, staged)
            size_bytes = staged.stat().st_size
            source_repr = str(resolved)
        else:
            parsed = urllib.parse.urlparse(str(remote_url))
            suffix = Path(parsed.path).suffix or ".bin"
            staged = self._resolve_staging_path(suffix)
            size_bytes = self._download_remote(provider_key, str(remote_url), staged)
            source_repr = str(remote_url)

        digest = self._compute_digest(staged)
        normalised = normalise_metadata(
            provider_key,
            metadata_payload,
            fallback_asset_type=asset_type_hint,
            source_url=remote_url,
        )
        provenanced = build_provenance_payload(
            provider=provider_key,
            source_url=normalised.source_url or remote_url,
            digest=digest,
            extra=normalised.extra,
            terms_acknowledged=terms_acknowledged,
        )
        record = IngestRecord(
            id=uuid.uuid4().hex[:12],
            provider=provider_key,
            source_kind=source_kind,
            source=source_repr,
            staged_path=str(staged),
            digest=digest,
            size=size_bytes,
            status="staged",
            raw_metadata=dict(metadata_payload),
            normalised_metadata=normalised.as_dict(),
            provenance=provenanced,
            asset_type_hint=asset_type_hint or normalised.asset_type,
            dest_relative=str(dest_relative) if dest_relative else None,
            terms_acknowledged=terms_acknowledged,
            pinned=pin,
        )

        with self._lock:
            # Dedup against existing queue entries
            existing_queue = self._digest_index.get(digest)
            if existing_queue:
                record.status = "duplicate"
                record.dedup_of = existing_queue
                record.notes.append("duplicate.staged")
                self._cleanup_staging(record)
            else:
                existing_asset = self._existing_asset_for_digest(digest)
                if existing_asset:
                    record.status = "duplicate"
                    record.existing_uid = existing_asset.get("uid")
                    record.asset_path = existing_asset.get("path")
                    record.notes.append("duplicate.registry")
                    self._cleanup_staging(record)
                else:
                    try:
                        self.cache.register_path(
                            record.staged_path,
                            pinned=pin,
                            digest=digest,
                            size=size_bytes,
                            persist=True,
                        )
                    except FileNotFoundError:
                        record.status = "failed"
                        record.error = "Staging file missing during dedup register."
                        record.staged_path = None
                        record.pinned = False
                    else:
                        self._digest_index[digest] = record.id
            record.updated_at = time.time()
            self._records[record.id] = record
            self._persist()
        LOGGER.info(
            "Asset queued via %s (status=%s, digest=%s)",
            provider_key,
            record.status,
            digest[:12] if digest else "none",
        )
        return record

    def list_jobs(self, *, limit: Optional[int] = None) -> list[Dict[str, Any]]:
        with self._lock:
            items = list(self._records.values())
        if limit is not None and limit >= 0:
            items = items[-limit:]
        return [item.as_dict() for item in items]

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            record = self._records.get(job_id)
            return record.as_dict() if record else None

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            counts: Dict[str, int] = {}
            for record in self._records.values():
                counts[record.status] = counts.get(record.status, 0) + 1
        return {"counts": counts, "total": sum(counts.values())}

    def apply(
        self,
        *,
        job_ids: Optional[Sequence[str]] = None,
        asset_type_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Finalise staged assets into the registry.

        When ``job_ids`` is omitted the queue processes all staged entries.
        Returns a summary dictionary describing applied, skipped, and failed jobs.
        """

        with self._lock:
            if job_ids:
                targets = [
                    self._records.get(job_id)
                    for job_id in job_ids
                    if self._records.get(job_id)
                ]
            else:
                targets = [
                    record
                    for record in self._records.values()
                    if record.status == "staged"
                ]
        applied: list[str] = []
        skipped: list[str] = []
        failed: Dict[str, str] = {}

        for record in targets:
            if record is None:
                continue
            if record.status != "staged" or not record.staged_path:
                skipped.append(record.id)
                continue
            staged_path = Path(record.staged_path)
            if not staged_path.exists():
                record.status = "failed"
                record.error = "Staging file missing."
                record.updated_at = time.time()
                failed[record.id] = record.error
                continue
            metadata = dict(record.normalised_metadata)
            asset_type = asset_type_override or record.asset_type_hint
            if not asset_type:
                asset_type = guess_asset_type(staged_path, metadata)
            metadata.pop("asset_type", None)
            license_tag = metadata.get("license")
            try:
                result = self.registry.register_file(
                    staged_path,
                    asset_type,
                    dest_relative=record.dest_relative,
                    metadata=metadata,
                    copy=True,
                    provenance=record.provenance,
                    license_tag=license_tag,
                )
            except Exception as exc:
                record.status = "failed"
                record.error = str(exc)
                record.updated_at = time.time()
                failed[record.id] = record.error
                LOGGER.warning("Failed to apply ingest job %s: %s", record.id, exc)
                continue
            record.asset_uid = result.get("uid")
            record.asset_path = result.get("path")
            record.thumb_path = result.get("thumb")
            record.status = "applied"
            record.error = None
            record.updated_at = time.time()
            applied.append(record.id)
            self._cleanup_staging(record)
            with self._lock:
                if record.digest:
                    self._digest_index.pop(record.digest, None)

        with self._lock:
            self._persist()

        return {"applied": applied, "skipped": skipped, "failed": failed}

    def release(self, job_id: str) -> bool:
        """
        Release a staged entry without applying it.

        This removes the staging artefact and keeps the history record with a
        ``released`` status.
        """

        with self._lock:
            record = self._records.get(job_id)
            if not record:
                return False
            if record.status not in {"staged", "duplicate", "failed"}:
                return False
            self._cleanup_staging(record)
            record.status = "released"
            record.updated_at = time.time()
            if record.digest:
                self._digest_index.pop(record.digest, None)
            self._persist()
        return True


_QUEUE: Optional[AssetIngestQueue] = None
_QUEUE_LOCK = threading.Lock()


def get_ingest_queue() -> AssetIngestQueue:
    """Return the process-wide ingest queue singleton."""

    global _QUEUE
    if _QUEUE is not None:
        return _QUEUE
    with _QUEUE_LOCK:
        if _QUEUE is None:
            _QUEUE = AssetIngestQueue()
    return _QUEUE
