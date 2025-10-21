"""ComfyVN package namespace."""

from __future__ import annotations

from pathlib import Path

from comfyvn.config.runtime_paths import ensure_portable_symlinks

__all__: list[str] = []


def _bootstrap_runtime_paths() -> None:
    try:
        repo_root = Path(__file__).resolve().parents[1]
        ensure_portable_symlinks(repo_root)
    except Exception:
        # Platforms without symlink support fall back to legacy directories.
        pass


_bootstrap_runtime_paths()

# Version will be injected in comfyvn.version during build steps.
__version__ = "1.0.0"
