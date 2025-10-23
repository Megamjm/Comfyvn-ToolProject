#!/usr/bin/env python3
# tools/worlds/build_pd_hero_pack.py
# [ComfyVN Architect | Codex implementation script]
"""
Fetches CC0 myth/legend characters from Wikidata via SPARQL and updates
data/worlds/throne_of_echoes/characters/roster.json. Safe to run anytime.
"""

import json
import random
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "data" / "worlds" / "throne_of_echoes" / "characters"
OUT = WORLD / "roster.json"

SPARQL = """
SELECT ?item ?itemLabel ?cultureLabel ?birth ?death WHERE {
  VALUES ?mythC { wd:Q22988604 wd:Q11190 wd:Q42721 }
  ?item wdt:P31/wdt:P279* ?mythC.
  OPTIONAL { ?item wdt:P172 ?culture. }
  OPTIONAL { ?item wdt:P569 ?birth. }
  OPTIONAL { ?item wdt:P570 ?death. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 300
"""

ROLES = ["Blade", "Bow", "Arcana", "Valor", "Shadow", "Artifice"]


def fetch():
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(
        SPARQL
    )
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def card(binding):
    label = binding["itemLabel"]["value"]
    culture = binding.get("cultureLabel", {}).get("value", "Unknown")
    birth = binding.get("birth", {}).get("value", None)
    death = binding.get("death", {}).get("value", None)
    return {
        "id": label.lower().replace(" ", "_"),
        "name": label,
        "role": random.choice(ROLES),
        "culture": culture,
        "epoch": {"birth": birth, "death": death},
        "aspects": [f"Legendary: {label}", f"Origin: {culture}"],
        "stunts": [],
        "notes": "Facts via Wikidata (CC0). Portraits optional.",
    }


def main():
    WORLD.mkdir(parents=True, exist_ok=True)
    data = fetch()
    seen, out_cards = set(), []
    for binding in data["results"]["bindings"]:
        if "itemLabel" not in binding:
            continue
        card_data = card(binding)
        if card_data["name"] in seen:
            continue
        seen.add(card_data["name"])
        out_cards.append(card_data)

    if OUT.exists():
        try:
            base = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            base = []
    else:
        base = []

    ids = {entry["id"] for entry in base}
    for entry in out_cards:
        if entry["id"] not in ids:
            base.append(entry)
            ids.add(entry["id"])

    OUT.write_text(json.dumps(base[:200], indent=2), encoding="utf-8")
    print(f"✅ Updated roster with {len(base[:200])} entries.")


if __name__ == "__main__":
    main()
