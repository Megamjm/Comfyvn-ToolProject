"""
Runtime paths helpers for ComfyVN Studio.

This module centralises access to mutable directories (data, config, cache,
logs) and redirects them to OS-appropriate locations using ``platformdirs``.
The legacy repo-relative folders are still supported via environment
overrides so power users can keep portable layouts when desired.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

try:
    from platformdirs import PlatformDirs  # type: ignore
except ImportError:  # pragma: no cover - optional dependency

    class PlatformDirs:  # type: ignore
        def __init__(self, appname: str, appauthor: str, roaming: bool) -> None:
            base = Path.cwd().resolve()
            self.user_data_path = str(base / "data")
            self.user_config_path = str(base / "config")
            self.user_cache_path = str(base / "cache")
            self.user_log_path = str(base / "logs")


APP_NAME = os.getenv("COMFYVN_APP_NAME", "ComfyVN Studio")
APP_AUTHOR = os.getenv("COMFYVN_APP_AUTHOR", "ComfyVN")


def _expand(path: Optional[str]) -> Optional[Path]:
    if not path:
        return None
    return Path(path).expanduser().resolve()


@dataclass(frozen=True)
class _RuntimeRoots:
    data: Path
    config: Path
    cache: Path
    logs: Path


@lru_cache(maxsize=1)
def _runtime_roots() -> _RuntimeRoots:
    override_root = _expand(os.getenv("COMFYVN_RUNTIME_ROOT"))
    if override_root:
        override_root.mkdir(parents=True, exist_ok=True)
        data = override_root / "data"
        config = override_root / "config"
        cache = override_root / "cache"
        logs = override_root / "logs"
    else:
        dirs = PlatformDirs(appname=APP_NAME, appauthor=APP_AUTHOR, roaming=False)
        data = Path(dirs.user_data_path)
        config = Path(dirs.user_config_path)
        cache = Path(dirs.user_cache_path)
        logs = Path(dirs.user_log_path)

    data = _expand(os.getenv("COMFYVN_DATA_DIR")) or data
    config = _expand(os.getenv("COMFYVN_CONFIG_DIR")) or config
    cache = _expand(os.getenv("COMFYVN_CACHE_DIR")) or cache
    logs = _expand(os.getenv("COMFYVN_LOG_DIR")) or logs

    for root in (data, config, cache, logs):
        if root.exists() and not root.is_dir():
            raise RuntimeError(
                f"Runtime path {root} exists but is not a directory. "
                "Remove or relocate the conflicting file (for example, rename "
                "it to *.bak) and retry."
            )
        root.mkdir(parents=True, exist_ok=True)

    return _RuntimeRoots(data=data, config=config, cache=cache, logs=logs)


def _join(base: Path, parts: Iterable[str | os.PathLike[str]]) -> Path:
    path = base.joinpath(*[Path(p) for p in parts if p])
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def data_dir(*parts: str | os.PathLike[str]) -> Path:
    return _join(_runtime_roots().data, parts or ())


def config_dir(*parts: str | os.PathLike[str]) -> Path:
    return _join(_runtime_roots().config, parts or ())


def cache_dir(*parts: str | os.PathLike[str]) -> Path:
    return _join(_runtime_roots().cache, parts or ())


def logs_dir(*parts: str | os.PathLike[str]) -> Path:
    return _join(_runtime_roots().logs, parts or ())


def workspace_dir(*parts: str | os.PathLike[str]) -> Path:
    return data_dir("workspaces", *parts)


def diagnostics_dir(*parts: str | os.PathLike[str]) -> Path:
    return logs_dir("diagnostics", *parts)


def jobs_log_file(job_id: str) -> Path:
    return logs_dir("job_logs", f"{job_id}.jsonl")


def imports_log_dir() -> Path:
    return logs_dir("imports")


def thumb_cache_dir() -> Path:
    return cache_dir("thumbs")


def audio_cache_file() -> Path:
    return cache_dir("audio_cache.json")


def music_cache_file() -> Path:
    return cache_dir("music_cache.json")


def render_cache_dir() -> Path:
    return cache_dir("renders")


def settings_file(name: str) -> Path:
    return config_dir("settings", name)


def recent_projects_file() -> Path:
    return logs_dir("recent_projects.json")


def ensure_portable_symlinks(repo_root: Optional[Path] = None) -> None:
    """
    Optionally create legacy directories in the repo root that point at the
    OS-specific locations. This keeps scripts that still reference ``logs/``
    or ``data/workspaces`` working while we migrate callers.
    """
    root = repo_root or Path.cwd()
    mapping = {
        root / "logs": _runtime_roots().logs,
        root / "cache": _runtime_roots().cache,
        root / "data" / "workspaces": workspace_dir(),
        root / "data" / "settings": config_dir("settings"),
    }

    for legacy, target in mapping.items():
        try:
            if legacy.exists() or legacy.is_symlink():
                if legacy.resolve() == target:
                    continue
                if legacy.is_symlink():
                    legacy.unlink()
                elif legacy.is_dir() and not any(legacy.iterdir()):
                    legacy.rmdir()
                else:
                    # Skip non-empty legacy directories to avoid data loss
                    continue
            legacy.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, legacy)
        except OSError:
            # Symlink creation can fail on Windows without elevated perms; fall back to mkdir.
            legacy.mkdir(parents=True, exist_ok=True)
