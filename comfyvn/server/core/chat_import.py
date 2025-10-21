from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtGui import QAction


@dataclass
class Line:
    idx: int
    speaker: str
    text: str
    ts: float | None = None
    meta: Dict[str, Any] | None = None


NAME_COLON = re.compile(r"^\s*([^:\[]+?)\s*:\s*(.+)$")
TS_NAME_COLON = re.compile(
    r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*([^:]+?)\s*:\s*(.+)$"
)
BRACKET_NAME_COLON = re.compile(r"^\s*\[(.*?)\]\s*([^:]+?)\s*:\s*(.+)$")


def _parse_time_to_epoch(s: str) -> float | None:
    # Accept HH:MM or HH:MM:SS, interpret as today seconds since midnight
    try:
        parts = [int(x) for x in s.split(":")]
        if len(parts) == 2:
            h, m = parts
            sec = h * 3600 + m * 60
        elif len(parts) == 3:
            h, m, s = parts
            sec = h * 3600 + m * 60 + s
        else:
            return None
        base = int(time.time()) // 86400 * 86400  # midnight today (approx)
        return float(base + sec)
    except Exception:
        return None


def parse_text(text: str, fmt: str = "auto") -> List[Line]:
    lines: List[Line] = []
    idx = 0
    for raw in text.splitlines():
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        spk, msg, ts = None, None, None
        m = TS_NAME_COLON.match(raw)
        if m:
            ts = _parse_time_to_epoch(m.group(1))
            spk = m.group(2).strip()
            msg = m.group(3).strip()
        else:
            m2 = BRACKET_NAME_COLON.match(raw)
            if m2:
                ts = None
                spk = m2.group(2).strip()
                msg = m2.group(3).strip()
            else:
                m3 = NAME_COLON.match(raw)
                if m3:
                    spk = m3.group(1).strip()
                    msg = m3.group(2).strip()
                else:
                    # continuation of previous line or narration
                    spk = ""
                    msg = raw.strip()
        lines.append(Line(idx=idx, speaker=spk or "", text=msg or "", ts=ts, meta={}))
        idx += 1
    return lines


def apply_alias_map(lines: List[Line], alias: Dict[str, str]) -> List[Line]:
    if not alias:
        return lines
    norm = {
        k.strip().lower(): v
        for k, v in alias.items()
        if isinstance(k, str) and isinstance(v, str)
    }
    for ln in lines:
        key = (ln.speaker or "").strip().lower()
        if key in norm:
            ln.speaker = norm[key]
    return lines


def assign_by_patterns(lines: List[Line], rules: List[Dict[str, str]]) -> List[Line]:
    """rules: [{"pattern": "^\*.*\*$", "speaker":"NARRATION"}, ...]"""
    comp = []
    for r in rules or []:
        try:
            comp.append(
                (re.compile(r.get("pattern", ""), re.IGNORECASE), r.get("speaker", ""))
            )
        except re.error:
            continue
    for ln in lines:
        for rgx, spk in comp:
            if rgx.search(ln.text):
                ln.speaker = spk
                break
    return lines


def to_scene_dict(name: str, lines: List[Line]) -> Dict[str, Any]:
    return {
        "scene_id": name,
        "created": time.time(),
        "lines": [asdict(ln) for ln in lines],
        "meta": {"imported": True},
    }
