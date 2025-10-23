from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from comfyvn.config import runtime_paths
from comfyvn.config.baseurl_authority import current_authority

logger = logging.getLogger(__name__)


def _default_config() -> Dict[str, Any]:
    authority = current_authority()
    return {
        "host": authority.base_url,
        "theme": "system",
        "layout": {},
    }


@dataclass
class StudioConfig:
    path: Path = field(default_factory=lambda: runtime_paths.config_dir("studio.json"))
    data: Dict[str, Any] = field(default_factory=_default_config)

    def load(self) -> Dict[str, Any]:
        try:
            if self.path.exists():
                content = self.path.read_text(encoding="utf-8")
                payload = json.loads(content)
                if isinstance(payload, dict):
                    self.data.update(payload)
        except json.JSONDecodeError as exc:
            logger.warning("Unable to parse studio config %s: %s", self.path, exc)
        except Exception as exc:
            logger.debug("Studio config load failed: %s", exc)
        return dict(self.data)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.data, indent=2, sort_keys=True)
            self.path.write_text(payload, encoding="utf-8")
        except Exception as exc:
            logger.error("Unable to persist studio config %s: %s", self.path, exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def update(self, **updates: Any) -> None:
        self.data.update(updates)
        self.save()


__all__ = ["StudioConfig"]
