"""SillyTavern extension synchronisation helpers.

This module exposes utilities that resolve the SillyTavern extension paths,
produce dry-run copy plans, and perform the actual file updates when
explicitly requested.  It is intentionally dependency-light so it can run
from install hooks or maintenance scripts without importing the full GUI.
"""

from __future__ import annotations

import argparse
import filecmp
import json
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
DEFAULT_MANIFEST_NAME = "manifest.json"
PLUGIN_FOLDER_NAME = "comfyvn-data-exporter"
PLUGIN_PACKAGE_NAME = "package.json"


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


def _manifest_info(directory: Path) -> dict[str, object]:
    manifest_path = Path(directory) / DEFAULT_MANIFEST_NAME
    info: dict[str, object] = {
        "path": manifest_path.as_posix(),
        "exists": manifest_path.exists(),
        "version": None,
        "error": None,
    }
    if not manifest_path.exists():
        info["error"] = "missing"
        return info
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        info["error"] = str(exc)
        return info
    info["manifest"] = data
    version = data.get("version")
    if version is not None:
        info["version"] = str(version)
    return info


def _bundle_plugin_info() -> dict[str, object]:
    plugin_dir = _detect_repo_root() / "SillyTavern Extension" / "plugin"
    bundle_dir = plugin_dir / PLUGIN_FOLDER_NAME
    package_json = bundle_dir / PLUGIN_PACKAGE_NAME
    manifest = {
        "path": package_json.as_posix(),
        "exists": package_json.exists(),
        "version": None,
        "error": None,
    }
    if not package_json.exists():
        manifest["error"] = "missing"
        return {
            "plugin_dir": plugin_dir.as_posix(),
            "bundle_dir": bundle_dir.as_posix(),
            "package": manifest,
        }
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
        manifest["manifest"] = data
        version = data.get("version")
        if version is not None:
            manifest["version"] = str(version)
    except Exception as exc:  # pragma: no cover - defensive
        manifest["error"] = str(exc)
    return {
        "plugin_dir": plugin_dir.as_posix(),
        "bundle_dir": bundle_dir.as_posix(),
        "package": manifest,
    }


def _package_info(path: Path) -> dict[str, object]:
    package_path = path / PLUGIN_PACKAGE_NAME if path.is_dir() else path
    info: dict[str, object] = {
        "path": package_path.as_posix(),
        "exists": package_path.exists(),
        "version": None,
        "error": None,
    }
    if not package_path.exists():
        info["error"] = "missing"
        return info
    try:
        data = json.loads(package_path.read_text(encoding="utf-8"))
        info["manifest"] = data
        version = data.get("version")
        if version is not None:
            info["version"] = str(version)
    except Exception as exc:  # pragma: no cover - defensive
        info["error"] = str(exc)
    return info


def _guess_st_root(path_info: ExtensionPathInfo) -> Optional[Path]:
    candidates = [
        path_info.selected_candidate,
        path_info.destination_dir,
        path_info.destination_dir.parent,
    ]
    for base in candidates:
        if not base:
            continue
        base = Path(base)
        for ancestor in (base, *base.parents):
            if ancestor.name.lower() == "sillytavern":
                return ancestor
        for ancestor in (base, *base.parents):
            if ancestor.name.lower() == "public":
                return ancestor.parent
    return None


def collect_extension_status(
    *,
    source: Optional[Path | str] = None,
    destination: Optional[Path | str] = None,
    extension_name: str = DEFAULT_EXTENSION_NAME,
    settings: Optional[SettingsManager] = None,
    paths: Optional[ExtensionPathInfo] = None,
) -> dict[str, object]:
    context = paths or resolve_paths(
        source=source,
        destination=destination,
        extension_name=extension_name,
        settings=settings,
    )

    source_manifest = _manifest_info(context.source_dir)
    dest_manifest = _manifest_info(context.destination_dir)

    extension_needs_sync = False
    version_status = "unknown"
    if not context.destination_exists:
        version_status = "missing"
        extension_needs_sync = True
    elif (
        source_manifest.get("version")
        and dest_manifest.get("version")
        and source_manifest["version"] == dest_manifest["version"]
    ):
        version_status = "match"
    elif dest_manifest.get("exists"):
        version_status = "mismatch" if source_manifest.get("version") else "unknown"
        extension_needs_sync = True
    else:
        version_status = "missing"
        extension_needs_sync = True

    watch_paths: list[dict[str, object]] = []
    seen: set[str] = set()

    def _add_watch(path: Path, purpose: str) -> None:
        posix = path.as_posix()
        if posix in seen:
            return
        seen.add(posix)
        watch_paths.append({"path": posix, "purpose": purpose, "exists": path.exists()})

    _add_watch(context.source_dir, "extension_source")
    _add_watch(context.destination_dir, "extension_destination")
    if context.destination_dir.parent:
        _add_watch(context.destination_dir.parent, "extensions_root")
    if context.selected_candidate:
        _add_watch(context.selected_candidate, "candidate_base")

    plugin_source = _detect_repo_root() / "SillyTavern Extension" / "plugin"
    _add_watch(plugin_source, "plugin_source")
    bundle_info = _bundle_plugin_info()
    bundle_dir = Path(bundle_info.get("bundle_dir") or plugin_source)
    _add_watch(bundle_dir, "plugin_bundle_dir")
    bundle_package_path = Path(bundle_info["package"]["path"])
    _add_watch(bundle_package_path, "plugin_bundle_package")

    st_root = _guess_st_root(context)
    plugin_dest = None
    plugin_dest_manifest: dict[str, object] | None = None
    if st_root:
        candidate = st_root / "plugins" / PLUGIN_FOLDER_NAME
        plugin_dest = candidate
        _add_watch(candidate, "plugin_destination")
        plugin_dest_manifest = _package_info(candidate)
        _add_watch(Path(plugin_dest_manifest["path"]), "plugin_destination_package")

    plugin_bundle = bundle_info

    bundle_version = plugin_bundle["package"].get("version")
    dest_version = plugin_dest_manifest.get("version") if plugin_dest_manifest else None
    plugin_version_status = "unknown"
    plugin_needs_sync = False
    if plugin_dest_manifest is None:
        plugin_version_status = "unresolved"
    elif not plugin_dest_manifest.get("exists"):
        plugin_version_status = "missing"
        plugin_needs_sync = True
    elif bundle_version and dest_version:
        if bundle_version == dest_version:
            plugin_version_status = "match"
        else:
            plugin_version_status = "mismatch"
            plugin_needs_sync = True
    elif bundle_version and not dest_version:
        plugin_version_status = "unknown"
        plugin_needs_sync = True
    else:
        plugin_version_status = "unknown"

    overall_needs_sync = extension_needs_sync or plugin_needs_sync

    return {
        "needs_sync": extension_needs_sync,
        "overall_needs_sync": overall_needs_sync,
        "extension_needs_sync": extension_needs_sync,
        "version_status": version_status,
        "source_manifest": source_manifest,
        "dest_manifest": dest_manifest,
        "plugin": {
            "source": plugin_bundle,
            "destination": plugin_dest.as_posix() if plugin_dest is not None else None,
            "destination_exists": plugin_dest.exists() if plugin_dest else False,
            "destination_package": plugin_dest_manifest,
            "version_status": plugin_version_status,
            "needs_sync": plugin_needs_sync,
        },
        "watch_paths": watch_paths,
        "plugin_version_status": plugin_version_status,
        "plugin_needs_sync": plugin_needs_sync,
    }


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
