"""High-level advisory scanner facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from comfyvn.core.advisory_hooks import BundleContext
from comfyvn.core.advisory_hooks import scan as _scan_bundle

BundleDict = Mapping[str, Any]


def _as_path(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    return None


def _coerce_assets(payload: Any) -> Sequence[Tuple[str, Path | None]]:
    assets: List[Tuple[str, Path | None]] = []
    if isinstance(payload, Mapping):
        payload = payload.values()
    if not isinstance(payload, Iterable):
        return assets

    for entry in payload:
        rel: str | None = None
        source: Path | None = None
        if isinstance(entry, (tuple, list)) and entry:
            rel = str(entry[0])
            if len(entry) > 1:
                source = _as_path(entry[1])
        elif isinstance(entry, Mapping):
            rel = (
                entry.get("path")
                or entry.get("relpath")
                or entry.get("id")
                or entry.get("name")
            )
            source = _as_path(entry.get("source") or entry.get("absolute_path"))
        elif isinstance(entry, str):
            rel = entry
        if rel:
            assets.append((str(rel), source))
    return assets


def _coerce_mapping(payload: Any, key_field: str = "id") -> Dict[str, dict]:
    if isinstance(payload, Mapping):
        return {str(k): dict(v) if isinstance(v, Mapping) else v for k, v in payload.items()}  # type: ignore[arg-type]
    result: Dict[str, dict] = {}
    if not isinstance(payload, Iterable):
        return result
    for entry in payload:
        if not isinstance(entry, Mapping):
            continue
        key = entry.get(key_field) or entry.get("scene_id") or entry.get("name")
        if not key:
            continue
        result[str(key)] = dict(entry)
    return result


def _coerce_scene_sources(bundle: BundleDict) -> Dict[str, Path]:
    sources: Dict[str, Path] = {}
    raw_sources = bundle.get("scene_sources")
    if isinstance(raw_sources, Mapping):
        for key, value in raw_sources.items():
            path = _as_path(value)
            if path is not None:
                sources[str(key)] = path
    scenes = bundle.get("scenes")
    if isinstance(scenes, Iterable):
        for entry in scenes:
            if not isinstance(entry, Mapping):
                continue
            key = (
                entry.get("id")
                or entry.get("scene_id")
                or entry.get("name")
                or entry.get("label")
            )
            path = entry.get("path") or entry.get("source")
            if key and path and str(key) not in sources:
                candidate = _as_path(path)
                if candidate is not None:
                    sources[str(key)] = candidate
    return sources


def _bundle_context_from_dict(bundle: BundleDict) -> BundleContext:
    project_id = bundle.get("project_id") or bundle.get("project")
    timeline_id = bundle.get("timeline_id") or bundle.get("timeline")
    metadata = bundle.get("metadata")
    metadata_dict: Dict[str, Any] = {}
    if isinstance(metadata, Mapping):
        metadata_dict = dict(metadata)

    scenes = _coerce_mapping(bundle.get("scenes") or {}, key_field="id")
    characters = _coerce_mapping(bundle.get("characters") or {}, key_field="id")
    licenses = bundle.get("licenses")
    if isinstance(licenses, Sequence) and not isinstance(licenses, (str, bytes)):
        licenses_seq: Sequence[Any] = licenses
    elif isinstance(licenses, Iterable) and not isinstance(licenses, (str, bytes)):
        licenses_seq = list(licenses)
    else:
        licenses_seq = []

    assets = _coerce_assets(bundle.get("assets") or [])
    scene_sources = _coerce_scene_sources(bundle)

    return BundleContext(
        project_id=str(project_id) if project_id else None,
        timeline_id=str(timeline_id) if timeline_id else None,
        scenes=scenes,
        scene_sources=scene_sources,
        characters=characters,
        licenses=licenses_seq,  # type: ignore[arg-type]
        assets=assets,
        metadata=metadata_dict,
    )


def scan(bundle: BundleDict | BundleContext) -> List[Dict[str, Any]]:
    """
    Run the advisory scanner for ``bundle`` and normalise severity levels.

    The return payload matches the CLI expectations: ``level`` is one of
    ``info``/``warn``/``block``.
    """
    if isinstance(bundle, BundleContext):
        context = bundle
    else:
        context = _bundle_context_from_dict(bundle)

    raw_findings = _scan_bundle(context)
    findings: List[Dict[str, Any]] = []
    for entry in raw_findings:
        severity = str(entry.get("severity") or "").lower()
        if severity in {"error", "critical", "block"}:
            level = "block"
        elif severity == "warn":
            level = "warn"
        else:
            level = "info"
        findings.append(
            {
                "level": level,
                "code": entry.get("kind") or "ADVISORY",
                "message": entry.get("message") or "",
                "detail": entry.get("detail") or {},
                "issue_id": entry.get("issue_id"),
                "raw": entry,
            }
        )
    return findings
