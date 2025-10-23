from __future__ import annotations

"""
Run SQLite `PRAGMA integrity_check` against the ComfyVN database.
"""

import argparse
import sqlite3
from pathlib import Path
from typing import Sequence

from comfyvn.core.db_manager import DEFAULT_DB_PATH
from comfyvn.db import ensure_schema


def check_integrity(db_path: Path | str) -> str:
    path = Path(db_path).expanduser()
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    return str(row[0] if row else "")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run PRAGMA integrity_check on the ComfyVN database."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH}).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = check_integrity(args.db_path)
    print(f"{args.db_path}: integrity_check => {result}")
    return 0 if result.lower() == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
