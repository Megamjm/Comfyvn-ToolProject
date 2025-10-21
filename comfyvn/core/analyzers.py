import re

from PySide6.QtGui import QAction


def simple_character_scan(text: str):
    chars = {}
    for m in re.finditer(r"\b([A-Z][a-zA-Z]+)\b", text or ""):
        name = m.group(1)
        if len(name) < 2 or name.lower() in {"the", "and", "You"}:
            continue
        chars[name] = chars.get(name, 0) + 1
    traits = []
    for m in re.finditer(r"\b(\w+)\s+(dress|shirt|hair|eyes)\b", text or "", re.I):
        traits.append({"attr": m.group(2).lower(), "val": m.group(1).lower()})
    return {
        "characters": sorted(chars.items(), key=lambda x: -x[1])[:20],
        "traits": traits,
    }


def continuity_check(states: list):
    issues = []
    ages = {}
    for s in states or []:
        name = s.get("name")
        age = s.get("age")
        if name is None:
            continue
        if name in ages and age is not None and ages[name] != age:
            issues.append(
                {"type": "age_mismatch", "name": name, "was": ages[name], "now": age}
            )
        if age is not None:
            ages[name] = age
    return {"ok": len(issues) == 0, "issues": issues}
