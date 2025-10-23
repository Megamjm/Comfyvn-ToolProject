from __future__ import annotations

import json
import logging
import re
from typing import Dict, Iterable, List

LOGGER = logging.getLogger(__name__)

LINE_PATTERNS = [
    re.compile(r"^(?P<speaker>[^:]+):\s*(?P<text>.+)$"),
    re.compile(r"^(?P<speaker>[^(\[]+?)[\[(](?P<meta>[^)\]]+)[\])]:\s*(?P<text>.+)$"),
]


class RoleplayParser:
    """Parse text or JSON transcripts into roleplay line dictionaries."""

    def parse_text(self, text: str) -> List[Dict[str, str]]:
        """Parse raw log text into structured lines."""
        lines: List[Dict[str, str]] = []
        for raw in self._iter_non_empty(text.splitlines()):
            parsed = self._parse_line(raw)
            lines.append(parsed)
        LOGGER.debug("Parsed %s lines from transcript", len(lines))
        return lines

    def parse_json(self, payload: str) -> List[Dict[str, str]]:
        """Accept JSON array/object transcripts for structured sources."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON payload: {exc}") from exc

        if isinstance(data, dict) and "lines" in data:
            data = data["lines"]

        if isinstance(data, dict) and "messages" in data:
            data = data["messages"]

        if not isinstance(data, list):
            raise ValueError(
                "JSON transcript must be a list, contain 'lines', or contain 'messages'."
            )

        lines: List[Dict[str, str]] = []
        for entry in data:
            parsed = self._parse_json_entry(entry)
            if parsed:
                lines.append(parsed)
        LOGGER.debug("Parsed %s lines from JSON payload", len(lines))
        return lines

    @staticmethod
    def _iter_non_empty(lines: Iterable[str]) -> Iterable[str]:
        for raw in lines:
            chunk = raw.strip()
            if chunk:
                yield chunk

    def _parse_line(self, raw: str) -> Dict[str, str]:
        for pattern in LINE_PATTERNS:
            match = pattern.match(raw)
            if match:
                speaker = match.group("speaker").strip()
                text = match.group("text").strip()
                meta = match.groupdict().get("meta")
                payload = {"speaker": speaker or "Narrator", "text": text}
                if meta:
                    payload["meta"] = meta.strip()
                return payload
        return {"speaker": "Narrator", "text": raw.strip()}

    def _parse_json_entry(self, entry: Dict[str, object]) -> Dict[str, str] | None:
        if not isinstance(entry, dict):
            raise ValueError("Transcript entries must be objects.")

        speaker = entry.get("speaker")
        text = entry.get("text")

        if text is None and isinstance(entry.get("mes"), str):
            text = entry["mes"]

        if speaker is None:
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                speaker = name
        if speaker is None:
            if bool(entry.get("is_user")):
                speaker = "User"
            else:
                speaker = entry.get("character") or entry.get("role") or "Narrator"

        if text is None:
            swipes = entry.get("swipes")
            if isinstance(swipes, list) and swipes:
                text = swipes[0]

        if not isinstance(text, str):
            return None

        cleaned = self._clean_text(text)
        if not cleaned:
            return None

        return {
            "speaker": str(speaker or "Narrator"),
            "text": cleaned,
        }

    @staticmethod
    def _clean_text(text: str) -> str:
        chunk = str(text or "").strip()
        if not chunk:
            return ""
        # Remove common RP markup (leading/trailing *action*). Preserve internal italics.
        if chunk.startswith("*") and chunk.endswith("*") and len(chunk) > 2:
            chunk = chunk.strip("*").strip()
        chunk = chunk.replace("\r\n", "\n")
        chunk = re.sub(r"\n{2,}", "\n\n", chunk)
        return chunk
