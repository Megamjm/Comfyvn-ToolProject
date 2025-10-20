import json
import os

import pytest


def test_scene_schema_present() -> None:
    schema_path = os.path.join("docs", "scene_bundle.schema.json")
    if not os.path.exists(schema_path):
        pytest.skip("Scene schema not present in repository")
    with open(schema_path, "r", encoding="utf-8") as handle:
        json.load(handle)
