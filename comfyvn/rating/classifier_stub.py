from __future__ import annotations

"""
Stub classifier for ComfyVN content rating.

The goal is to provide a conservative baseline that errs on the side of
marking items as Mature/Adult until a full classifier is integrated. Reviewers
can pin overrides that persist across sessions, and downstream callers can
request gating decisions that respect the current SFW mode.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from comfyvn.config import feature_flags
from comfyvn.config.runtime_paths import config_dir

LOGGER = logging.getLogger("comfyvn.rating")

RATING_ORDER = ("E", "T", "M", "Adult")
RISKY_RATINGS = {"M", "Adult"}

# Keyword matrix intentionally conservative; synonyms collapse to simple stems.
RATING_MATRIX: Dict[str, Dict[str, Sequence[str]]] = {
    "Adult": {
        "keywords": (
            "explicit",
            "sexual",
            "porn",
            "nudity",
            "intercourse",
            "fetish",
            "erotic",
            "18+",
            "nsfw",
        ),
        "tags": (
            "adult",
            "nsfw",
            "r18",
            "sex",
            "hentai",
            "pornography",
            "smut",
        ),
    },
    "M": {
        "keywords": (
            "violence",
            "blood",
            "gore",
            "murder",
            "injury",
            "weapon",
            "alcohol",
            "drug",
            "narcotic",
            "intense",
            "gambling",
        ),
        "tags": (
            "mature",
            "violence",
            "blood",
            "gore",
            "substance",
            "horror",
            "psychological",
        ),
    },
    "T": {
        "keywords": (
            "mild",
            "suggestive",
            "fantasy",
            "comic",
            "prank",
            "mystery",
            "romance",
        ),
        "tags": (
            "teen",
            "pg13",
            "suggestive",
            "fantasy",
            "adventure",
        ),
    },
    "E": {
        "keywords": (
            "wholesome",
            "educational",
            "friendly",
            "casual",
            "family",
            "puzzle",
        ),
        "tags": (
            "all-ages",
            "casual",
            "family",
            "wholesome",
            "puzzle",
        ),
    },
}


def _now() -> float:
    return time.time()


def _normalize_tokens(payload: Mapping[str, Any] | None) -> Tuple[set[str], set[str]]:
    text_tokens: set[str] = set()
    tag_tokens: set[str] = set()

    if not payload:
        return text_tokens, tag_tokens

    def _push_text(value: Any) -> None:
        if isinstance(value, str):
            lowered = value.lower()
            for token in lowered.replace("\n", " ").replace("\t", " ").split():
                cleaned = "".join(
                    ch for ch in token if ch.isalnum() or ch in {"+", "#"}
                )
                if cleaned:
                    text_tokens.add(cleaned)

    # Root-level text fields the caller might provide.
    for key in ("text", "title", "description", "summary"):
        _push_text(payload.get(key))

    # Tags array may live directly under payload or meta.
    for tags in (
        payload.get("tags"),
        (payload.get("meta") or {}).get("tags"),
        (payload.get("meta") or {}).get("categories"),
    ):
        if isinstance(tags, (list, tuple, set)):
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    tag_tokens.add(tag.strip().lower())

    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        for value in meta.values():
            _push_text(value)

    return text_tokens, tag_tokens


@dataclass
class RatingResult:
    item_id: str
    rating: str
    confidence: float
    nsfw: bool
    reasons: List[str] = field(default_factory=list)
    matched: Dict[str, List[str]] = field(default_factory=dict)
    source: str = "classifier"
    reviewer: Optional[str] = None
    override_reason: Optional[str] = None
    override_timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "rating": self.rating,
            "confidence": round(self.confidence, 3),
            "nsfw": self.nsfw,
            "reasons": list(self.reasons),
            "matched": {k: list(v) for k, v in self.matched.items()},
            "source": self.source,
            "reviewer": self.reviewer,
            "override_reason": self.override_reason,
            "override_timestamp": self.override_timestamp,
        }


@dataclass
class OverrideRecord:
    item_id: str
    rating: str
    reviewer: str
    reason: str
    scope: str = "asset"
    timestamp: float = field(default_factory=_now)

    def to_result(self) -> RatingResult:
        return RatingResult(
            item_id=self.item_id,
            rating=self.rating,
            confidence=0.99,
            nsfw=self.rating in RISKY_RATINGS,
            reasons=[self.reason],
            matched={},
            source="override",
            reviewer=self.reviewer,
            override_reason=self.reason,
            override_timestamp=self.timestamp,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "rating": self.rating,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "scope": self.scope,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OverrideRecord":
        return cls(
            item_id=str(payload.get("item_id") or payload.get("id") or ""),
            rating=str(payload.get("rating") or "T"),
            reviewer=str(payload.get("reviewer") or "unknown"),
            reason=str(payload.get("reason") or "unspecified"),
            scope=str(payload.get("scope") or "asset"),
            timestamp=float(payload.get("timestamp") or _now()),
        )


class RatingStore:
    """
    Persist reviewer overrides and ack history.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or config_dir("rating", "overrides.json")
        self._cache: Dict[str, OverrideRecord] = {}
        self._acks: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except Exception:
            LOGGER.warning(
                "Rating overrides file unreadable: %s", self.path, exc_info=True
            )
            data = {}

        overrides = data.get("overrides") if isinstance(data, Mapping) else None
        if isinstance(overrides, Mapping):
            for item_id, payload in overrides.items():
                try:
                    record = OverrideRecord.from_dict({"item_id": item_id, **payload})
                except Exception:
                    LOGGER.debug(
                        "Invalid override payload skipped: %s -> %s", item_id, payload
                    )
                    continue
                self._cache[item_id] = record

        acks = data.get("acks") if isinstance(data, Mapping) else None
        if isinstance(acks, Mapping):
            self._acks = {
                key: value for key, value in acks.items() if isinstance(value, Mapping)
            }

    def _write(self) -> None:
        payload = {
            "overrides": {
                item_id: record.to_dict() for item_id, record in self._cache.items()
            },
            "acks": self._acks,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            LOGGER.warning(
                "Failed to persist rating overrides to %s", self.path, exc_info=True
            )

    def get_override(self, item_id: str) -> Optional[OverrideRecord]:
        self._ensure_loaded()
        return self._cache.get(item_id)

    def list_overrides(self) -> List[OverrideRecord]:
        self._ensure_loaded()
        return sorted(self._cache.values(), key=lambda rec: rec.timestamp, reverse=True)

    def put_override(
        self,
        item_id: str,
        rating: str,
        reviewer: str,
        reason: str,
        *,
        scope: str = "asset",
    ) -> OverrideRecord:
        self._ensure_loaded()
        rating = rating.upper()
        if rating not in RATING_ORDER:
            raise ValueError(f"unsupported rating '{rating}'")
        record = OverrideRecord(
            item_id=item_id,
            rating=rating,
            reviewer=reviewer,
            reason=reason,
            scope=scope,
        )
        self._cache[item_id] = record
        self._write()
        LOGGER.info(
            "Rating override stored item=%s rating=%s reviewer=%s scope=%s",
            item_id,
            rating,
            reviewer,
            scope,
        )
        return record

    def delete_override(self, item_id: str) -> bool:
        self._ensure_loaded()
        removed = self._cache.pop(item_id, None)
        if removed:
            self._write()
            LOGGER.info("Rating override removed item=%s", item_id)
            return True
        return False

    def issue_ack(self, *, item_id: str, action: str, rating: str) -> Dict[str, Any]:
        self._ensure_loaded()
        token = uuid.uuid4().hex
        entry = {
            "token": token,
            "item_id": item_id,
            "action": action,
            "rating": rating,
            "issued_at": _now(),
            "acknowledged_at": None,
            "user": None,
            "notes": None,
        }
        self._acks[token] = entry
        self._write()
        return entry

    def acknowledge(
        self, token: str, user: str, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        self._ensure_loaded()
        entry = self._acks.get(token)
        if not entry:
            raise KeyError("ack token not found")
        entry["acknowledged_at"] = _now()
        entry["user"] = user
        if notes:
            entry["notes"] = notes
        self._write()
        LOGGER.info(
            "Rating ack recorded token=%s item=%s action=%s user=%s",
            token,
            entry.get("item_id"),
            entry.get("action"),
            user,
        )
        return entry

    def list_acks(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return sorted(
            self._acks.values(),
            key=lambda entry: entry.get("issued_at") or 0,
            reverse=True,
        )

    def is_acknowledged(self, token: Optional[str]) -> bool:
        if not token:
            return False
        self._ensure_loaded()
        entry = self._acks.get(token)
        if not entry:
            return False
        return bool(entry.get("acknowledged_at"))


class RatingClassifier:
    """
    Heuristic classifier that uses the keyword matrix and metadata hints.
    """

    def classify(self, item_id: str, payload: Mapping[str, Any] | None) -> RatingResult:
        text_tokens, tag_tokens = _normalize_tokens(payload)
        matched: Dict[str, List[str]] = {rating: [] for rating in RATING_MATRIX}

        resolved_rating = "T"
        confidence = 0.55
        reasons: List[str] = []

        def _match(rule_rating: str, category: str, candidates: Iterable[str]) -> None:
            for candidate in candidates:
                lower = candidate.lower()
                if lower in text_tokens or lower in tag_tokens:
                    matched.setdefault(rule_rating, []).append(f"{category}:{lower}")

        for rating, rule in RATING_MATRIX.items():
            keywords = rule.get("keywords") or ()
            tags = rule.get("tags") or ()
            _match(rating, "keyword", keywords)
            _match(rating, "tag", tags)

        for rating in ("Adult", "M", "T", "E"):
            hits = matched.get(rating) or []
            if hits:
                resolved_rating = rating
                reasons.extend(hits)
                confidence = 0.85 if rating in {"Adult", "M"} else 0.7
                break

        if not reasons:
            reasons.append("fallback: conservative teen rating")

        nsfw = resolved_rating in RISKY_RATINGS
        return RatingResult(
            item_id=item_id,
            rating=resolved_rating,
            confidence=confidence,
            nsfw=nsfw,
            reasons=reasons,
            matched={k: v for k, v in matched.items() if v},
        )


class RatingService:
    """
    High level facade combining classifier, overrides, and gating behaviour.
    """

    def __init__(self, store: Optional[RatingStore] = None) -> None:
        self.store = store or RatingStore()
        self.classifier = RatingClassifier()

    def _emit_hook(self, event: str, payload: Dict[str, Any]) -> None:
        if not feature_flags.is_enabled("enable_rating_modder_stream"):
            return
        try:
            from comfyvn.core import modder_hooks
        except Exception:
            return
        try:
            modder_hooks.emit(event, payload)
        except Exception:
            LOGGER.debug("Failed to emit rating hook %s", event, exc_info=True)

    def matrix(self) -> Dict[str, Any]:
        return {
            rating: {
                "keywords": list(rule.get("keywords", ())),
                "tags": list(rule.get("tags", ())),
                "nsfw": rating in RISKY_RATINGS,
                "description": self._describe_rating(rating),
            }
            for rating, rule in RATING_MATRIX.items()
        }

    def _describe_rating(self, rating: str) -> str:
        descriptions = {
            "E": "Everyone — suitable for all audiences.",
            "T": "Teen — may contain mild language or thematic elements.",
            "M": "Mature — intense violence, blood, or substance references.",
            "Adult": "Adult — explicit sexual content or extreme material.",
        }
        return descriptions.get(rating, "Unspecified rating bucket.")

    def classify(self, item_id: str, payload: Mapping[str, Any] | None) -> RatingResult:
        override = self.store.get_override(item_id)
        if override:
            LOGGER.debug(
                "Rating override hit item=%s rating=%s", item_id, override.rating
            )
            return override.to_result()
        result = self.classifier.classify(item_id, payload)
        LOGGER.debug(
            "Rating classified item=%s rating=%s nsfw=%s matched=%s",
            item_id,
            result.rating,
            result.nsfw,
            result.matched,
        )
        return result

    def evaluate(
        self,
        item_id: str,
        payload: Mapping[str, Any] | None,
        *,
        mode: str = "sfw",
        acknowledged: bool = False,
        action: str = "generic",
        ack_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        mode_normalized = (mode or "sfw").strip().lower()
        result = self.classify(item_id, payload)

        requires_ack = mode_normalized == "sfw" and result.rating in RISKY_RATINGS
        allowed = True
        ack_status = "not_required"

        if requires_ack:
            allowed = False
            if acknowledged:
                if ack_token and self.store.is_acknowledged(ack_token):
                    allowed = True
                    ack_status = "verified"
                else:
                    ack_status = "pending"
                    if not ack_token:
                        LOGGER.warning(
                            "Ack requested without token item=%s action=%s rating=%s",
                            item_id,
                            action,
                            result.rating,
                        )
            else:
                entry = self.store.issue_ack(
                    item_id=item_id, action=action, rating=result.rating
                )
                ack_token = entry["token"]
                ack_status = "issued"

        response = {
            "ok": True,
            "item_id": item_id,
            "rating": result.to_dict(),
            "mode": mode_normalized,
            "allowed": allowed,
            "requires_ack": requires_ack,
            "ack_token": ack_token,
            "ack_status": ack_status,
        }
        self._emit_hook(
            "on_rating_decision",
            {
                "item_id": item_id,
                "rating": result.rating,
                "nsfw": result.nsfw,
                "confidence": result.confidence,
                "mode": mode_normalized,
                "source": result.source,
                "matched": result.matched,
                "ack_status": ack_status,
                "allowed": allowed,
            },
        )
        return response

    def put_override(
        self,
        item_id: str,
        rating: str,
        reviewer: str,
        reason: str,
        *,
        scope: str = "asset",
    ) -> RatingResult:
        record = self.store.put_override(item_id, rating, reviewer, reason, scope=scope)
        self._emit_hook(
            "on_rating_override",
            {
                "item_id": record.item_id,
                "rating": record.rating,
                "reviewer": record.reviewer,
                "reason": record.reason,
                "scope": record.scope,
                "removed": False,
                "timestamp": record.timestamp,
            },
        )
        return record.to_result()

    def delete_override(self, item_id: str) -> bool:
        removed = self.store.delete_override(item_id)
        if removed:
            self._emit_hook(
                "on_rating_override",
                {
                    "item_id": item_id,
                    "removed": True,
                },
            )
        return removed

    def list_overrides(self) -> List[Dict[str, Any]]:
        return [record.to_dict() for record in self.store.list_overrides()]

    def acknowledge(
        self, token: str, user: str, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        entry = self.store.acknowledge(token, user, notes)
        self._emit_hook(
            "on_rating_acknowledged",
            {
                "token": entry.get("token"),
                "item_id": entry.get("item_id"),
                "action": entry.get("action"),
                "rating": entry.get("rating"),
                "user": entry.get("user"),
                "acknowledged_at": entry.get("acknowledged_at"),
            },
        )
        return dict(entry)

    def list_acks(self) -> List[Dict[str, Any]]:
        return self.store.list_acks()
