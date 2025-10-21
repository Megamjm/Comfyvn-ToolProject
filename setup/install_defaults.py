"""Bootstrap default data/layout assets for ComfyVN.

This script installs a small set of starter files and directories that help
new users experiment with ComfyVN out of the box.  Run it once after cloning:

    python setup/install_defaults.py

Use `--dry-run` to preview actions, or `--force` to overwrite existing files.
"""

from __future__ import annotations

import argparse
import errno
import os
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_DEFAULTS_ROOT = Path(__file__).resolve().parent / "defaults"
WORLDS_SOURCE = REPO_ROOT / "defaults" / "worlds"
WORLDS_DEST = REPO_ROOT / "data" / "worlds"
SILLYTAVERN_SOURCE = REPO_ROOT / "SillyTavern Extension"
SILLYTAVERN_DEST = REPO_ROOT / "extensions" / "sillytavern"
LOGS_TEST_FILENAME = "install_defaults_check.txt"

CATEGORY_CORE = "core"
CATEGORY_WORLDS = "worlds"
CATEGORY_SILLYTAVERN = "sillytavern"

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
    "data/worlds",
    "config",
    "logs",
    "scripts",
]


@dataclass(frozen=True)
class CopyAction:
    source: Path
    destination: Path
    category: str


@dataclass
class InstallSummary:
    created_dirs: list[str]
    copied: dict[str, list[Path]]
    linked: dict[str, list[Path]]
    skipped: dict[str, list[Path]]
    logs_test_file: Path | None
    warnings: list[str] = field(default_factory=list)

    def combined(self, category: str) -> list[Path]:
        return self.copied.get(category, []) + self.linked.get(category, [])

    def skipped_for(self, category: str) -> list[Path]:
        return self.skipped.get(category, [])


def discover_copy_actions(
    base: Path, destination_root: Path, category: str
) -> Iterable[CopyAction]:
    if not base.exists():
        return []
    actions: list[CopyAction] = []
    for path in base.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(base)
        actions.append(
            CopyAction(
                source=path,
                destination=destination_root / rel,
                category=category,
            )
        )
    return actions


def ensure_directories(
    directories: Iterable[str], *, dry_run: bool
) -> tuple[list[str], list[str]]:
    created: list[str] = []
    warnings: list[str] = []
    for rel in directories:
        target = REPO_ROOT / rel
        if target.exists():
            continue
        if dry_run:
            created.append(rel)
            continue
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                loop_parent = target.parent
                try:
                    loop_display = loop_parent.relative_to(REPO_ROOT)
                except ValueError:
                    loop_display = loop_parent
                warnings.append(
                    f"Skipped creating {rel}: symlink loop detected near {loop_display}"
                )
                continue
            warnings.append(f"Failed to create {rel}: {exc}")
            continue
        created.append(rel)
    return created, warnings


def apply_copy_action(
    action: CopyAction,
    *,
    dry_run: bool,
    force: bool,
    prefer_symlinks: bool,
) -> str:
    destination = action.destination
    destination_parent = destination.parent
    existing = destination.exists() or destination.is_symlink()

    if existing and not force:
        return "skipped"

    outcome = "linked" if prefer_symlinks else "copied"

    if dry_run:
        return outcome if not existing else outcome

    destination_parent.mkdir(parents=True, exist_ok=True)

    if existing:
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    if prefer_symlinks:
        try:
            rel_target = os.path.relpath(action.source, start=destination_parent)
            os.symlink(rel_target, destination)
            return "linked"
        except OSError:
            # Fall back to copying if symlink creation fails (e.g., Windows without privileges).
            pass

    shutil.copy2(action.source, destination)
    return "copied"


def verify_logs_directory(*, dry_run: bool) -> Path | None:
    logs_dir = REPO_ROOT / "logs"
    test_file = logs_dir / LOGS_TEST_FILENAME
    if dry_run:
        return test_file

    logs_dir.mkdir(parents=True, exist_ok=True)
    content = (
        "ComfyVN defaults installer verification -- "
        f"{datetime.now().isoformat(timespec='seconds')}\n"
    )
    test_file.write_text(content, encoding="utf-8")
    return test_file


def install_defaults(
    *,
    dry_run: bool,
    force: bool,
    install_sillytavern: bool,
    use_symlinks: bool,
) -> InstallSummary:
    created_dirs, dir_warnings = ensure_directories(ESSENTIAL_DIRS, dry_run=dry_run)

    copied: dict[str, list[Path]] = defaultdict(list)
    linked: dict[str, list[Path]] = defaultdict(list)
    skipped: dict[str, list[Path]] = defaultdict(list)
    warnings: list[str] = list(dir_warnings)

    actions: list[CopyAction] = []
    if SETUP_DEFAULTS_ROOT.exists():
        actions.extend(
            discover_copy_actions(SETUP_DEFAULTS_ROOT, REPO_ROOT, CATEGORY_CORE)
        )
    else:
        warnings.append(
            "Setup defaults directory is missing; skipped core starter assets."
        )

    if WORLDS_SOURCE.exists():
        actions.extend(
            discover_copy_actions(WORLDS_SOURCE, WORLDS_DEST, CATEGORY_WORLDS)
        )
    else:
        warnings.append(
            "World defaults directory is missing at defaults/worlds; skipped world presets."
        )

    if install_sillytavern:
        created_ext, extra_warnings = ensure_directories(
            ["extensions/sillytavern"], dry_run=dry_run
        )
        created_dirs.extend(created_ext)
        warnings.extend(extra_warnings)
        if SILLYTAVERN_SOURCE.exists():
            actions.extend(
                discover_copy_actions(
                    SILLYTAVERN_SOURCE, SILLYTAVERN_DEST, CATEGORY_SILLYTAVERN
                )
            )
        else:
            warnings.append(
                "SillyTavern Extension source is missing; skipping extension install."
            )

    for action in actions:
        result = apply_copy_action(
            action,
            dry_run=dry_run,
            force=force,
            prefer_symlinks=use_symlinks,
        )

        if result == "skipped":
            skipped[action.category].append(action.destination)
        elif result == "linked":
            linked[action.category].append(action.destination)
        else:
            copied[action.category].append(action.destination)

    logs_test_file = verify_logs_directory(dry_run=dry_run)

    return InstallSummary(
        created_dirs=created_dirs,
        copied=dict(copied),
        linked=dict(linked),
        skipped=dict(skipped),
        logs_test_file=logs_test_file,
        warnings=warnings,
    )


def prompt_yes_no(question: str, *, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    prompt = f"{question} {suffix} "
    while True:
        try:
            response = input(prompt).strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt:
            print("\n[setup] Cancelled by user.")
            raise SystemExit(1)

        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please respond with 'y' or 'n'.")


def print_summary(
    summary: InstallSummary,
    *,
    dry_run: bool,
    install_sillytavern: bool,
) -> None:
    def format_paths(paths: Iterable[Path]) -> str:
        items = list(paths)
        if not items:
            return "  (none)"
        return "\n".join(f"  - {path.relative_to(REPO_ROOT)}" for path in items)

    def format_with_symlink_flag(category: str) -> str:
        combined = summary.combined(category)
        if not combined:
            return "  (none)"
        symlink_targets = set(summary.linked.get(category, []))
        lines = []
        for path in combined:
            marker = " (symlink)" if path in symlink_targets else ""
            lines.append(f"  - {path.relative_to(REPO_ROOT)}{marker}")
        return "\n".join(lines)

    if dry_run:
        print("[setup] Dry run complete.")
    else:
        print("[setup] Installation complete.")

    if summary.created_dirs:
        print("• Created directories:")
        for rel in summary.created_dirs:
            print(f"  - {rel}")
    else:
        print("• Created directories:\n  (none)")

    print("• Copied defaults:")
    print(format_with_symlink_flag(CATEGORY_CORE))

    print("• Seeded worlds:")
    print(format_with_symlink_flag(CATEGORY_WORLDS))

    if install_sillytavern:
        print("• Installed SillyTavern extension:")
        print(format_with_symlink_flag(CATEGORY_SILLYTAVERN))
    else:
        print("• Installed SillyTavern extension:\n  (skipped by user)")

    skipped_paths = []
    for paths in summary.skipped.values():
        skipped_paths.extend(paths)
    if skipped_paths:
        print("• Skipped existing files (use --force to overwrite):")
        print(format_paths(skipped_paths))
    else:
        print("• Skipped existing files:\n  (none)")

    if summary.logs_test_file is not None:
        relative = summary.logs_test_file.relative_to(REPO_ROOT)
        if dry_run:
            print(f"• Logs write test:\n  would write {relative}")
        else:
            print(f"• Logs write test:\n  wrote {relative}")

    if summary.warnings:
        print("• Warnings:")
        for message in summary.warnings:
            print(f"  - {message}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Install starter data for ComfyVN.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show actions without writing to disk."
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing files."
    )
    parser.add_argument(
        "--use-symlinks",
        action="store_true",
        help="Prefer creating symlinks instead of copying files (falls back to copying).",
    )
    parser.add_argument(
        "--include-sillytavern",
        dest="include_sillytavern",
        action="store_true",
        help="Install the SillyTavern extension without prompting.",
    )
    parser.add_argument(
        "--no-sillytavern",
        dest="no_sillytavern",
        action="store_true",
        help="Skip installing the SillyTavern extension without prompting.",
    )
    args = parser.parse_args(argv)

    if not SETUP_DEFAULTS_ROOT.exists():
        print(
            "[setup] Defaults directory is missing; nothing to install.",
            file=sys.stderr,
        )
        return 1

    if args.include_sillytavern and args.no_sillytavern:
        print("[setup] Conflicting SillyTavern flags provided.", file=sys.stderr)
        return 2

    if args.include_sillytavern:
        install_silly = True
    elif args.no_sillytavern:
        install_silly = False
    else:
        if sys.stdin.isatty():
            install_silly = prompt_yes_no(
                "Install SillyTavern bridge assets?", default=True
            )
        else:
            install_silly = False

    if install_silly and not SILLYTAVERN_SOURCE.exists():
        print(
            "[setup] SillyTavern Extension assets were not found; skipping installation.",
            file=sys.stderr,
        )
        install_silly = False

    summary = install_defaults(
        dry_run=args.dry_run,
        force=args.force,
        install_sillytavern=install_silly,
        use_symlinks=args.use_symlinks,
    )

    print_summary(
        summary,
        dry_run=args.dry_run,
        install_sillytavern=install_silly,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
