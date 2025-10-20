from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/core/advisory.py
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class AdvisoryIssue:
    target_id: str
    kind: str          # "copyright", "nsfw", "policy", "quality"
    message: str
    severity: str      # "info"|"warn"|"error"
    resolved: bool = False


class AdvisoryScanner:
    """Lightweight synchronous scanner (stub). Real rules can be hooked later."""

    def __init__(self):
        self.rules = {
            "nsfw_keywords": ["nsfw", "explicit", "18+"],
            "copyright_flags": ["©", "copyright", "all rights reserved"],
        }

    def scan_text(self, target_id: str, text: str) -> List[AdvisoryIssue]:
        issues: List[AdvisoryIssue] = []
        low = text.lower()
        if any(k in low for k in self.rules["nsfw_keywords"]):
            issues.append(
                AdvisoryIssue(target_id, "nsfw", "Possible NSFW content", "warn")
            )
        if any(k.lower() in low for k in self.rules["copyright_flags"]):
            issues.append(
                AdvisoryIssue(
                    target_id,
                    "copyright",
                    "Potential copyrighted material reference",
                    "warn",
                )
            )
        return issues


scanner = AdvisoryScanner()
advisory_logs: list[Dict[str, Any]] = []


def log_issue(issue: AdvisoryIssue):
    advisory_logs.append(issue.__dict__)


def list_logs():
    return advisory_logs