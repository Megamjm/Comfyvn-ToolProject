from __future__ import annotations

import logging
import re
import shutil
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from comfyvn.config.runtime_paths import data_dir
from comfyvn.core.advisory import AdvisoryIssue, log_issue

LOGGER = logging.getLogger(__name__)


@dataclass
class ImportSession:
    """Represents the working directories for a single import job."""

    kind: str
    import_id: str
    source_path: Path
    raw_path: Path
    extracted_dir: Path
    converted_dir: Path
    data_root: Path
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary_path(self) -> Path:
        return self.converted_dir / "summary.json"

    @property
    def manifest_path(self) -> Path:
        return self.converted_dir / "manifest.json"

    @property
    def base_dir(self) -> Path:
        """Return the root directory for this import kind (e.g., data/imports/vn)."""
        return self.converted_dir.parent.parent


class FileImporter:
    """
    Helper for provisioning on-disk directories used by import pipelines.

    Each import kind (``vn`` / ``manga`` / etc.) receives dedicated ``raw``,
    ``extracted``, and ``converted`` directories under ``data/imports/<kind>``.
    """

    def __init__(self, kind: str, *, data_root: Optional[Path | str] = None) -> None:
        base_root = Path(data_root).expanduser().resolve() if data_root else data_dir()
        self.kind = kind
        self.data_root = base_root
        self.kind_root = base_root / "imports" / kind
        self.raw_dir = self.kind_root / "raw"
        self.extracted_dir = self.kind_root / "extracted"
        self.converted_dir = self.kind_root / "converted"

        for path in (
            self.kind_root,
            self.raw_dir,
            self.extracted_dir,
            self.converted_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _generate_import_id(self, source: Path) -> str:
        timestamp = int(time.time())
        suffix = uuid.uuid4().hex[:6]
        stem = source.stem.replace(" ", "_") or "import"
        return f"{stem}-{timestamp}-{suffix}"

    def new_session(
        self,
        source: Path | str,
        *,
        import_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ImportSession:
        """
        Prepare a new import session by copying ``source`` into the ``raw`` directory
        and creating fresh ``extracted`` / ``converted`` working folders.
        """

        source_path = Path(source).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"source path does not exist: {source_path}")

        import_id = import_id or self._generate_import_id(source_path)

        raw_target = self._allocate_raw_path(source_path, import_id)
        LOGGER.debug(
            "Provisioning import session kind=%s id=%s src=%s raw=%s",
            self.kind,
            import_id,
            source_path,
            raw_target,
        )
        shutil.copy2(source_path, raw_target)

        extracted_dir = self._ensure_clean_dir(self.extracted_dir / import_id)
        converted_dir = self._ensure_clean_dir(self.converted_dir / import_id)

        session = ImportSession(
            kind=self.kind,
            import_id=import_id,
            source_path=source_path,
            raw_path=raw_target,
            extracted_dir=extracted_dir,
            converted_dir=converted_dir,
            data_root=self.data_root,
            metadata=dict(metadata or {}),
        )
        return session

    def _allocate_raw_path(self, source_path: Path, import_id: str) -> Path:
        suffix = source_path.suffix
        if suffix:
            filename = f"{import_id}{suffix}"
        else:
            filename = f"{import_id}_{source_path.name}"
        target = self.raw_dir / filename
        # Avoid collisions if the generated name already exists.
        counter = 1
        candidate = target
        while candidate.exists():
            candidate = target.with_stem(f"{target.stem}_{counter}")
            counter += 1
        return candidate

    @staticmethod
    def _ensure_clean_dir(path: Path) -> Path:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        return path


_OPEN_LICENSE_HINTS = (
    "cc0",
    "cc-by",
    "creative commons",
    "public domain",
    "mit",
    "bsd",
    "apache",
    "isc",
    "mpl",
    "gpl",
    "lgpl",
    "agpl",
    "unlicense",
)


def _is_open_license(name: str) -> bool:
    lowered = name.strip().lower()
    return any(hint in lowered for hint in _OPEN_LICENSE_HINTS)


def log_license_issues(
    import_id: str,
    assets: List[str],
    licenses: List[Any],
    *,
    import_kind: str,
) -> List[Dict[str, Any]]:
    """
    Record advisory issues for assets that lack clear open-licence provenance.

    Returns the serialized advisory payloads for inclusion in importer summaries.
    """

    advisories: List[Dict[str, Any]] = []
    assets = assets or []
    licenses = licenses or []

    if not assets:
        return advisories

    if not licenses:
        limit = min(len(assets), 25)
        for asset in assets[:limit]:
            issue = AdvisoryIssue(
                target_id=f"asset:{asset}",
                kind="copyright",
                message="Asset imported without license metadata; manual review required.",
                severity="warn",
                detail={"import_id": import_id, "import_kind": import_kind},
            )
            log_issue(issue)
            advisories.append(issue.to_dict())
        if len(assets) > limit:
            issue = AdvisoryIssue(
                target_id=f"import:{import_id}",
                kind="policy",
                message="Additional assets missing license metadata",
                severity="warn",
                detail={
                    "skipped_assets": len(assets) - limit,
                    "import_kind": import_kind,
                },
            )
            log_issue(issue)
            advisories.append(issue.to_dict())
        return advisories
    for entry in licenses:
        if isinstance(entry, dict):
            name = str(entry.get("name") or entry.get("id") or "").strip()
            scope = entry.get("scope")
        else:
            name = str(entry).strip()
            scope = None
        if not name:
            name = "unspecified"
        if _is_open_license(name):
            continue
        target_suffix = f":{scope}" if scope else ""
        issue = AdvisoryIssue(
            target_id=f"import:{import_id}{target_suffix}",
            kind="policy",
            message=f"Non-open license detected: {name}",
            severity="warn",
            detail={"license": entry, "assets": assets, "import_kind": import_kind},
        )
        log_issue(issue)
        advisories.append(issue.to_dict())

    return advisories


_PREVIEW_LINE_PATTERN = re.compile(r"\s+")


def _ensure_layout_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class ImportDirectories:
    """
    Helper representing the canonical ``raw/extracted/converted/preview`` layout.
    """

    root: Path
    raw: Path
    extracted: Path
    converted: Path
    preview: Path
    status: Path

    @classmethod
    def ensure(cls, *parts: str) -> "ImportDirectories":
        root = _ensure_layout_dir(data_dir("imports", *parts))
        raw = _ensure_layout_dir(root / "raw")
        extracted = _ensure_layout_dir(root / "extracted")
        converted = _ensure_layout_dir(root / "converted")
        preview = _ensure_layout_dir(root / "preview")
        status = _ensure_layout_dir(root / "status")
        return cls(
            root=root,
            raw=raw,
            extracted=extracted,
            converted=converted,
            preview=preview,
            status=status,
        )


def sanitize_filename(filename: Optional[str], default: str = "upload.txt") -> str:
    """
    Normalise a user-supplied filename into a filesystem-safe variant.
    """
    if not filename:
        return default

    candidate = str(filename).split("/")[-1].split("\\")[-1].strip()
    candidate = (
        unicodedata.normalize("NFKD", candidate)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    candidate = candidate.replace(" ", "_")
    candidate = re.sub(r"[^A-Za-z0-9._-]", "", candidate)
    candidate = candidate.lstrip("._")

    if not candidate:
        return default

    return candidate[:128]


def build_preview_excerpt(
    lines: Sequence[Dict[str, Any]],
    *,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """
    Return a trimmed list of transcript lines suitable for preview panels.
    """
    excerpt: List[Dict[str, Any]] = []
    for entry in lines[:limit]:
        speaker = str(entry.get("speaker") or "Narrator")
        text = str(entry.get("text") or "")
        slot: Dict[str, Any] = {"speaker": speaker, "text": text}
        meta = entry.get("meta")
        if meta:
            slot["meta"] = meta
        excerpt.append(slot)
    return excerpt


def flatten_lines(lines: Iterable[Dict[str, Any]]) -> str:
    """
    Convert structured lines into a newline-separated transcript.
    """
    chunks: List[str] = []
    for entry in lines:
        speaker = str(entry.get("speaker") or "Narrator")
        text = str(entry.get("text") or "")
        chunks.append(f"{speaker}: {text}")
    return "\n".join(chunks)


def build_preview_payload(
    *,
    scene_uid: str,
    title: str,
    detail_level: str,
    lines: Sequence[Dict[str, Any]],
    participants: Sequence[str],
    persona_hints: Dict[str, List[str]],
    advisory_flags: Sequence[Dict[str, Any]],
    world: Optional[str] = None,
    source: Optional[str] = None,
    excerpt_limit: int = 6,
) -> Dict[str, Any]:
    """
    Construct a lightweight preview payload for Studio consumers.
    """
    excerpt = build_preview_excerpt(lines, limit=excerpt_limit)
    synopsis = " ".join(
        _PREVIEW_LINE_PATTERN.sub(" ", slot["text"]).strip()
        for slot in excerpt
        if slot.get("text")
    ).strip()
    synopsis = synopsis[:320]

    return {
        "scene_uid": scene_uid,
        "title": title,
        "detail_level": detail_level,
        "participants": list(participants),
        "persona_hints": dict(persona_hints),
        "world": world,
        "source": source,
        "excerpt": excerpt,
        "line_count": len(lines),
        "synopsis": synopsis,
        "advisory_flags": list(advisory_flags),
    }


__all__ = [
    "FileImporter",
    "ImportSession",
    "ImportDirectories",
    "sanitize_filename",
    "build_preview_excerpt",
    "build_preview_payload",
    "flatten_lines",
    "log_license_issues",
]
