from __future__ import annotations

import logging
from collections import Counter
import re
from typing import Dict, List

LOGGER = logging.getLogger(__name__)

_PERSONA_HINT_PATTERN = re.compile(r"\(([^)]+)\)|\[([^\]]+)\]")


class RoleplayAnalyzer:
    """Utility helpers for examining parsed roleplay transcripts."""

    def participants(self, lines: List[Dict[str, str]]) -> List[str]:
        """Return participants in order of first appearance."""
        seen: List[str] = []
        for entry in lines:
            speaker = entry.get("speaker") or "Narrator"
            if speaker not in seen:
                seen.append(speaker)
        LOGGER.debug("Detected participants: %s", seen)
        return seen

    def speaker_frequencies(self, lines: List[Dict[str, str]]) -> Dict[str, int]:
        """Count how many utterances each speaker has."""
        counter: Counter[str] = Counter()
        for entry in lines:
            counter[entry.get("speaker") or "Narrator"] += 1
        frequencies = dict(counter)
        LOGGER.debug("Speaker frequencies: %s", frequencies)
        return frequencies

    def persona_hints(self, lines: List[Dict[str, str]]) -> Dict[str, List[str]]:
        """
        Extract lightweight persona hints from inline metadata or text markers.
        """
        hints: Dict[str, List[str]] = {}
        for entry in lines:
            speaker = entry.get("speaker") or "Narrator"
            bucket = hints.setdefault(speaker, [])

            meta = entry.get("meta")
            if isinstance(meta, str):
                cleaned = meta.strip()
                if cleaned and cleaned not in bucket:
                    bucket.append(cleaned)

            text = entry.get("text") or ""
            for match in _PERSONA_HINT_PATTERN.finditer(text):
                snippet = next((group for group in match.groups() if group), "").strip()
                if snippet and snippet not in bucket:
                    bucket.append(snippet)

            # Keep hint lists compact.
            if len(bucket) > 5:
                del bucket[5:]
        LOGGER.debug("Persona hints: %s", hints)
        return hints
