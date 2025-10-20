"""Bootstrap default data/layout assets for ComfyVN.

This script installs a small set of starter files and directories that help
new users experiment with ComfyVN out of the box.  Run it once after cloning:

    python setup/install_defaults.py

Use `--dry-run` to preview actions, or `--force` to overwrite existing files.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_ROOT = Path(__file__).resolve().parent / "defaults"


ESSENTIAL_DIRS = [
    "data/assets/backgrounds",
    "data/assets/characters",
    "data/assets/music",
    "data/assets/scenes",
    "data/assets/sprites",
    "data/assets/voices",
    "data/assets/_thumbs",
    "data/workflows",
    "data/workflows_comfy",
    "data/playground",
    "data/projects",
    "data/renders",
    "data/templates",
    "data/workspaces/presets",
    "config",
    "logs",
    "scripts",
]


@dataclass(frozen=True)
class CopyAction:
    source: Path
    destination: Path


def discover_default_files(base: Path) -> Iterable[CopyAction]:
    for path in base.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(base)
        yield CopyAction(source=path, destination=REPO_ROOT / rel)


def ensure_directories(directories: Iterable[str], *, dry_run: bool) -> list[str]:
    created: list[str] = []
    for rel in directories:
        target = REPO_ROOT / rel
        if target.exists():
            continue
        created.append(rel)
        if not dry_run:
            target.mkdir(parents=True, exist_ok=True)
    return created


def install_defaults(*, dry_run: bool, force: bool) -> tuple[list[str], list[Path], list[Path]]:
    created_dirs = ensure_directories(ESSENTIAL_DIRS, dry_run=dry_run)
    copied: list[Path] = []
    skipped: list[Path] = []

    for action in discover_default_files(DEFAULTS_ROOT):
        dest = action.destination
        if dest.exists() and not force:
            skipped.append(dest)
            continue
        copied.append(dest)
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if dest.is_file():
                dest.unlink()
            else:
                shutil.rmtree(dest)
        shutil.copy2(action.source, dest)
    return created_dirs, copied, skipped


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install starter data for ComfyVN.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing to disk.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args(argv)

    if not DEFAULTS_ROOT.exists():
        print("[setup] Defaults directory is missing; nothing to install.", file=sys.stderr)
        return 1

    created_dirs, copied, skipped = install_defaults(dry_run=args.dry_run, force=args.force)

    def format_paths(items: Iterable[Path]) -> str:
        return "\n".join(f"  - {path.relative_to(REPO_ROOT)}" for path in items) if items else "  (none)"

    if args.dry_run:
        print("[setup] Dry run complete.")
    else:
        print("[setup] Installation complete.")

    if created_dirs:
        print("• Created directories:")
        for rel in created_dirs:
            print(f"  - {rel}")
    else:
        print("• Created directories:\n  (none)")

    print("• Copied defaults:")
    print(format_paths(copied))

    if skipped:
        print("• Skipped existing files (use --force to overwrite):")
        print(format_paths(skipped))
    else:
        print("• Skipped existing files:\n  (none)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
