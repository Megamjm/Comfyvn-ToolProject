from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

__all__ = ["get_scenario_schema", "SCENARIO_SCHEMA_PATH"]

SCHEMA_ROOT = Path(__file__).resolve().parent
SCENARIO_SCHEMA_PATH = SCHEMA_ROOT / "scenario_schema.json"


@lru_cache(maxsize=1)
def get_scenario_schema() -> Dict[str, Any]:
    """
    Load and cache the canonical scenario JSON schema.
    """
    return json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))
