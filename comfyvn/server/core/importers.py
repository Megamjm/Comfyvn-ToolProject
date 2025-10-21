from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PySide6.QtGui import QAction


def _norm_name(name: str) -> str:
    return (name or "").strip()


def _apply_speaker_dict(name: str, sd: Dict[str, str] | None) -> str:
    if not sd:
        return name
    return sd.get(name, sd.get(name.lower(), name))


def _parse_ts(ts) -> float:
    # accept float/epoch, int, or ISO string
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        try:
            return float(ts)
        except Exception:
            return 0.0
    s = str(ts)
    # Slack "1681247056.000200"
    try:
        if s.isdigit() or (s.replace(".", "", 1).isdigit() and s.count(".") <= 1):
            return float(s)
    except Exception:
        pass
    try:
        from datetime import datetime

        from dateutil import parser as dparser  # optional, fallback below

        return dparser.parse(s).timestamp()
    except Exception:
        try:
            from datetime import datetime

            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0


def lines_to_scene(
    scene_id: str,
    title: str,
    lines: List[Dict[str, Any]],
    project_id: str | None = None,
    tags: List[str] | None = None,
) -> Dict[str, Any]:
    sc = {
        "scene_id": scene_id,
        "title": title or scene_id,
        "lines": lines,
        "tags": tags or [],
    }
    if project_id:
        if f"project:{project_id}" not in sc["tags"]:
            sc["tags"].append(f"project:{project_id}")
        sc["project_id"] = project_id
    return sc


def merge_into_scene(
    scene_path: Path, incoming: List[Dict[str, Any]], policy: str = "append"
) -> Dict[str, Any]:
    # policy: append | overwrite | by_timestamp
    if scene_path.exists():
        try:
            sc = json.loads(scene_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            sc = {"scene_id": scene_path.stem, "lines": []}
    else:
        sc = {"scene_id": scene_path.stem, "lines": []}
    base = sc.get("lines") or []
    if policy == "overwrite":
        sc["lines"] = incoming
    elif policy == "by_timestamp":
        # merge by timestamp if provided, else append
        combined = base + incoming
        combined.sort(key=lambda x: x.get("ts") or 0.0)
        sc["lines"] = combined
    else:
        sc["lines"] = base + incoming
    return sc


# ---- Parsers ----
def import_csv(
    text: str, speaker_dict: Dict[str, str] | None = None
) -> List[Dict[str, Any]]:
    out = []
    import io

    f = io.StringIO(text)
    reader = csv.DictReader(f)
    for row in reader:
        speaker = _apply_speaker_dict(
            _norm_name(
                row.get("speaker") or row.get("author") or row.get("name") or ""
            ),
            speaker_dict,
        )
        text = row.get("text") or row.get("content") or row.get("message") or ""
        ts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if text.strip():
            out.append(
                {
                    "speaker": speaker or "",
                    "text": text,
                    "ts": ts,
                    "meta": {"src": "csv"},
                }
            )
    return out


def import_jsonl(
    text: str, speaker_dict: Dict[str, str] | None = None
) -> List[Dict[str, Any]]:
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except Exception:
            continue
        speaker = _apply_speaker_dict(
            _norm_name(
                row.get("speaker") or row.get("author") or row.get("name") or ""
            ),
            speaker_dict,
        )
        text = row.get("text") or row.get("content") or row.get("message") or ""
        ts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if text.strip():
            out.append(
                {
                    "speaker": speaker or "",
                    "text": text,
                    "ts": ts,
                    "meta": {"src": "jsonl"},
                }
            )
    return out


def import_markdown(
    text: str, speaker_dict: Dict[str, str] | None = None
) -> List[Dict[str, Any]]:
    out = []
    # patterns: "- **Name:** text" or "Name: text" or "**Name**: text"
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = (
            re.match(r"[-*]\s*\*\*([^*]+)\*\*\s*:\s*(.+)", s)
            or re.match(r"\*\*([^*]+)\*\*\s*[:-]\s*(.+)", s)
            or re.match(r"([^:]+)\s*:\s*(.+)", s)
        )
        if m:
            speaker = _apply_speaker_dict(_norm_name(m.group(1).strip()), speaker_dict)
            text = m.group(2).strip()
            out.append(
                {
                    "speaker": speaker or "",
                    "text": text,
                    "ts": 0.0,
                    "meta": {"src": "md"},
                }
            )
        else:
            # continuation line
            if out:
                out[-1]["text"] += "\n" + s
    return out


def import_discord_json(
    text: str, speaker_dict: Dict[str, str] | None = None
) -> List[Dict[str, Any]]:
    out = []
    try:
        data = json.loads(text)
    except Exception:
        return out
    # support formats: {"messages":[{"author":{"name":..},"timestamp":..,"content":..}, ...]}
    msgs = (
        data.get("messages") or data.get("Messages") or data.get("messagesList") or []
    )
    if isinstance(msgs, list) and msgs:
        for m in msgs:
            speaker = _apply_speaker_dict(
                _norm_name(
                    (m.get("author") or {}).get("name")
                    if isinstance(m.get("author"), dict)
                    else (m.get("author") or m.get("username") or "")
                ),
                speaker_dict,
            )
            text = m.get("content") or m.get("text") or ""
            ts = _parse_ts(m.get("timestamp") or m.get("ts"))
            if text:
                out.append(
                    {
                        "speaker": speaker or "",
                        "text": text,
                        "ts": ts,
                        "meta": {"src": "discord"},
                    }
                )
        return out
    # alternative: list of messages dict
    if isinstance(data, list):
        for m in data:
            speaker = _apply_speaker_dict(
                _norm_name(m.get("author") or m.get("username") or ""), speaker_dict
            )
            text = m.get("content") or m.get("text") or ""
            ts = _parse_ts(m.get("timestamp") or m.get("ts"))
            if text:
                out.append(
                    {
                        "speaker": speaker or "",
                        "text": text,
                        "ts": ts,
                        "meta": {"src": "discord"},
                    }
                )
    return out


def import_slack_json(
    text: str, speaker_dict: Dict[str, str] | None = None
) -> List[Dict[str, Any]]:
    out = []
    try:
        data = json.loads(text)
    except Exception:
        try:
            data = [json.loads(l) for l in text.splitlines() if l.strip()]
        except Exception:
            return out
    msgs = data if isinstance(data, list) else data.get("messages") or []
    for m in msgs:
        u = (
            (m.get("user_profile") or {}).get("display_name")
            or m.get("user")
            or (m.get("username") or "")
        )
        speaker = _apply_speaker_dict(_norm_name(u), speaker_dict)
        text = m.get("text") or ""
        ts = _parse_ts(m.get("ts"))
        if text:
            out.append(
                {
                    "speaker": speaker or "",
                    "text": text,
                    "ts": ts,
                    "meta": {"src": "slack", "channel": m.get("channel")},
                }
            )
    return out


def import_telegram_json(
    text: str, speaker_dict: Dict[str, str] | None = None
) -> List[Dict[str, Any]]:
    out = []
    try:
        data = json.loads(text)
    except Exception:
        return out
    msgs = data.get("messages") or []
    for m in msgs:
        name = m.get("from") or m.get("from_name") or m.get("author") or ""
        speaker = _apply_speaker_dict(_norm_name(name), speaker_dict)
        text = (
            m.get("text")
            if isinstance(m.get("text"), str)
            else (
                "".join(
                    x if isinstance(x, str) else x.get("text", "")
                    for x in (m.get("text") or [])
                )
            )
        )
        ts = _parse_ts(m.get("date") or m.get("timestamp"))
        if text:
            out.append(
                {
                    "speaker": speaker or "",
                    "text": text,
                    "ts": ts,
                    "meta": {"src": "telegram"},
                }
            )
    return out


# ---- Exporters ----
def export_jsonl(lines: List[Dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(
            {
                "speaker": l.get("speaker", ""),
                "text": l.get("text", ""),
                "ts": l.get("ts", 0.0),
            }
        )
        for l in lines
    )


def export_markdown(lines: List[Dict[str, Any]]) -> str:
    buf = []
    for l in lines:
        sp = l.get("speaker") or ""
        tx = (l.get("text") or "").replace("\n", "\n  ")
        buf.append(f"- **{sp}:** {tx}")
    return "\n".join(buf)


def export_csv(lines: List[Dict[str, Any]]) -> str:
    import csv
    import io

    f = io.StringIO()
    w = csv.writer(f)
    w.writerow(["speaker", "text", "ts"])
    for l in lines:
        w.writerow([l.get("speaker", ""), l.get("text", ""), l.get("ts", 0.0)])
    return f.getvalue()
