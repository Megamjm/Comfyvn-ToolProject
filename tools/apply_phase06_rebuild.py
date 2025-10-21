"""
Phase 0 (v0.6) rebuild helper.

This CLI provisions the canonical directory layout and bootstraps the
SQLite schema required by the Studio shell.  It is safe to run multiple
times; tables are created on demand and missing columns are patched in.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfyvn.core.db_manager import DEFAULT_DB_PATH, DBManager  # noqa: E402

DATA_ROOT = ROOT / "data"

DIRS: Iterable[Path] = (
    ROOT / "logs",
    ROOT / "exports",
    ROOT / "cache" / "sprites",
    ROOT / "cache" / "thumbs",
    ROOT / "comfyvn" / "data" / "templates",
    ROOT / "comfyvn" / "data" / "settings",
    ROOT / "comfyvn" / "data" / "variables",
    DATA_ROOT / "assets" / "_meta",
    DATA_ROOT / "assets" / "characters",
    DATA_ROOT / "assets" / "backgrounds",
    DATA_ROOT / "assets" / "music",
    DATA_ROOT / "assets" / "voices",
)


def ensure_dirs() -> None:
    """Create the directory scaffold expected by the Studio shell."""
    for directory in DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def apply_schema(db_path: Path) -> set[str]:
    """Apply v0.6 schema migrations and return the set of tables present."""
    manager = DBManager(db_path)
    manager.ensure_schema()
    return manager.existing_tables()


def rebuild(db_path: Path) -> set[str]:
    """Rebuild the directory scaffold and database schema."""
    ensure_dirs()
    return apply_schema(db_path)


def ensure_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Maintain compatibility with older callers expecting this helper."""
    apply_schema(db_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild phase-06 directories and database."
    )
    parser.add_argument(
        "--recreate-all",
        action="store_true",
        help="Create directories and ensure the v0.6 schema exists.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (defaults to {DEFAULT_DB_PATH}).",
    )
    args = parser.parse_args()

    if not args.recreate_all:
        parser.print_help()
        return

    tables = rebuild(args.db_path.expanduser())
    print(f"[v0.6] ✅ Recreated folders and ensured DB at: {args.db_path}")
    print(f"[v0.6] Found {len(tables)} tables: {', '.join(sorted(tables))}")


if __name__ == "__main__":
    main()
