#!/usr/bin/env python3
# tools/worlds/doctor_worlds.py
# [ComfyVN Architect | Codex implementation script]
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORLDS = ROOT / "data" / "worlds"


def main():
    problems = []
    for world_id in ["grayshore", "veiled_age", "throne_of_echoes"]:
        base = WORLDS / world_id
        if not (base / "world.yaml").exists():
            problems.append(f"{world_id}: missing world.yaml")
        if not (base / "lore" / "summary.md").exists():
            problems.append(f"{world_id}: missing lore/summary.md")
        if not (base / "timeline" / "epochs.json").exists():
            problems.append(f"{world_id}: missing timeline/epochs.json")
    if problems:
        print("❌ Issues:\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("✅ Worlds look good.")


if __name__ == "__main__":
    main()
