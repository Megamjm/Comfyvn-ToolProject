from __future__ import annotations

import datetime as dt
import uuid
from typing import Dict, List, Optional

from .analyzer import RoleplayAnalyzer


class RoleplayFormatter:
    """Transform parsed transcript lines into Scene JSON structures."""

    def __init__(self) -> None:
        self.analyzer = RoleplayAnalyzer()

    def to_scene(
        self,
        lines: List[Dict[str, str]],
        *,
        title: Optional[str] = None,
        world: Optional[str] = None,
        source: Optional[str] = None,
        job_ref: Optional[int] = None,
    ) -> Dict[str, object]:
        scene_uid = f"roleplay_{uuid.uuid4().hex[:8]}"
        nodes: List[Dict[str, object]] = []
        previous_node: Optional[Dict[str, object]] = None

        for idx, line in enumerate(lines):
            node_id = f"n{idx:04d}"
            node = {
                "id": node_id,
                "type": "text",
                "content": {
                    "speaker": line.get("speaker") or "Narrator",
                    "text": line.get("text") or "",
                },
                "next": [],
                "meta": {"source_line": idx},
            }
            meta = line.get("meta")
            if meta:
                node["meta"]["raw_meta"] = meta
            nodes.append(node)

            if previous_node is not None:
                previous_node["next"] = [node_id]
            previous_node = node

        participants = self.analyzer.participants(lines)
        timestamp = dt.datetime.utcnow().isoformat() + "Z"

        return {
            "id": scene_uid,
            "title": title or scene_uid,
            "nodes": nodes,
            "meta": {
                "import_type": "roleplay_log",
                "imported_at": timestamp,
                "import_source": source or "roleplay.upload",
                "world_tag": world or "unlinked",
                "participants": participants,
                "speaker_frequencies": self.analyzer.speaker_frequencies(lines),
                "job_ref": job_ref,
            },
        }
