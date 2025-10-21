"""
Hash-based deduplication cache manager.

This cache keeps a persistent JSON index of unique file blobs keyed by their
content hash. Multiple asset paths can reference the same blob entry while
tracking per-path refcounts and pin state. A simple LRU eviction policy drops
the oldest, non-pinned entries when optional limits are exceeded.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional

from comfyvn.config.runtime_paths import cache_dir

CACHE_VERSION = 1


@dataclass
class CachePathRecord:
    """Metadata for an individual path that points at a cache entry."""

    pinned: bool = False
    refcount: int = 1
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, float | int | bool]:
        return {
            "pinned": self.pinned,
            "refcount": self.refcount,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "CachePathRecord":
        return cls(
            pinned=bool(payload.get("pinned", False)),
            refcount=int(payload.get("refcount", 1)),
            last_seen=float(payload.get("last_seen", time.time())),
        )


@dataclass
class CacheEntry:
    """Represents a unique blob in the cache."""

    digest: str
    size: int
    created_at: float
    last_access: float
    paths: Dict[str, CachePathRecord] = field(default_factory=dict)

    def bump_path(
        self,
        path: str,
        *,
        pinned: bool = False,
        increment: int = 1,
        seen_at: Optional[float] = None,
    ) -> None:
        record = self.paths.get(path)
        timestamp = seen_at or time.time()
        if record:
            if increment:
                record.refcount = max(1, record.refcount + increment)
            if pinned:
                record.pinned = True
            record.last_seen = timestamp
        else:
            if increment <= 0:
                raise KeyError(
                    f"Cannot attach new path {path!r} with non-positive refcount"
                )
            self.paths[path] = CachePathRecord(
                pinned=pinned,
                refcount=max(1, increment),
                last_seen=timestamp,
            )

    def release_path(self, path: str, decrement: int = 1) -> bool:
        record = self.paths.get(path)
        if not record:
            return False
        record.refcount = max(0, record.refcount - decrement)
        record.last_seen = time.time()
        if record.refcount == 0:
            self.paths.pop(path, None)
            return True
        return False

    @property
    def is_pinned(self) -> bool:
        return any(record.pinned for record in self.paths.values())

    @property
    def total_refcount(self) -> int:
        return sum(record.refcount for record in self.paths.values())

    def to_dict(self) -> Dict[str, object]:
        return {
            "digest": self.digest,
            "size": self.size,
            "created_at": self.created_at,
            "last_access": self.last_access,
            "paths": {path: record.to_dict() for path, record in self.paths.items()},
        }

    @classmethod
    def from_dict(cls, digest: str, payload: Dict[str, object]) -> "CacheEntry":
        entry = cls(
            digest=digest,
            size=int(payload.get("size", 0)),
            created_at=float(payload.get("created_at", time.time())),
            last_access=float(payload.get("last_access", time.time())),
        )
        paths_payload = payload.get("paths", {}) or {}
        if isinstance(paths_payload, dict):
            for path, record in paths_payload.items():
                if not isinstance(path, str):
                    continue
                if isinstance(record, dict):
                    entry.paths[path] = CachePathRecord.from_dict(record)
        return entry


class CacheManager:
    """
    Persistent JSON-backed deduplication cache.

    A cache entry is keyed by its content digest. Multiple asset paths can point
    to a single entry while maintaining individual refcounts and pin state. The
    manager optionally enforces global limits on the number of cached blobs or
    their aggregate size by evicting the least-recently-used, non-pinned
    entries.
    """

    DEFAULT_INDEX_NAME = "dedup_cache.json"

    def __init__(
        self,
        *,
        index_path: Optional[Path] = None,
        max_entries: Optional[int] = None,
        max_bytes: Optional[int] = None,
        hash_name: str = "sha256",
        chunk_size: int = 1 << 20,
    ) -> None:
        self.index_path = (
            Path(index_path)
            if index_path
            else cache_dir("dedup", self.DEFAULT_INDEX_NAME)
        )
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.hash_name = hash_name
        self.chunk_size = chunk_size

        self._lock = threading.RLock()
        self._entries: Dict[str, CacheEntry] = {}
        self._path_index: Dict[str, str] = {}

        self._load()

    # -----------------
    # Serialisation I/O
    # -----------------
    def _load(self) -> None:
        if not self.index_path.exists():
            self._persist()
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            # Corrupted cache – start fresh.
            payload = {}
        entries_payload = (
            payload.get("entries", {}) if isinstance(payload, dict) else {}
        )
        if isinstance(entries_payload, dict):
            for digest, entry_payload in entries_payload.items():
                if not isinstance(digest, str) or not isinstance(entry_payload, dict):
                    continue
                entry = CacheEntry.from_dict(digest, entry_payload)
                self._entries[digest] = entry
                for path in entry.paths:
                    self._path_index[path] = digest

    def _persist(self) -> None:
        serialised = {
            "version": CACHE_VERSION,
            "entries": {
                digest: entry.to_dict() for digest, entry in self._entries.items()
            },
        }
        self.index_path.write_text(
            json.dumps(serialised, indent=2, sort_keys=True), encoding="utf-8"
        )

    # ---------------
    # Hashing helpers
    # ---------------
    def _hasher(self) -> "hashlib._Hash":
        try:
            return hashlib.new(self.hash_name)
        except ValueError:
            raise ValueError(f"Unsupported hash algorithm {self.hash_name!r}")

    def compute_digest(self, path: Path) -> str:
        hasher = self._hasher()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(self.chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    # --------------------
    # Path index utilities
    # --------------------
    @staticmethod
    def _canonical_path(path: Path | str) -> str:
        return str(Path(path).expanduser().resolve())

    def _lookup_digest(self, path: Path | str) -> Optional[str]:
        return self._path_index.get(self._canonical_path(path))

    def _ensure_entry(
        self, digest: str, *, size: int, now: Optional[float] = None
    ) -> CacheEntry:
        entry = self._entries.get(digest)
        if entry:
            entry.size = size
            entry.last_access = now or time.time()
            return entry
        timestamp = now or time.time()
        entry = CacheEntry(
            digest=digest,
            size=size,
            created_at=timestamp,
            last_access=timestamp,
        )
        self._entries[digest] = entry
        return entry

    # -------------------
    # Public API helpers
    # -------------------
    def register_path(
        self,
        path: Path | str,
        *,
        pinned: bool = False,
        refcount: int = 1,
        digest: Optional[str] = None,
        size: Optional[int] = None,
        persist: bool = True,
    ) -> CacheEntry:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        digest_val = digest or self.compute_digest(file_path)
        size_val = size if size is not None else file_path.stat().st_size
        canonical = self._canonical_path(file_path)
        now = time.time()

        with self._lock:
            entry = self._ensure_entry(digest_val, size=size_val, now=now)
            entry.bump_path(canonical, pinned=pinned, increment=refcount, seen_at=now)
            entry.last_access = now
            self._path_index[canonical] = digest_val
            self._enforce_limits()
            if persist:
                self._persist()
            return entry

    def touch(self, path: Path | str, *, persist: bool = True) -> Optional[CacheEntry]:
        canonical = self._canonical_path(path)
        with self._lock:
            digest = self._path_index.get(canonical)
            if not digest:
                return None
            entry = self._entries.get(digest)
            if not entry:
                self._path_index.pop(canonical, None)
                return None
            now = time.time()
            entry.last_access = now
            record = entry.paths.get(canonical)
            if record:
                record.last_seen = now
            if persist:
                self._persist()
            return entry

    def pin(self, path: Path | str, *, persist: bool = True) -> CacheEntry:
        canonical = self._canonical_path(path)
        with self._lock:
            digest = self._path_index.get(canonical)
            if not digest:
                raise KeyError(f"Path {canonical} not registered in cache")
            entry = self._entries[digest]
            entry.bump_path(canonical, pinned=True, increment=0, seen_at=time.time())
            if persist:
                self._persist()
            return entry

    def unpin(self, path: Path | str, *, persist: bool = True) -> CacheEntry:
        canonical = self._canonical_path(path)
        with self._lock:
            digest = self._path_index.get(canonical)
            if not digest:
                raise KeyError(f"Path {canonical} not registered in cache")
            entry = self._entries[digest]
            record = entry.paths.get(canonical)
            if record:
                record.pinned = False
                record.last_seen = time.time()
            if persist:
                self._persist()
            return entry

    def release_path(
        self,
        path: Path | str,
        *,
        decrement: int = 1,
        persist: bool = True,
    ) -> bool:
        canonical = self._canonical_path(path)
        with self._lock:
            digest = self._path_index.get(canonical)
            if not digest:
                return False
            entry = self._entries.get(digest)
            if not entry:
                self._path_index.pop(canonical, None)
                return False
            removed = entry.release_path(canonical, decrement=decrement)
            if removed:
                self._path_index.pop(canonical, None)
            if entry.total_refcount == 0:
                self._entries.pop(digest, None)
            if persist:
                self._persist()
            return True

    # -----------------
    # Eviction handling
    # -----------------
    def _enforce_limits(self) -> None:
        if self.max_entries is not None:
            self._evict_until(lambda: len(self._entries) <= self.max_entries)
        if self.max_bytes is not None:
            self._evict_until(lambda: self.total_size <= self.max_bytes)

    def _evict_until(self, predicate) -> None:
        if predicate():
            return
        for digest in self._eviction_order():
            if predicate():
                break
            self._evict_entry(digest)

    def _eviction_order(self) -> Iterator[str]:
        candidates = [
            entry
            for entry in self._entries.values()
            if not entry.is_pinned and entry.paths
        ]
        candidates.sort(key=lambda item: item.last_access)
        for entry in candidates:
            yield entry.digest

    def _evict_entry(self, digest: str) -> None:
        entry = self._entries.pop(digest, None)
        if not entry:
            return
        for path in list(entry.paths):
            self._path_index.pop(path, None)

    # ---------------
    # Introspection
    # ---------------
    @property
    def total_size(self) -> int:
        return sum(entry.size for entry in self._entries.values())

    def get_entry(self, digest: str) -> Optional[CacheEntry]:
        return self._entries.get(digest)

    def get_entry_for_path(self, path: Path | str) -> Optional[CacheEntry]:
        digest = self._lookup_digest(path)
        if not digest:
            return None
        return self._entries.get(digest)

    def iter_entries(self) -> Iterator[CacheEntry]:
        return iter(self._entries.values())

    def pinned_paths(self) -> Dict[str, bool]:
        mapping: Dict[str, bool] = {}
        for path, digest in self._path_index.items():
            entry = self._entries.get(digest)
            if not entry:
                continue
            record = entry.paths.get(path)
            if record and record.pinned:
                mapping[path] = True
        return mapping

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "entries": {
                    digest: entry.to_dict() for digest, entry in self._entries.items()
                },
                "paths": dict(self._path_index),
                "total_size": self.total_size,
            }

    # ---------------
    # Bulk rebuild API
    # ---------------
    def rebuild_from_files(
        self,
        files: Iterable[Path],
        *,
        preserve_pins: bool = True,
    ) -> Dict[str, int]:
        files = [Path(path) for path in files]
        pinned = self.pinned_paths() if preserve_pins else {}
        now = time.time()
        stats = {"processed": 0, "duplicates": 0, "skipped": 0}
        with self._lock:
            self._entries.clear()
            self._path_index.clear()
            for file_path in files:
                file_path = Path(file_path).expanduser().resolve()
                if not file_path.is_file():
                    stats["skipped"] += 1
                    continue
                canonical = self._canonical_path(file_path)
                try:
                    digest = self.compute_digest(file_path)
                    size = file_path.stat().st_size
                except OSError:
                    stats["skipped"] += 1
                    continue
                entry = self._ensure_entry(digest, size=size, now=now)
                existed = canonical in entry.paths
                if digest in self._entries and entry.total_refcount > 0 and not existed:
                    stats["duplicates"] += 1
                entry.bump_path(
                    canonical,
                    pinned=pinned.get(canonical, False),
                    increment=1,
                    seen_at=now,
                )
                self._path_index[canonical] = digest
                entry.last_access = now
                stats["processed"] += 1
            self._persist()
        return stats

    @staticmethod
    def iter_asset_files(root: Path) -> Iterator[Path]:
        for path in root.rglob("*"):
            if path.is_file():
                yield path
