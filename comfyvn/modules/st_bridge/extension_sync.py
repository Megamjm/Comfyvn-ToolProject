"""Utilities for syncing the SillyTavern extension bundle.

This module exposes a ``main`` entrypoint that copies the bundled SillyTavern
extension assets from the repository into the user's SillyTavern extensions
directory.  It is intentionally lightweight so the install manager can import
it safely during bootstrap.
"""

from __future__ import annotations

import argparse
import filecmp
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

LOGGER = logging.getLogger(__name__)

ENV_DEST_DIR = "COMFYVN_ST_EXTENSIONS_DIR"
ENV_ST_ROOT = "SILLYTAVERN_PATH"
DEFAULT_EXTENSION_NAME = "ComfyVN"
DEFAULT_SOURCE_ROOT = Path("SillyTavern Extension") / "extension"


@dataclass(slots=True)
class CopySummary:
    """Simple container describing the results of a copy operation."""

    source: Path
    destination: Path
    created: int = 0
    updated: int = 0
    skipped: int = 0
    dirs_created: int = 0

    @property
    def files_processed(self) -> int:
        return self.created + self.updated + self.skipped

    def as_dict(self) -> dict[str, str | int]:
        return {
            "source": str(self.source),
            "destination": str(self.destination),
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "dirs_created": self.dirs_created,
            "files_processed": self.files_processed,
        }


def _detect_repo_root() -> Path:
    """Resolve the repository root relative to this file."""
    return Path(__file__).resolve().parents[3]


def _resolve_source(base: Path | None, extension_name: str) -> Path:
    if base is None:
        base = _detect_repo_root() / DEFAULT_SOURCE_ROOT
    base = base.expanduser().resolve()
    if base.name.lower() == extension_name.lower():
        return base
    candidate = base / extension_name
    if candidate.exists():
        return candidate
    return base


def _env_destination() -> Path | None:
    raw = os.getenv(ENV_DEST_DIR)
    if raw:
        return Path(raw).expanduser()
    st_root = os.getenv(ENV_ST_ROOT)
    if not st_root:
        return None
    return Path(st_root).expanduser() / "public" / "scripts" / "extensions"


def _resolve_destination(base: Path | None, extension_name: str) -> Path:
    if base is None:
        base = _env_destination()
    if base is None:
        base = Path.home() / "SillyTavern" / "public" / "scripts" / "extensions"

    base = base.expanduser()
    if base.name.lower() == extension_name.lower():
        return base
    # If target already looks like an extension (manifest present), keep as-is.
    manifest = base / "manifest.json"
    if manifest.exists():
        return base
    return base / extension_name


def _iter_files(src: Path) -> Iterable[Path]:
    for path in sorted(src.rglob("*")):
        if path.name.startswith("."):  # skip dotfiles (build artifacts)
            continue
        yield path


def _files_equal(src: Path, dst: Path) -> bool:
    try:
        return dst.exists() and filecmp.cmp(src, dst, shallow=False)
    except Exception:
        return False


def copy_extension_tree(
    source: Path, destination: Path, *, dry_run: bool = False
) -> CopySummary:
    """Copy the extension bundle into place and return statistics."""
    summary = CopySummary(source=source, destination=destination)
    if not source.is_dir():
        raise FileNotFoundError(f"Extension source directory missing: {source}")

    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)

    for path in _iter_files(source):
        rel = path.relative_to(source)
        target = destination / rel
        if path.is_dir():
            if not target.exists() and not dry_run:
                target.mkdir(parents=True, exist_ok=True)
                summary.dirs_created += 1
            continue

        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if _files_equal(path, target):
                summary.skipped += 1
                LOGGER.debug("skip  %s", rel.as_posix())
                continue
            summary.updated += 1
            LOGGER.debug("update %s", rel.as_posix())
            if not dry_run:
                shutil.copy2(path, target)
        else:
            summary.created += 1
            LOGGER.debug("create %s", rel.as_posix())
            if not dry_run:
                shutil.copy2(path, target)

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="comfyvn.modules.st_bridge.extension_sync",
        description="Copy the bundled SillyTavern extension into SillyTavern's extensions directory.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Path to the source extension directory. Defaults to the bundled repo copy.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        help=(
            "Path to SillyTavern's extensions directory or the final ComfyVN extension folder. "
            f"Defaults to ${ENV_DEST_DIR} or ~/SillyTavern/public/scripts/extensions."
        ),
    )
    parser.add_argument(
        "--extension-name",
        default=DEFAULT_EXTENSION_NAME,
        help=f"Extension folder name (default: {DEFAULT_EXTENSION_NAME}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk the copy operation without writing files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for copy decisions.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, str | int]:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if (
        args.dest is None
        and os.getenv(ENV_DEST_DIR) is None
        and os.getenv(ENV_ST_ROOT) is None
    ):
        LOGGER.info(
            "SILLYTAVERN_PATH environment variable is not set; skipping SillyTavern "
            "extension sync. Export SILLYTAVERN_PATH or use --dest to enable syncing."
        )
        return {
            "status": "skipped",
            "reason": "SILLYTAVERN_PATH not set",
            "destination": None,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "dirs_created": 0,
            "files_processed": 0,
        }

    source = _resolve_source(args.source, args.extension_name)
    destination = _resolve_destination(args.dest, args.extension_name)

    summary = copy_extension_tree(source, destination, dry_run=args.dry_run)
    payload = summary.as_dict()

    status = "DRY RUN" if args.dry_run else "OK"
    print(
        f"[{status}] SillyTavern extension sync → {payload['destination']} "
        f"(created {payload['created']}, updated {payload['updated']}, skipped {payload['skipped']})"
    )
    return payload


if __name__ == "__main__":  # pragma: no cover
    main()
