from PySide6.QtGui import QAction
import uuid, datetime
from typing import List, Dict, Optional
from .analyzer import RoleplayAnalyzer
class RoleplayFormatter:
    def __init__(self): self.analyzer=RoleplayAnalyzer()
    def to_scene(self, lines: List[Dict], world: Optional[str]=None, source: Optional[str]=None) -> Dict:
        sid=f"scene_{uuid.uuid4().hex[:8]}"; parts=[{"name":p} for p in self.analyzer.participants(lines)]
        return {"scene_id":sid,"created":datetime.datetime.now().isoformat(),"participants":parts,"lines":lines,"meta":{"import_type":"roleplay_log","source":source or "manual","world_tag":world or "unlinked"}}