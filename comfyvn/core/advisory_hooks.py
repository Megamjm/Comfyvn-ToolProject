from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from comfyvn.core.advisory import AdvisoryIssue, log_issue, scanner

LOGGER = logging.getLogger("comfyvn.advisory.hooks")


@dataclass
class BundleContext:
    """Lightweight context describing a content bundle for advisory scans."""

    project_id: Optional[str] = None
    timeline_id: Optional[str] = None
    scenes: Dict[str, dict] = field(default_factory=dict)
    scene_sources: Dict[str, Optional[Path]] = field(default_factory=dict)
    characters: Dict[str, dict] = field(default_factory=dict)
    licenses: Sequence[Any] = field(default_factory=list)
    assets: Sequence[Tuple[str, Optional[Path]]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def _target(self, suffix: str) -> str:
        base = f"project:{self.project_id}" if self.project_id else "project:unknown"
        return f"{base}:{suffix}"


def _flatten_scene_text(scene: dict) -> str:
    """Extract dialogue text from a scene structure for keyword scanning."""

    fragments: List[str] = []

    def _append(value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            fragments.append(text)

    _append(scene.get("title"))
    _append(scene.get("summary"))
    _append(scene.get("description"))

    dialogue: Iterable[Any]
    if isinstance(scene.get("dialogue"), list):
        dialogue = scene["dialogue"]
    elif isinstance(scene.get("lines"), list):
        dialogue = scene["lines"]
    else:
        dialogue = []

    for entry in dialogue:
        if isinstance(entry, str):
            _append(entry)
            continue
        if isinstance(entry, dict):
            _append(entry.get("text"))
            _append(entry.get("prompt"))
            if isinstance(entry.get("options"), list):
                for option in entry["options"]:
                    if isinstance(option, dict):
                        _append(option.get("text"))
            continue
        if isinstance(entry, Iterable):
            for item in entry:
                _append(item)

    if not fragments:
        fallback = scene.get("narration") or scene.get("body") or ""
        _append(fallback)

    return "\n".join(fragments)


def scan(bundle: BundleContext) -> List[Dict[str, Any]]:
    """
    Run advisory scans against a bundle context.

    Findings are logged via ``log_issue`` and the serialized issue payloads are returned.
    """

    findings: List[Dict[str, Any]] = []

    def _record(issue: AdvisoryIssue) -> None:
        if bundle.timeline_id and "timeline_id" not in issue.detail:
            issue.detail["timeline_id"] = bundle.timeline_id
        if bundle.metadata and "source" not in issue.detail:
            issue.detail["source"] = bundle.metadata.get("source")
        entry = log_issue(issue)
        findings.append(entry)

    for scene_id, payload in bundle.scenes.items():
        text = _flatten_scene_text(payload)
        if not text.strip():
            continue
        issues = scanner.scan(f"scene:{scene_id}", text, license_scan=True)
        source_path = bundle.scene_sources.get(scene_id)
        for issue in issues:
            if source_path:
                issue.detail.setdefault("path", Path(source_path).as_posix())
            _record(issue)

    if bundle.assets and not bundle.licenses:
        issue = AdvisoryIssue(
            target_id=bundle._target("assets"),
            kind="policy",
            message="Assets present without accompanying license metadata.",
            severity="warn",
            detail={
                "assets_without_license": len(bundle.assets),
                "origin": bundle.metadata.get("source", "unspecified"),
            },
        )
        _record(issue)

    LOGGER.info(
        "Advisory bundle scan project=%s timeline=%s findings=%s scenes=%s assets=%s",
        bundle.project_id or "unknown",
        bundle.timeline_id or "unknown",
        len(findings),
        len(bundle.scenes),
        len(bundle.assets),
    )
    return findings
