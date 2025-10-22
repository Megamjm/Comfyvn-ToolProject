from __future__ import annotations

"""
Shared helpers for marketplace publish packagers.

Provides deterministic ZIP construction, license manifest extraction,
and diff helpers so Steam/itch packagers share the same behaviour.
"""

import difflib
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from comfyvn.exporters.renpy_orchestrator import DiffEntry

ZIP_EPOCH: Tuple[int, int, int, int, int, int] = (2025, 1, 1, 0, 0, 0)
SUPPORTED_PLATFORMS: Tuple[str, ...] = ("windows", "linux", "mac")
PLACEHOLDER_ICON: bytes = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000A49444154789C6360000002000154A24F5C0000000049454E44AE426082"
)


@dataclass
class PackageOptions:
    label: Optional[str] = None
    version: Optional[str] = None
    platforms: Sequence[str] = field(default_factory=lambda: ("windows", "linux"))
    publish_root: Path = Path("exports/publish")
    icon_path: Optional[Path] = None
    eula_path: Optional[Path] = None
    license_path: Optional[Path] = None
    include_debug: bool = False
    dry_run: bool = False
    provenance_inputs: Dict[str, Any] = field(default_factory=dict)
    metadata_overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageResult:
    target: str
    label: str
    version: Optional[str]
    archive_path: Optional[Path]
    manifest_path: Path
    license_manifest_path: Path
    checksum: Optional[str]
    dry_run: bool
    diffs: List[DiffEntry] = field(default_factory=list)
    provenance_sidecars: Dict[str, Optional[str]] = field(default_factory=dict)
    hooks_path: Optional[str] = None
    manifest: Dict[str, Any] = field(default_factory=dict)
    license_manifest: Dict[str, Any] = field(default_factory=dict)


class DeterministicZipBuilder:
    """Collect ZIP entries and render them with deterministic metadata."""

    def __init__(self) -> None:
        self._file_entries: List[Tuple[str, Path, int]] = []
        self._byte_entries: List[Tuple[str, bytes, int]] = []

    def add_file(self, arcname: str, source: Path, *, mode: int = 0o644) -> None:
        self._file_entries.append((arcname, source, mode))

    def add_bytes(self, arcname: str, payload: bytes, *, mode: int = 0o644) -> None:
        self._byte_entries.append((arcname, payload, mode))

    def build(self) -> bytes:
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as zf:
            for arcname, source, mode in sorted(
                self._file_entries, key=lambda item: item[0]
            ):
                info = ZipInfo(arcname)
                info.date_time = ZIP_EPOCH
                info.compress_type = ZIP_DEFLATED
                info.external_attr = mode << 16
                with source.open("rb") as handle:
                    zf.writestr(info, handle.read())
            for arcname, payload, mode in sorted(
                self._byte_entries, key=lambda item: item[0]
            ):
                info = ZipInfo(arcname)
                info.date_time = ZIP_EPOCH
                info.compress_type = ZIP_DEFLATED
                info.external_attr = mode << 16
                zf.writestr(info, payload)
        buffer.seek(0)
        return buffer.read()


def slugify(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or fallback


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def ensure_publish_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalise_platforms(platforms: Sequence[str]) -> List[str]:
    result: List[str] = []
    for platform in platforms:
        slug = platform.strip().lower()
        if not slug:
            continue
        if slug not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform '{platform}'")
        if slug not in result:
            result.append(slug)
    if not result:
        raise ValueError("at least one platform must be specified")
    return result


def read_optional(path: Optional[Path]) -> Optional[bytes]:
    if path is None:
        return None
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def build_license_manifest(assets: Dict[str, Any]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for bucket, records in (assets or {}).items():
        if not isinstance(records, Iterable):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            extras = record.get("extras") or {}
            license_name = (
                extras.get("license") or extras.get("licence") or "unspecified"
            )
            author = (
                extras.get("author") or extras.get("creator") or extras.get("artist")
            )
            source_url = (
                extras.get("source_url") or extras.get("source") or record.get("source")
            )
            entries.append(
                {
                    "category": bucket,
                    "relpath": record.get("relpath") or record.get("output"),
                    "alias": record.get("alias"),
                    "license": license_name,
                    "author": author,
                    "source": source_url,
                    "sha256": record.get("sha256"),
                }
            )
    return {
        "count": len(entries),
        "entries": entries,
    }


def diff_text(path: Path, candidate: str) -> DiffEntry:
    if not path.exists():
        return DiffEntry(path=path.as_posix(), status="new", detail=candidate)
    current = path.read_text(encoding="utf-8")
    if current == candidate:
        return DiffEntry(path=path.as_posix(), status="unchanged")
    diff_lines = list(
        difflib.unified_diff(
            current.splitlines(),
            candidate.splitlines(),
            fromfile=path.as_posix(),
            tofile=f"{path.as_posix()} (planned)",
            lineterm="",
            n=3,
        )
    )
    snippet = "\n".join(diff_lines[:200])
    return DiffEntry(path=path.as_posix(), status="modified", detail=snippet)


def diff_binary(path: Path, payload: bytes) -> DiffEntry:
    if not path.exists():
        return DiffEntry(path=path.as_posix(), status="new")
    existing = path.read_bytes()
    if existing == payload:
        return DiffEntry(path=path.as_posix(), status="unchanged")
    current = sha256_bytes(existing)
    planned = sha256_bytes(payload)
    return DiffEntry(
        path=path.as_posix(),
        status="modified",
        detail=json.dumps({"current_sha256": current, "planned_sha256": planned}),
    )


def collect_game_files(game_dir: Path) -> List[Tuple[str, Path]]:
    files: List[Tuple[str, Path]] = []
    if not game_dir.exists():
        return files
    for entry in sorted(game_dir.rglob("*")):
        if entry.is_file():
            rel = entry.relative_to(game_dir).as_posix()
            files.append((rel, entry))
    return files


def hooks_payload() -> Dict[str, Any]:
    try:
        from comfyvn.core import modder_hooks
    except Exception:
        return {"available": False, "events": []}

    specs = modder_hooks.hook_specs()
    events = []
    for name, spec in sorted(specs.items()):
        events.append(
            {
                "name": name,
                "description": spec.description,
                "payload_fields": spec.payload_fields,
                "ws_topic": spec.ws_topic,
                "rest_event": spec.rest_event,
            }
        )
    return {"available": True, "events": events}


def resolve_icon_bytes(options: PackageOptions) -> bytes:
    data = read_optional(options.icon_path)
    if data:
        return data
    return PLACEHOLDER_ICON


def resolve_eula_text(options: PackageOptions, *, target: str, label: str) -> str:
    raw = None
    if options.eula_path:
        try:
            raw = options.eula_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = None
    if raw:
        return raw
    return (
        f"{label} — {target.capitalize()} build EULA\n"
        "This is a placeholder agreement. Replace this file with your studio's personalised EULA.\n"
        "Generated by ComfyVN export publish pipeline.\n"
    )


def resolve_license_text(
    options: PackageOptions, license_manifest: Dict[str, Any]
) -> str:
    if options.license_path:
        try:
            return options.license_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            pass
    summary = [
        "ComfyVN License Manifest Summary",
        f"Entries: {license_manifest.get('count', 0)}",
        "",
    ]
    for entry in license_manifest.get("entries", [])[:20]:
        summary.append(
            f"- {entry.get('relpath') or entry.get('alias')}: {entry.get('license')} ({entry.get('source')})"
        )
    if license_manifest.get("count", 0) > 20:
        summary.append("... (truncated)")
    summary.append("")
    summary.append(
        "Provide a dedicated license file via publish request to override this summary."
    )
    return "\n".join(summary)


def package_slug(
    project_id: str, label: Optional[str], version: Optional[str], target: str
) -> str:
    base = slugify(label or project_id or target, fallback=target)
    if version:
        version_slug = slugify(version, fallback="v")
        return f"{base}-{version_slug}"
    return base


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_json_log(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + os.linesep)


__all__ = [
    "DeterministicZipBuilder",
    "PackageOptions",
    "PackageResult",
    "ZIP_EPOCH",
    "SUPPORTED_PLATFORMS",
    "append_json_log",
    "build_license_manifest",
    "collect_game_files",
    "diff_binary",
    "diff_text",
    "ensure_publish_root",
    "hooks_payload",
    "normalise_platforms",
    "package_slug",
    "read_optional",
    "resolve_eula_text",
    "resolve_icon_bytes",
    "resolve_license_text",
    "sha256_bytes",
    "sha256_file",
    "slugify",
    "write_json",
]
