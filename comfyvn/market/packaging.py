from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

from .manifest import (
    DEFAULT_GLOBAL_ROUTE_ALLOWLIST,
    TRUST_LEVELS,
    ExtensionManifest,
    ManifestError,
    find_manifest_path,
    load_manifest,
)

DEFAULT_PACKAGE_SUFFIX = ".cvnext"
DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.log",
    ".DS_Store",
    "Thumbs.db",
)


@dataclass
class PackageBuildResult:
    package_path: Path
    manifest: ExtensionManifest
    file_count: int
    bytes_written: int
    sha256: str


def _should_ignore(rel_path: str, ignore_patterns: Iterable[str]) -> bool:
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        parts = rel_path.split("/")
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def _scan_files(
    root: Path,
    *,
    include_hidden: bool,
    ignore_patterns: Iterable[str],
    manifest_name: str,
) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == manifest_name:
            continue
        if not include_hidden and any(
            part.startswith(".") for part in path.relative_to(root).parts
        ):
            continue
        if _should_ignore(rel, ignore_patterns):
            continue
        yield path


def build_extension_package(
    source: str | Path,
    output: str | Path | None = None,
    *,
    trust_level: str | None = None,
    route_allowlist: Mapping[str, Sequence[str]] | None = None,
    include_hidden: bool = False,
    overwrite: bool = False,
    ignore_patterns: Iterable[str] = DEFAULT_IGNORE_PATTERNS,
) -> PackageBuildResult:
    """
    Build a distributable archive for the extension rooted at ``source``.

    The manifest is validated before packaging and serialised back into the
    archive to guarantee consumers read a normalised payload.
    """

    root = Path(source).expanduser().resolve()
    if not root.exists():
        raise ManifestError(f"source directory not found: {root}")
    manifest_path = find_manifest_path(root)
    manifest = load_manifest(
        manifest_path,
        trust_level=trust_level,
        route_allowlist=route_allowlist or DEFAULT_GLOBAL_ROUTE_ALLOWLIST,
    )
    manifest_payload = manifest.to_loader_payload()
    manifest_json = json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n"

    package_name = f"{manifest.id}-{manifest.version}{DEFAULT_PACKAGE_SUFFIX}"
    if output is None:
        dest = root.parent / package_name
    else:
        output_path = Path(output).expanduser().resolve()
        if output_path.is_dir():
            dest = output_path / package_name
        else:
            dest = output_path
    if dest.exists():
        if overwrite:
            dest.unlink()
        else:
            raise ManifestError(f"destination already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    file_count = 1  # manifest entry
    bytes_written = len(manifest_json.encode("utf-8"))

    with ZipFile(dest, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(manifest_path.name, manifest_json)
        for file_path in _scan_files(
            root,
            include_hidden=include_hidden,
            ignore_patterns=ignore_patterns,
            manifest_name=manifest_path.name,
        ):
            rel = file_path.relative_to(root).as_posix()
            zf.write(file_path, rel)
            file_count += 1
            try:
                bytes_written += file_path.stat().st_size
            except OSError:  # pragma: no cover - filesystem race
                pass

    sha256 = _compute_sha256(dest)
    return PackageBuildResult(
        package_path=dest,
        manifest=manifest,
        file_count=file_count,
        bytes_written=bytes_written,
        sha256=sha256,
    )


def _compute_sha256(path: Path, chunk_size: int = 65536) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_allowlist(path: str | Path | None) -> Mapping[str, Sequence[str]] | None:
    if path is None:
        return None
    raw = Path(path).expanduser().resolve()
    if not raw.exists():
        raise ManifestError(f"allowlist file not found: {raw}")
    try:
        data = json.loads(raw.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"allowlist is not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ManifestError("allowlist must be a JSON object {trust_level: [prefixes]}")
    allowlist: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(value, list):
            raise ManifestError(
                f"allowlist for trust '{key}' must be an array of prefixes"
            )
        allowlist[key] = [str(prefix) for prefix in value]
    return allowlist


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package a ComfyVN extension into a signed archive.",
    )
    parser.add_argument("source", help="Path to the extension root directory")
    parser.add_argument(
        "-o",
        "--output",
        help="Destination file or directory (defaults to ../<id>-<version>.cvnext)",
    )
    parser.add_argument(
        "--trust",
        choices=TRUST_LEVELS,
        help="Override the manifest trust level before packaging",
    )
    parser.add_argument(
        "--allowlist",
        help="JSON file describing additional global route allowlist prefixes",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and folders (dot-prefixed) in the archive",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        dest="ignore",
        default=[],
        help="Glob pattern to exclude (may be specified multiple times)",
    )
    args = parser.parse_args(argv)

    try:
        allowlist = _load_allowlist(args.allowlist)
        result = build_extension_package(
            args.source,
            output=args.output,
            trust_level=args.trust,
            route_allowlist=allowlist,
            include_hidden=args.include_hidden,
            overwrite=args.force,
            ignore_patterns=tuple(args.ignore) + DEFAULT_IGNORE_PATTERNS,
        )
    except ManifestError as exc:  # pragma: no cover - CLI path
        print(f"[error] {exc}")
        return os.EX_DATAERR
    print(f"[ok] created {result.package_path}")
    print(
        f"      files={result.file_count} bytes={result.bytes_written} sha256={result.sha256}"
    )
    print(f"      manifest id={result.manifest.id} version={result.manifest.version}")
    print(f"      trust={result.manifest.trust.level}")
    return os.EX_OK


if __name__ == "__main__":  # pragma: no cover - CLI helper
    raise SystemExit(main())
