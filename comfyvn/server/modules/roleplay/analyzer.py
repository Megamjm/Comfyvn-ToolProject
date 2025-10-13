# comfyvn/server/modules/roleplay/analyzer.py
# 🤝 Emotion tagging for independent imports

import re


class RoleplayAnalyzer:
    """Heuristic emotion classifier for generic text logs."""

    EMOTION_PATTERNS = {
        "angry": r"\b(angry|mad|furious|rage|yell)\b",
        "sad": r"\b(sad|cry|tears|lonely)\b",
        "happy": r"\b(happy|smile|laugh|grin)\b",
        "romantic": r"\b(love|kiss|heart|dear)\b",
        "surprised": r"\b(wow|gasp|shock|surpris)\b",
    }

    def analyze_line(self, text: str) -> str:
        low = text.lower()
        for emo, pat in self.EMOTION_PATTERNS.items():
            if re.search(pat, low):
                return emo
        if "!" in text:
            return "excited"
        if "..." in text:
            return "uncertain"
        return "neutral"
