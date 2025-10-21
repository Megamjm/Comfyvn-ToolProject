from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from comfyvn.core.db_manager import DEFAULT_DB_PATH, DBManager

LOGGER = logging.getLogger("comfyvn.advisory")


@dataclass
class AdvisoryIssue:
    """Represents a single advisory finding."""

    target_id: str
    kind: str  # "copyright" | "nsfw" | "policy" | "quality"
    message: str
    severity: str  # "info" | "warn" | "error"
    detail: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    notes: List[str] = field(default_factory=list)
    issue_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "target_id": self.target_id,
            "kind": self.kind,
            "message": self.message,
            "severity": self.severity,
            "detail": self.detail,
            "resolved": self.resolved,
            "notes": list(self.notes),
            "timestamp": self.timestamp,
        }


class FindingsStore:
    """SQLite-backed persistence layer for advisory findings."""

    def __init__(self, db_path: str | None = None, project_id: str = "default") -> None:
        self._db_manager = DBManager(db_path or DEFAULT_DB_PATH)
        self.db_path = self._db_manager.db_path
        self.project_id = project_id
        self._db_manager.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["resolved"] = bool(payload.get("resolved"))
        payload["detail"] = json.loads(payload.get("detail") or "{}")
        notes_raw = payload.get("notes")
        payload["notes"] = json.loads(notes_raw) if notes_raw else []
        if payload.get("timestamp") is not None:
            try:
                payload["timestamp"] = float(payload["timestamp"])
            except (TypeError, ValueError):  # pragma: no cover - defensive
                payload["timestamp"] = None
        return payload

    def insert(self, issue: AdvisoryIssue) -> Dict[str, Any]:
        entry = issue.to_dict()
        detail_json = json.dumps(entry.get("detail") or {}, ensure_ascii=False)
        notes_json = json.dumps(entry.get("notes") or [], ensure_ascii=False)
        timestamp = float(entry.get("timestamp") or time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO findings (project_id, issue_id, target_id, kind, message, severity, detail, resolved, notes, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(issue_id) DO UPDATE SET
                    target_id=excluded.target_id,
                    kind=excluded.kind,
                    message=excluded.message,
                    severity=excluded.severity,
                    detail=excluded.detail,
                    resolved=excluded.resolved,
                    timestamp=excluded.timestamp
                """,
                (
                    self.project_id,
                    entry["issue_id"],
                    entry["target_id"],
                    entry["kind"],
                    entry["message"],
                    entry["severity"],
                    detail_json,
                    1 if entry.get("resolved") else 0,
                    notes_json,
                    timestamp,
                ),
            )
            row = conn.execute(
                """
                SELECT issue_id, target_id, kind, message, severity, detail, resolved, notes, timestamp, created_at
                FROM findings
                WHERE project_id = ? AND issue_id = ?
                """,
                (self.project_id, entry["issue_id"]),
            ).fetchone()
        return self._row_to_dict(row)

    def list(self, *, resolved: Optional[bool] = None) -> List[Dict[str, Any]]:
        clauses = ["project_id = ?"]
        params: List[Any] = [self.project_id]
        if resolved is not None:
            clauses.append("resolved = ?")
            params.append(1 if resolved else 0)
        where_sql = " AND ".join(clauses)
        query = f"""
            SELECT issue_id, target_id, kind, message, severity, detail, resolved, notes, timestamp, created_at
            FROM findings
            WHERE {where_sql}
            ORDER BY timestamp DESC, created_at DESC
        """
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def resolve(self, issue_id: str, notes: Optional[str] = None) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT notes FROM findings WHERE project_id = ? AND issue_id = ?
                """,
                (self.project_id, issue_id),
            ).fetchone()
            if not row:
                return False
            note_list = json.loads(row["notes"] or "[]")
            if notes:
                note_list.append(notes)
            conn.execute(
                """
                UPDATE findings
                SET resolved = 1,
                    notes = ?,
                    timestamp = COALESCE(timestamp, ?)  -- preserve initial timestamp if present
                WHERE project_id = ? AND issue_id = ?
                """,
                (
                    json.dumps(note_list, ensure_ascii=False),
                    float(time.time()),
                    self.project_id,
                    issue_id,
                ),
            )
        return True


class AdvisoryScanner:
    """Lightweight synchronous scanner (stub). Real rules can be hooked later."""

    def __init__(self) -> None:
        self.rules = {
            "nsfw_keywords": ["nsfw", "explicit", "18+"],
            "copyright_flags": ["©", "copyright", "all rights reserved"],
            "license_required": ["all rights reserved", "no redistribution"],
        }

    def scan_text(self, target_id: str, text: str) -> List[AdvisoryIssue]:
        issues: List[AdvisoryIssue] = []
        low = text.lower()
        if any(k in low for k in self.rules["nsfw_keywords"]):
            issues.append(
                AdvisoryIssue(
                    target_id,
                    "nsfw",
                    "Possible NSFW content detected",
                    "warn",
                    detail={"match": "keyword"},
                )
            )
        if any(k.lower() in low for k in self.rules["copyright_flags"]):
            issues.append(
                AdvisoryIssue(
                    target_id,
                    "copyright",
                    "Potential copyrighted material reference",
                    "warn",
                    detail={"match": "copyright"},
                )
            )
        return issues

    def scan_license(self, target_id: str, text: str) -> List[AdvisoryIssue]:
        issues: List[AdvisoryIssue] = []
        low = text.lower()
        if any(k in low for k in self.rules["license_required"]):
            issues.append(
                AdvisoryIssue(
                    target_id,
                    "policy",
                    "License terms require manual review",
                    "warn",
                    detail={"match": "license"},
                )
            )
        return issues

    def scan(
        self, target_id: str, text: str, *, license_scan: bool = False
    ) -> List[AdvisoryIssue]:
        issues = self.scan_text(target_id, text)
        if license_scan:
            issues.extend(self.scan_license(target_id, text))
        return issues


scanner = AdvisoryScanner()
advisory_logs: Optional[List[Dict[str, Any]]] = None
findings_store = FindingsStore()


def _use_in_memory() -> bool:
    return isinstance(advisory_logs, list)


def log_issue(issue: AdvisoryIssue) -> Dict[str, Any]:
    if _use_in_memory():
        entry = issue.to_dict()
        advisory_logs.append(entry)  # type: ignore[arg-type]
    else:
        entry = findings_store.insert(issue)
    LOGGER.warning(
        "Advisory issue target=%s kind=%s severity=%s id=%s",
        issue.target_id,
        issue.kind,
        issue.severity,
        issue.issue_id,
    )
    return entry


def list_logs(*, resolved: Optional[bool] = None) -> List[Dict[str, Any]]:
    if _use_in_memory():
        logs = advisory_logs or []
        if resolved is None:
            return list(logs)
        return [entry for entry in logs if entry["resolved"] is resolved]
    return findings_store.list(resolved=resolved)


def scan_text(
    target_id: str, text: str, *, license_scan: bool = False
) -> List[Dict[str, Any]]:
    issues = scanner.scan(target_id, text, license_scan=license_scan)
    logged: List[Dict[str, Any]] = []
    for issue in issues:
        logged.append(log_issue(issue))
    LOGGER.info(
        "Advisory scan target=%s issues=%s license_scan=%s",
        target_id,
        len(issues),
        license_scan,
    )
    return logged


def resolve_issue(issue_id: str, notes: Optional[str] = None) -> bool:
    if _use_in_memory():
        logs = advisory_logs or []
        for entry in logs:
            if entry["issue_id"] == issue_id:
                entry["resolved"] = True
                entry.setdefault("notes", [])
                if notes:
                    entry["notes"].append(notes)
                LOGGER.info("Advisory issue resolved id=%s", issue_id)
                return True
        LOGGER.debug("Advisory issue not found id=%s", issue_id)
        return False
    updated = findings_store.resolve(issue_id, notes)
    if updated:
        LOGGER.info("Advisory issue resolved id=%s", issue_id)
    else:
        LOGGER.debug("Advisory issue not found id=%s", issue_id)
    return updated
