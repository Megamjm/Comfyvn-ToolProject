"""
Compatibility shim for the phase-06 rebuild helper.

Historically the migration script lived under ``setup/``.  The canonical
implementation now resides in ``tools.apply_phase06_rebuild``; this
module re-exports the public helpers so existing imports continue to
work without modification.
"""

from __future__ import annotations

from tools.apply_phase06_rebuild import (  # noqa: F401
    DIRS,
    apply_schema,
    ensure_db,
    ensure_dirs,
    main,
    rebuild,
)

__all__ = ["DIRS", "apply_schema", "ensure_db", "ensure_dirs", "main", "rebuild"]


if __name__ == "__main__":
    main()
