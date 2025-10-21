"""SillyTavern extension synchronisation helpers.

This module exposes utilities that resolve the SillyTavern extension paths,
produce dry-run copy plans, and perform the actual file updates when
explicitly requested.  It is intentionally dependency-light so it can run
from install hooks or maintenance scripts without importing the full GUI.
"""

from __future__ import annotations

import argparse
import filecmp
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from comfyvn.core.settings_manager import SettingsManager

LOGGER = logging.getLogger(__name__)

ENV_DEST_DIR = "COMFYVN_ST_EXTENSIONS_DIR"
ENV_ST_ROOT = "SILLYTAVERN_PATH"
DEFAULT_EXTENSION_NAME = "ComfyVN"
DEFAULT_SOURCE_ROOT = Path("SillyTavern Extension") / "extension"
DEFAULT_ST_RELATIVE = Path("public") / "scripts" / "extensions"


@dataclass(slots=True)
class CopyAction:
    """Single planned or executed file operation."""

    action: str
    path: str

    def as_dict(self) -> dict[str, str]:
        return {"action": self.action, "path": self.path}


@dataclass(slots=True)
class CopySummary:
    """Container describing the result of a sync operation."""

    source: Path
    destination: Path
    created: int = 0
    updated: int = 0
    skipped: int = 0
    dirs_created: int = 0
    actions: list[CopyAction] = field(default_factory=list)

    @property
    def files_processed(self) -> int:
        return self.created + self.updated + self.skipped

    def record(self, action: str, rel_path: Path) -> None:
        self.actions.append(CopyAction(action=action, path=rel_path.as_posix()))

    def as_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "destination": str(self.destination),
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "dirs_created": self.dirs_created,
            "files_processed": self.files_processed,
            "actions": [action.as_dict() for action in self.actions],
        }


@dataclass(slots=True)
class ExtensionPathInfo:
    """Resolved SillyTavern extension path context."""

    extension_name: str
    source_dir: Path
    source_exists: bool
    destination_dir: Path
    destination_exists: bool
    selected_source: str
    selected_candidate: Path
    selected_candidate_exists: bool
    resolution_chain: list[dict[str, object]]
    config: dict[str, object]
    enabled: bool
    settings_path: Optional[Path]

    def as_dict(self) -> dict[str, object]:
        return {
            "extension_name": self.extension_name,
            "source_dir": str(self.source_dir),
            "source_exists": self.source_exists,
            "destination_dir": str(self.destination_dir),
            "destination_exists": self.destination_exists,
            "resolved_from": self.selected_source,
            "resolved_candidate": str(self.selected_candidate),
            "resolved_candidate_exists": self.selected_candidate_exists,
            "resolution_chain": [
                {
                    "source": entry["source"],
                    "candidate": (
                        str(entry["candidate"]) if entry.get("candidate") else None
                    ),
                    "resolved": (
                        str(entry["resolved"]) if entry.get("resolved") else None
                    ),
                    "exists": entry.get("exists"),
                }
                for entry in self.resolution_chain
            ],
            "config": self.config,
            "enabled": self.enabled,
            "settings_path": str(self.settings_path) if self.settings_path else None,
        }


def _detect_repo_root() -> Path:
    """Resolve the repository root relative to this file."""
    return Path(__file__).resolve().parents[3]


def _resolve_source(base: Optional[Path], extension_name: str) -> Path:
    if base is None:
        base = _detect_repo_root() / DEFAULT_SOURCE_ROOT
    base = base.expanduser().resolve()
    if base.name.lower() == extension_name.lower():
        return base
    candidate = base / extension_name
    if candidate.exists():
        return candidate
    return base


def _candidate_from_env() -> tuple[Optional[Path], Optional[Path]]:
    """Return explicit extension dir and ST root from environment variables."""
    dest_raw = os.getenv(ENV_DEST_DIR)
    env_dir = Path(dest_raw).expanduser() if dest_raw else None
    st_root_raw = os.getenv(ENV_ST_ROOT)
    st_root = Path(st_root_raw).expanduser() if st_root_raw else None
    return env_dir, st_root


def _sanitize_config(raw: dict[str, object]) -> dict[str, object]:
    if not raw:
        return {}
    view: dict[str, object] = {}
    if "enabled" in raw:
        view["enabled"] = bool(raw["enabled"])
    if "base" in raw and raw["base"]:
        view["base"] = raw["base"]
    if "base_url" in raw and raw["base_url"]:
        view["base_url"] = raw["base_url"]
    if "plugin_base" in raw and raw["plugin_base"]:
        view["plugin_base"] = raw["plugin_base"]
    if "extensions_path" in raw and raw["extensions_path"]:
        view["extensions_path"] = raw["extensions_path"]
    if "extensions_dir" in raw and raw["extensions_dir"]:
        view["extensions_dir"] = raw["extensions_dir"]
    if "user_id" in raw and raw["user_id"]:
        view["user_id"] = raw["user_id"]
    if "token" in raw and raw["token"]:
        view["token_present"] = True
    return view


def resolve_paths(
    *,
    source: Optional[Path | str] = None,
    destination: Optional[Path | str] = None,
    extension_name: str = DEFAULT_EXTENSION_NAME,
    settings: Optional[SettingsManager] = None,
) -> ExtensionPathInfo:
    """Resolve SillyTavern extension source and destination paths."""
    if isinstance(source, str):
        source_path = Path(source)
    else:
        source_path = source
    if isinstance(destination, str):
        destination_path = Path(destination)
    else:
        destination_path = destination

    source_dir = _resolve_source(source_path, extension_name)
    source_exists = source_dir.is_dir()

    settings_manager: Optional[SettingsManager] = None
    settings_path: Optional[Path] = None
    config_data: dict[str, object] = {}
    enabled = True
    try:
        settings_manager = settings or SettingsManager()
        settings_path = settings_manager.path
        cfg = settings_manager.load()
        st_cfg = dict(cfg.get("integrations", {}).get("sillytavern", {}))
        config_data = _sanitize_config(st_cfg)
        enabled = bool(st_cfg.get("enabled", True))
        configured_path = st_cfg.get("extensions_path") or st_cfg.get("extensions_dir")
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.debug("Failed to load SillyTavern settings: %s", exc)
        configured_path = None

    env_dir, env_root = _candidate_from_env()

    candidate_chain: list[tuple[str, Optional[Path]]] = [
        ("argument", destination_path),
        ("settings", Path(configured_path).expanduser() if configured_path else None),
        ("env", env_dir),
        (
            "env_root",
            env_root / DEFAULT_ST_RELATIVE if env_root else None,
        ),
        ("default", Path.home() / "SillyTavern" / DEFAULT_ST_RELATIVE),
    ]

    resolution_chain: list[dict[str, object]] = []
    selected_destination: Optional[Path] = None
    selected_candidate: Optional[Path] = None
    selected_source_name = "unknown"
    selected_candidate_exists = False

    for source_name, candidate in candidate_chain:
        entry: dict[str, object] = {"source": source_name, "candidate": candidate}
        if candidate is not None:
            resolved = candidate.expanduser()
            if resolved.name.lower() != extension_name.lower():
                manifest = resolved / "manifest.json"
                if manifest.exists():
                    # Already an extension folder; no suffix needed.
                    final = resolved
                else:
                    final = resolved / extension_name
            else:
                final = resolved
            entry["resolved"] = final
            entry["exists"] = final.exists()
            if selected_destination is None:
                selected_destination = final
                selected_candidate = resolved
                selected_source_name = source_name
                selected_candidate_exists = resolved.exists()
        else:
            entry["resolved"] = None
            entry["exists"] = None
        resolution_chain.append(entry)

    if selected_destination is None:
        # This should not happen because the default candidate is always supplied.
        raise RuntimeError("Failed to resolve SillyTavern extension destination.")

    destination_dir = selected_destination
    destination_exists = destination_dir.exists()

    return ExtensionPathInfo(
        extension_name=extension_name,
        source_dir=source_dir,
        source_exists=source_exists,
        destination_dir=destination_dir,
        destination_exists=destination_exists,
        selected_source=selected_source_name,
        selected_candidate=selected_candidate or destination_dir,
        selected_candidate_exists=selected_candidate_exists,
        resolution_chain=resolution_chain,
        config=config_data,
        enabled=enabled,
        settings_path=settings_path,
    )


def _iter_files(src: Path) -> Iterable[Path]:
    for path in sorted(src.rglob("*")):
        if path.name.startswith("."):
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
    """Copy the SillyTavern extension tree into place."""
    if not source.is_dir():
        raise FileNotFoundError(f"Extension source directory missing: {source}")

    summary = CopySummary(source=source, destination=destination)

    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)

    for path in _iter_files(source):
        rel = path.relative_to(source)
        target = destination / rel
        if path.is_dir():
            if not target.exists():
                summary.dirs_created += 1
                summary.record("mkdir", rel)
                if not dry_run:
                    target.mkdir(parents=True, exist_ok=True)
            continue

        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if _files_equal(path, target):
                summary.skipped += 1
                summary.record("skip", rel)
                continue
            summary.updated += 1
            summary.record("update", rel)
            if not dry_run:
                shutil.copy2(path, target)
        else:
            summary.created += 1
            summary.record("create", rel)
            if not dry_run:
                shutil.copy2(path, target)

    return summary


def sync_extension(
    *,
    source: Optional[Path | str] = None,
    destination: Optional[Path | str] = None,
    extension_name: str = DEFAULT_EXTENSION_NAME,
    dry_run: bool = False,
    settings: Optional[SettingsManager] = None,
    paths: Optional[ExtensionPathInfo] = None,
) -> dict[str, object]:
    """High-level helper that resolves paths and performs the sync."""
    context = paths or resolve_paths(
        source=source,
        destination=destination,
        extension_name=extension_name,
        settings=settings,
    )

    if not context.source_exists:
        raise FileNotFoundError(
            f"SillyTavern extension source missing: {context.source_dir}"
        )

    if (
        not dry_run
        and context.selected_source == "default"
        and not context.selected_candidate_exists
    ):
        raise RuntimeError(
            "SILLYTAVERN_PATH environment variable is not set; skipping SillyTavern "
            "extension sync. Export SILLYTAVERN_PATH or set COMFYVN_ST_EXTENSIONS_DIR "
            "or configure integrations.sillytavern.extensions_path."
        )

    summary = copy_extension_tree(
        context.source_dir, context.destination_dir, dry_run=dry_run
    )
    result = summary.as_dict()
    result.update(
        {
            "dry_run": dry_run,
            "paths": context.as_dict(),
        }
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="comfyvn.bridge.st_bridge.extension_sync",
        description=(
            "Copy the bundled SillyTavern extension into SillyTavern's extensions directory. "
            "Respects COMFYVN_ST_EXTENSIONS_DIR, SILLYTAVERN_PATH, and settings overrides."
        ),
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
            f"Defaults to ${ENV_DEST_DIR}, ${ENV_ST_ROOT}, or ~/SillyTavern/{DEFAULT_ST_RELATIVE}."
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
        help="Walk the copy operation without writing files; emits the planned actions.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for copy decisions.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> dict[str, object]:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    context = resolve_paths(
        source=args.source,
        destination=args.dest,
        extension_name=args.extension_name,
    )

    if not context.source_exists:
        message = (
            f"SillyTavern extension source directory is missing: {context.source_dir}"
        )
        LOGGER.warning(message)
        result = {
            "status": "error",
            "reason": "source_missing",
            "destination": str(context.destination_dir),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "dirs_created": 0,
            "files_processed": 0,
        }
        return result

    if (
        not args.dry_run
        and context.selected_source == "default"
        and not context.selected_candidate_exists
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

    result = sync_extension(
        source=args.source,
        destination=args.dest,
        extension_name=args.extension_name,
        dry_run=args.dry_run,
        paths=context,
    )

    summary = (
        f"created {result['created']}, updated {result['updated']}, "
        f"skipped {result['skipped']}"
    )
    if args.dry_run:
        LOGGER.info(
            "[DRY RUN] SillyTavern extension sync → %s (%s)",
            result["destination"],
            summary,
        )
        for action in result.get("actions", []):
            LOGGER.info(" - %s %s", action["action"], action["path"])
    else:
        LOGGER.info(
            "[OK] SillyTavern extension sync → %s (%s)",
            result["destination"],
            summary,
        )

    return result


if __name__ == "__main__":  # pragma: no cover
    main()
