from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from comfyvn.collab import CollabClientState, CollabHub
from comfyvn.config.feature_flags import load_feature_flags
from comfyvn.server.core.storage import scene_load, scene_save

LOGGER = logging.getLogger(__name__)


def _loader(scene_id: str):
    return asyncio.to_thread(scene_load, scene_id)


def _saver(payload: Dict[str, Any]):
    return asyncio.to_thread(scene_save, payload)


HUB = CollabHub(
    loader=_loader,
    saver=_saver,
    feature_flags=load_feature_flags(),
)


async def get_room(scene_id: str):
    return await HUB.room(scene_id)


async def refresh_feature_flags() -> None:
    HUB.update_feature_flags(load_feature_flags())


__all__ = ["HUB", "get_room", "refresh_feature_flags", "CollabClientState"]
