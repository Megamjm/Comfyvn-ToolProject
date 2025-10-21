from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction

from comfyvn.ext.plugins import Plugin


def _concat_job(payload: dict, job_id: str | None):
    a = str(payload.get("a", ""))
    b = str(payload.get("b", ""))
    out = Path("./exports") / f"concat_{(job_id or 'x')[:8]}.txt"
    out.write_text(a + b, encoding="utf-8")
    return {"ok": True, "out": (a + b), "output": str(out)}


plugin = Plugin(
    name="concat",
    jobs={"concat": _concat_job},
    meta={
        "builtin": True,
        "desc": "Concatenate strings a and b into exports/concat_<id>.txt",
    },
)
