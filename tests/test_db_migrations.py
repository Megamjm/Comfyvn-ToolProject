from __future__ import annotations

import sqlite3
from pathlib import Path

from comfyvn.db import MigrationRunner, load_default_migrations


def test_sql_migrations_idempotent(tmp_path: Path):
    db_path = tmp_path / "migrations.db"
    migrations = load_default_migrations()
    runner = MigrationRunner(db_path, migrations)

    executed = runner.apply_all()
    assert executed == ("v0.6",)

    repeated = runner.apply_all()
    assert repeated == ()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "scenes" in tables
        assert "settings" in tables
        result = conn.execute("PRAGMA integrity_check;").fetchone()

    assert result is not None
    assert str(result[0]).lower() == "ok"
