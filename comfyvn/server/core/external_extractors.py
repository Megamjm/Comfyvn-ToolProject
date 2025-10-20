"""
Manage external extraction tools (e.g., arc_unpacker) that assist VN imports.

Tools are declared by the user (we never auto-install or download them) and
stored in ``config/import_tools.json``.  Each tool definition includes a local
filesystem path, supported file extensions, optional notes, and legal
warnings.  The manager exposes registration helpers plus a safe ``invoke``
method for running an extractor in a temporary directory.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)

CONFIG_PATH = Path("config/import_tools.json")


@dataclass
class ExtractorTool:
    name: str
    path: Path
    extensions: List[str] = field(default_factory=list)
    notes: str = ""
    warning: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "extensions": self.extensions,
            "notes": self.notes,
            "warning": self.warning,
        }


class ExternalExtractorManager:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config_path = config_path
        self._tools: Dict[str, ExtractorTool] = {}
        self._load()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.config_path.exists():
            self._tools = {}
            return
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Failed to load import tools config: %s", exc)
            self._tools = {}
            return
        tools: Dict[str, ExtractorTool] = {}
        for name, data in (payload.get("tools") or {}).items():
            if not isinstance(data, dict):
                continue
            path_value = Path(data.get("path") or "")
            tool = ExtractorTool(
                name=name,
                path=path_value,
                extensions=[ext.lower() for ext in (data.get("extensions") or [])],
                notes=str(data.get("notes") or ""),
                warning=str(data.get("warning") or ""),
            )
            tools[name] = tool
        self._tools = tools

    def _save(self) -> None:
        payload = {
            "tools": {name: tool.to_dict() for name, tool in self._tools.items()},
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list_tools(self) -> List[ExtractorTool]:
        return sorted(self._tools.values(), key=lambda t: t.name.lower())

    def register(
        self,
        name: str,
        path: str,
        *,
        extensions: Optional[Iterable[str]] = None,
        notes: str = "",
        warning: str = "",
    ) -> ExtractorTool:
        name = name.strip()
        if not name:
            raise ValueError("tool name required")
        tool_path = Path(path).expanduser()
        tool = ExtractorTool(
            name=name,
            path=tool_path,
            extensions=[ext.lower() for ext in (extensions or [])],
            notes=notes,
            warning=warning,
        )
        self._tools[name] = tool
        self._save()
        LOGGER.info("Registered extractor %s -> %s", name, tool_path)
        return tool

    def unregister(self, name: str) -> bool:
        removed = self._tools.pop(name, None)
        if removed:
            self._save()
            LOGGER.info("Removed extractor %s", name)
            return True
        return False

    def get(self, name: str) -> Optional[ExtractorTool]:
        return self._tools.get(name)

    def resolve_for_extension(self, suffix: str) -> Optional[ExtractorTool]:
        suffix = suffix.lower()
        for tool in self._tools.values():
            if suffix in tool.extensions:
                return tool
        return None

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    def invoke(self, name: str, source: Path, *, output_dir: Path) -> Path:
        tool = self.get(name)
        if not tool:
            raise ValueError(f"extractor '{name}' not registered")
        if not tool.path.exists():
            raise FileNotFoundError(f"extractor path not found: {tool.path}")

        cmd = [str(tool.path), str(source), "-o", str(output_dir)]
        LOGGER.info("Running extractor %s -> %s", name, cmd)
        legal = tool.warning or "Verify extraction is legal in your region before proceeding."
        LOGGER.warning("[Extractor:%s] %s", name, legal)

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            LOGGER.error(
                "Extractor %s failed (exit %s). stdout=%s stderr=%s",
                name,
                result.returncode,
                result.stdout.strip(),
                result.stderr.strip(),
            )
            raise RuntimeError(f"extractor {name} failed (exit {result.returncode})")

        LOGGER.debug("Extractor %s completed: %s", name, output_dir)
        return output_dir


extractor_manager = ExternalExtractorManager()


def ensure_tool_entry(name: str, path: str) -> None:
    """
    Convenience helper used by docs/installers to seed recommended warnings.
    """
    warning = (
        "Use only with content you own or that is legally distributable in your jurisdiction. "
        "Some VN archives are protected by copyright or region restrictions."
    )
    extractor_manager.register(
        name,
        path,
        extensions=[".arc", ".xp3", ".dat", ".pak"],
        notes="External VN archive extractor (arc_unpacker compatible).",
        warning=warning,
    )
