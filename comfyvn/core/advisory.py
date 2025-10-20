from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

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
            "timestamp": self.timestamp,
        }


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

    def scan(self, target_id: str, text: str, *, license_scan: bool = False) -> List[AdvisoryIssue]:
        issues = self.scan_text(target_id, text)
        if license_scan:
            issues.extend(self.scan_license(target_id, text))
        return issues


scanner = AdvisoryScanner()
advisory_logs: List[Dict[str, Any]] = []


def log_issue(issue: AdvisoryIssue) -> None:
    entry = issue.to_dict()
    advisory_logs.append(entry)
    LOGGER.warning(
        "Advisory issue target=%s kind=%s severity=%s id=%s",
        issue.target_id,
        issue.kind,
        issue.severity,
        issue.issue_id,
    )


def list_logs(*, resolved: Optional[bool] = None) -> List[Dict[str, Any]]:
    if resolved is None:
        return list(advisory_logs)
    return [entry for entry in advisory_logs if entry["resolved"] is resolved]


def scan_text(target_id: str, text: str, *, license_scan: bool = False) -> List[Dict[str, Any]]:
    issues = scanner.scan(target_id, text, license_scan=license_scan)
    for issue in issues:
        log_issue(issue)
    LOGGER.info(
        "Advisory scan target=%s issues=%s license_scan=%s",
        target_id,
        len(issues),
        license_scan,
    )
    return [issue.to_dict() for issue in issues]


def resolve_issue(issue_id: str, notes: Optional[str] = None) -> bool:
    for entry in advisory_logs:
        if entry["issue_id"] == issue_id:
            entry["resolved"] = True
            entry.setdefault("notes", [])
            if notes:
                entry["notes"].append(notes)
            LOGGER.info("Advisory issue resolved id=%s", issue_id)
            return True
    LOGGER.debug("Advisory issue not found id=%s", issue_id)
    return False
