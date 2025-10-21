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

        if not isinstance(data, list):
            raise ValueError("JSON transcript must be a list or contain 'lines'.")

        lines: List[Dict[str, str]] = []
        for entry in data:
            if not isinstance(entry, dict):
                raise ValueError(
                    "Transcript entries must be objects with speaker/text fields."
                )
            speaker = str(entry.get("speaker") or "Narrator")
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            lines.append({"speaker": speaker, "text": text})
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
