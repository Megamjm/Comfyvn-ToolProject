from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from comfyvn.core.settings_manager import SettingsManager
from comfyvn.core.advisory import AdvisoryIssue, log_issue

LOGGER = logging.getLogger("comfyvn.policy.filter")

NSFW_KEYWORDS = {"nsfw", "explicit", "adult", "18+", "mature"}


@dataclass
class FilterResult:
    item_id: str
    allowed: bool
    reason: Optional[str] = None
    severity: str = "info"


class ContentFilter:
    def __init__(self, settings: Optional[SettingsManager] = None) -> None:
        self.settings = settings or SettingsManager()

    def mode(self) -> str:
        cfg = self.settings.load()
        return cfg.get("filters", {}).get("content_mode", "sfw")

    def set_mode(self, mode: str) -> str:
        mode = mode.lower()
        if mode not in {"sfw", "warn", "unrestricted"}:
            raise ValueError("mode must be sfw|warn|unrestricted")
        cfg = self.settings.load()
        cfg.setdefault("filters", {})["content_mode"] = mode
        self.settings.save(cfg)
        LOGGER.info("Content filter mode set to %s", mode)
        return mode

    def classify(self, item: Dict) -> Tuple[bool, Optional[str], str]:
        meta = item.get("meta") or {}
        tags: Iterable[str] = meta.get("tags") or item.get("tags") or []
        rating = (meta.get("rating") or "").lower()
        if meta.get("nsfw") or rating in {"mature", "explicit"}:
            return False, "metadata flagged as NSFW", "warn"
        for tag in tags:
            if isinstance(tag, str) and tag.lower() in NSFW_KEYWORDS:
                return False, f"tag '{tag}' flagged as NSFW", "warn"
        return True, None, "info"

    def filter_items(self, items: List[Dict], *, mode: Optional[str] = None) -> Dict[str, List[Dict]]:
        mode = (mode or self.mode()).lower()
        allowed_items: List[Dict] = []
        flagged_items: List[Dict] = []
        warnings: List[FilterResult] = []

        for item in items:
            item_id = str(item.get("id") or item.get("uid") or item.get("path") or "unknown")
            allowed, reason, severity = self.classify(item)
            if allowed or mode == "unrestricted":
                allowed_items.append(item)
                if not allowed:
                    warnings.append(FilterResult(item_id=item_id, allowed=True, reason=reason, severity=severity))
            elif mode == "warn":
                allowed_items.append(item)
                warnings.append(FilterResult(item_id=item_id, allowed=True, reason=reason, severity=severity))
            else:
                flagged_items.append(item)
                warnings.append(FilterResult(item_id=item_id, allowed=False, reason=reason, severity=severity))

        for warning in warnings:
            if warning.reason:
                log_issue(
                    AdvisoryIssue(
                        target_id=warning.item_id,
                        kind="nsfw",
                        message=warning.reason,
                        severity="warn" if not warning.allowed else "info",
                        detail={"filter_mode": mode},
                        resolved=warning.allowed,
                    )
                )

        LOGGER.debug(
            "Content filter mode=%s allowed=%s flagged=%s",
            mode,
            len(allowed_items),
            len(flagged_items),
        )
        return {
            "mode": mode,
            "allowed": allowed_items,
            "flagged": flagged_items,
            "warnings": [warning.__dict__ for warning in warnings],
        }


content_filter = ContentFilter()
