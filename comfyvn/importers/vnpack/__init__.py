"""
Adapters for handling packaged Visual Novel archives (zip, rpa, etc).

The ``BaseAdapter`` provides a lightweight interface that individual archive
formats implement.  Each adapter is responsible for sniffing whether it can
handle a path, listing contents for dry-run previews, performing safe
extraction into a staging directory, and (optionally) mapping any interesting
scene graph hints for the caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Type

from comfyvn.importers.vnpack.base import BaseAdapter
from comfyvn.importers.vnpack.rpa_adapter import RpaAdapter
from comfyvn.importers.vnpack.zip_adapter import ZipAdapter

ADAPTERS: List[Type[BaseAdapter]] = [ZipAdapter, RpaAdapter]


def find_adapter(path: Path | str) -> Optional[BaseAdapter]:
    candidate = Path(path)
    for adapter_cls in ADAPTERS:
        if adapter_cls.detect(candidate):
            return adapter_cls(candidate)
    return None


__all__ = ["BaseAdapter", "ZipAdapter", "RpaAdapter", "ADAPTERS", "find_adapter"]
