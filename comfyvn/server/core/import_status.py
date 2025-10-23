from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from comfyvn.config.runtime_paths import data_dir


def _isoformat(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ImportStatus:
    job_id: str
    kind: str
    state: str = "queued"
    percent: float = 0.0
    message: str = ""
    task_id: Optional[str] = None
    logs_path: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 0
    created_at: str = field(default_factory=lambda: _isoformat(time.time()))
    updated_at: str = field(default_factory=lambda: _isoformat(time.time()))
    links: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    history: list[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "state": self.state,
            "percent": float(self.percent),
            "message": self.message,
            "task_id": self.task_id,
            "logs_path": self.logs_path,
            "attempts": int(self.attempts),
            "max_attempts": int(self.max_attempts),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "links": dict(self.links),
            "meta": dict(self.meta),
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ImportStatus":
        base = cls(
            job_id=str(payload.get("job_id", "")),
            kind=str(payload.get("kind", "")),
            state=str(payload.get("state", "queued")),
            percent=float(payload.get("percent", 0.0) or 0.0),
            message=str(payload.get("message", "")),
            task_id=payload.get("task_id"),
            logs_path=payload.get("logs_path"),
            attempts=int(payload.get("attempts", 0) or 0),
            max_attempts=int(payload.get("max_attempts", 0) or 0),
            created_at=str(payload.get("created_at") or _isoformat(time.time())),
            updated_at=str(payload.get("updated_at") or _isoformat(time.time())),
        )
        links = payload.get("links")
        if isinstance(links, dict):
            base.links = dict(links)
        meta = payload.get("meta")
        if isinstance(meta, dict):
            base.meta = dict(meta)
        history = payload.get("history")
        if isinstance(history, list):
            events: list[Dict[str, Any]] = []
            for event in history:
                if isinstance(event, dict):
                    events.append(dict(event))
            base.history = events
        return base


class ImportStatusStore:
    """
    Persist import job status snapshots under ``data/imports/<kind>/status``.

    The store maintains a lightweight index so lookups by job id remain O(1).
    """

    def __init__(self, root: Optional[Path | str] = None) -> None:
        base = Path(root).expanduser().resolve() if root else data_dir("imports")
        self.base = _ensure_dir(base)
        self._lock = threading.RLock()
        self.index_path = self.base / "status_index.json"
        self._index: Dict[str, Dict[str, str]] = self._load_index()

    # ------------------------------------------------------------------ helpers
    def _status_dir(self, kind: str) -> Path:
        safe = str(kind or "generic").strip() or "generic"
        return _ensure_dir(self.base / safe / "status")

    def _status_path(self, kind: str, job_id: str) -> Path:
        safe_job = str(job_id).strip()
        return self._status_dir(kind) / f"{safe_job}.json"

    def _load_index(self) -> Dict[str, Dict[str, str]]:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out: Dict[str, Dict[str, str]] = {}
                for key, value in data.items():
                    if isinstance(value, dict) and "kind" in value and "path" in value:
                        out[str(key)] = {
                            "kind": str(value["kind"]),
                            "path": str(value["path"]),
                        }
                return out
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            self.index_path.rename(self.index_path.with_suffix(".bak"))
        return {}

    def _persist_index(self) -> None:
        tmp_path = self.index_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp_path.replace(self.index_path)

    def _write_payload(self, path: Path, payload: Dict[str, Any]) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)

    def _load_status(self, path: Path) -> ImportStatus:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise KeyError(f"status file missing: {path}") from None
        except json.JSONDecodeError as exc:
            raise KeyError(f"status file corrupted: {path}") from exc
        return ImportStatus.from_dict(data)

    def _resolve_job(self, job_id: str) -> Optional[Dict[str, str]]:
        cached = self._index.get(job_id)
        if cached:
            path = Path(cached["path"])
            if path.exists():
                return cached
        for status_file in self.base.glob("*/status/*.json"):
            if status_file.stem == job_id:
                rel_kind = status_file.parent.parent.name
                record = {"kind": rel_kind, "path": status_file.as_posix()}
                self._index[job_id] = record
                self._persist_index()
                return record
        return None

    def _append_event(
        self,
        status: ImportStatus,
        *,
        stage: Optional[str] = None,
        detail: Optional[str] = None,
        progress: Optional[float] = None,
        state: Optional[str] = None,
    ) -> None:
        event = {
            "timestamp": _isoformat(time.time()),
            "stage": stage,
            "detail": detail,
            "progress": float(progress) if progress is not None else status.percent,
            "state": state or status.state,
        }
        status.history.append(event)

    # ------------------------------------------------------------------ public
    def register(
        self,
        kind: str,
        job_id: str,
        *,
        state: str = "queued",
        percent: float = 0.0,
        message: str = "",
        task_id: Optional[str] = None,
        logs_path: Optional[str] = None,
        attempts: int = 0,
        max_attempts: int = 0,
        links: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> ImportStatus:
        with self._lock:
            status = ImportStatus(
                job_id=str(job_id),
                kind=str(kind or "generic"),
                state=str(state or "queued"),
                percent=float(percent or 0.0),
                message=str(message or ""),
                task_id=task_id,
                logs_path=logs_path,
                attempts=int(attempts or 0),
                max_attempts=int(max_attempts or 0),
            )
            if links:
                status.links.update(links)
            if meta:
                status.meta.update(meta)
            path = self._status_path(status.kind, status.job_id)
            self._write_payload(path, status.to_dict())
            self._index[status.job_id] = {
                "kind": status.kind,
                "path": path.as_posix(),
            }
            self._persist_index()
            return status

    def update(
        self,
        job_id: str,
        *,
        state: Optional[str] = None,
        percent: Optional[float] = None,
        message: Optional[str] = None,
        task_id: Optional[str] = None,
        logs_path: Optional[str] = None,
        links: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        attempts: Optional[int] = None,
        max_attempts: Optional[int] = None,
        stage: Optional[str] = None,
        detail: Optional[str] = None,
        progress: Optional[float] = None,
    ) -> ImportStatus:
        with self._lock:
            record = self._resolve_job(str(job_id))
            if not record:
                raise KeyError(f"unknown import job: {job_id}")
            path = Path(record["path"])
            status = self._load_status(path)
            if state:
                status.state = str(state)
            if percent is not None:
                status.percent = float(percent)
            if message is not None:
                status.message = str(message)
            if task_id is not None:
                status.task_id = task_id
            if logs_path is not None:
                status.logs_path = logs_path
            if attempts is not None:
                status.attempts = int(attempts)
            if max_attempts is not None:
                status.max_attempts = int(max_attempts)
            if links:
                status.links.update(links)
            if meta:
                status.meta.update(meta)
            if stage or detail or progress is not None:
                self._append_event(
                    status,
                    stage=stage,
                    detail=detail,
                    progress=progress,
                    state=state,
                )
            status.updated_at = _isoformat(time.time())
            self._write_payload(path, status.to_dict())
            self._index[status.job_id] = {
                "kind": status.kind,
                "path": path.as_posix(),
            }
            self._persist_index()
            return status

    def get(self, job_id: str) -> ImportStatus:
        with self._lock:
            record = self._resolve_job(str(job_id))
            if not record:
                raise KeyError(f"unknown import job: {job_id}")
            path = Path(record["path"])
            status = self._load_status(path)
            # ensure index persists absolute path for next lookup
            self._index[status.job_id] = {
                "kind": status.kind,
                "path": path.as_posix(),
            }
            self._persist_index()
            return status

    def list(self, *, kinds: Optional[Iterable[str]] = None) -> list[ImportStatus]:
        allow = {str(k).strip() for k in kinds} if kinds else None
        statuses: list[ImportStatus] = []
        with self._lock:
            candidates = list(self.base.glob("*/status/*.json"))
        for path in candidates:
            kind = path.parent.parent.name
            if allow and kind not in allow:
                continue
            try:
                statuses.append(self._load_status(path))
            except KeyError:
                continue
        statuses.sort(key=lambda item: item.updated_at, reverse=True)
        return statuses


import_status_store = ImportStatusStore()
