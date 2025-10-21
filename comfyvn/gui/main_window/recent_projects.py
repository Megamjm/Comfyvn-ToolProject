import json
import logging
from typing import List

from comfyvn.config.runtime_paths import recent_projects_file

RECENT_PATH = recent_projects_file()
logger = logging.getLogger(__name__)


def load_recent(max_items: int = 10) -> List[str]:
    if not RECENT_PATH.exists():
        return []
    try:
        data = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data[:max_items]]
    except json.JSONDecodeError as exc:
        logger.warning("Failed to read recent projects: %s", exc)
    return []


def touch_recent(project_path: str) -> None:
    recents = load_recent()
    path_str = str(project_path)
    if path_str in recents:
        recents.remove(path_str)
    recents.insert(0, path_str)
    RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECENT_PATH.write_text(json.dumps(recents[:20], indent=2), encoding="utf-8")
    logger.info("Recent projects updated: %s", path_str)
