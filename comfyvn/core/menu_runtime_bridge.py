from __future__ import annotations

import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtGui import QAction


@dataclass
class MenuItem:
    label: str
    handler: Optional[str] = None
    section: str = "View"
    separator_before: bool = False
    order: Optional[int] = None
    callback: Optional[Callable[["MainWindow"], None]] = None


class MenuRegistry:
    def __init__(self):
        self.items: List[MenuItem] = []

    def add(
        self,
        label: str,
        handler: Optional[str] = None,
        section: str = "View",
        separator_before: bool = False,
        order: Optional[int] = None,
        callback: Optional[Callable[["MainWindow"], None]] = None,
    ):
        if handler is None and callback is None:
            raise ValueError("Menu items require a handler name or callback")
        self.items.append(
            MenuItem(label, handler, section, separator_before, order, callback)
        )

    def by_section(self) -> Dict[str, List[MenuItem]]:
        out: Dict[str, List[MenuItem]] = {}
        for it in self.items:
            out.setdefault(it.section, []).append(it)
        return out

    def clear(self):
        self.items.clear()


menu_registry = MenuRegistry()


def _load_py_module(mod_path: Path, module_name: Optional[str] = None):
    name = module_name or mod_path.stem
    spec = importlib.util.spec_from_file_location(name, mod_path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def reload_from_extensions(
    registry: MenuRegistry,
    base_folder: Path = Path("extensions"),
    *,
    clear: bool = True,
    metadata: Optional[List["ExtensionMetadata"]] = None,
):
    """Load python extension entrypoints that declare `register(menu_registry)`."""
    from comfyvn.core.extensions_discovery import \
        ExtensionMetadata  # local import to avoid cycle

    if clear:
        registry.clear()
    if metadata is None:
        if not base_folder.exists():
            return
        for py in sorted(base_folder.rglob("*.py")):
            _load_extension_module(registry, py, module_name=None)
        return

    for meta in metadata:
        if not meta.compatible:
            print(
                f"[Extensions] Skipping {meta.id}: incompatible — {', '.join(meta.errors) if meta.errors else 'see manifest'}"
            )
            continue
        if meta.entrypoint and meta.entrypoint.exists():
            _load_extension_module(
                registry, meta.entrypoint, module_name=f"comfyvn_ext_{meta.id}"
            )
        elif meta.path.is_file():
            _load_extension_module(
                registry, meta.path, module_name=f"comfyvn_ext_{meta.id}"
            )
        else:
            print(f"[Extensions] {meta.id} has no valid entrypoint; skipped")


def _load_extension_module(
    registry: MenuRegistry, path: Path, module_name: Optional[str]
) -> None:
    try:
        mod = _load_py_module(path, module_name=module_name)
        if not mod:
            return
        fn = getattr(mod, "register", None)
        if callable(fn):
            try:
                sig = inspect.signature(fn)
                if len(sig.parameters) == 0:
                    fn()
                else:
                    fn(registry)
            except (ValueError, TypeError):
                fn(registry)
    except Exception as exc:
        print(f"[Extensions] Failed to load {path}: {exc}")
