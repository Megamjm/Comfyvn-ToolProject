from PySide6.QtGui import QAction


def pick_mood(tags: list):
    mood = "calm" if "sad" in (t.lower() for t in (tags or [])) else "uplift"
    return {"mood": mood, "bpm": 90 if mood == "calm" else 118}
