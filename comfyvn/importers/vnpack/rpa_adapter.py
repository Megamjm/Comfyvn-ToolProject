"""
Stub adapter for Ren'Py archive (.rpa) packages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from comfyvn.importers.vnpack.base import BaseAdapter


class RpaAdapter(BaseAdapter):
    exts = (".rpa",)

    # TODO: integrate rpatool/renpy unpacker when available in the runtime image.

    def list_contents(self) -> List[Dict[str, object]]:
        return [
            {
                "path": "<rpa:unsupported>",
                "size": 0,
                "compressed": 0,
                "is_dir": False,
                "notes": "RPA archives require external tooling; stub only.",
            }
        ]

    def extract(self, out_dir: Path) -> Iterable[Path]:
        return []
