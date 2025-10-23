"""ComfyVN package namespace."""

from __future__ import annotations

import sys
import types
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


def _ensure_qt_stub() -> None:
    """Provide a minimal Qt stub when PySide6 cannot be imported (e.g. headless servers)."""
    try:
        from PySide6.QtGui import QAction  # type: ignore

        _ = QAction  # pragma: no cover - ensure import executed
    except Exception:
        qt_module = types.ModuleType("PySide6")
        qtgui_module = types.ModuleType("PySide6.QtGui")

        class _DummySignal:
            def connect(self, *_args, **_kwargs) -> None:  # pragma: no cover - noop
                return None

        class QAction:  # type: ignore
            """Fallback QAction stub for non-GUI environments."""

            def __init__(self, *_args, **_kwargs) -> None:
                self.triggered = _DummySignal()

            def setShortcut(self, *_args, **_kwargs) -> None:
                return None

            def setStatusTip(self, *_args, **_kwargs) -> None:
                return None

            def setObjectName(self, *_args, **_kwargs) -> None:
                return None

        qtgui_module.QAction = QAction  # type: ignore[attr-defined]
        qt_module.QtGui = qtgui_module  # type: ignore[attr-defined]
        sys.modules.setdefault("PySide6", qt_module)
        sys.modules["PySide6.QtGui"] = qtgui_module


_ensure_qt_stub()

# Version will be injected in comfyvn.version during build steps.
__version__ = "1.0.0"
