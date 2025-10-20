from PySide6.QtGui import QAction
import logging
logger = logging.getLogger(__name__)
# comfyvn/server/core/manager_loader.py
# 🧩 Central Manager Loader — audio, lora, playground, persona, etc.

import os


def load_managers():
    """Initialize all ComfyVN core managers safely."""
    from comfyvn.core.mode_manager import ModeManager
    from comfyvn.core.event_bus import EventBus
    from comfyvn.core.job_manager import JobManager
    from comfyvn.core.st_sync_manager import STSyncManager
    from comfyvn.assets.audio_manager import AudioManager
    from comfyvn.assets.lora_manager import LoRAManager
    from comfyvn.assets.playground_manager import PlaygroundManager
    from comfyvn.assets.persona_manager import PersonaManager
    from comfyvn.assets.npc_manager import NPCManager
    from comfyvn.assets.export_manager import ExportManager
    from comfyvn.assets.cache_manager import CacheManager
    from comfyvn.assets.model_discovery import safe_mode_enabled

    managers = {}
    managers["audio_manager"] = AudioManager()
    managers["lora_manager"] = LoRAManager()
    managers["playground"] = PlaygroundManager()
    managers["persona"] = PersonaManager()
    managers["npc"] = NPCManager()
    managers["mode_manager"] = ModeManager()
    managers["event_bus"] = EventBus()
    managers["job_manager"] = JobManager(event_bus=managers["event_bus"])
    managers["st_sync"] = STSyncManager(
        base_url=os.getenv("SILLYTAVERN_URL", "http://127.0.0.1:8000")
    )
    managers["export_manager"] = ExportManager()
    managers["cache_manager"] = CacheManager()
    managers["safe_mode_enabled"] = safe_mode_enabled
    return managers