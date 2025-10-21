import json
from pathlib import Path
from typing import Iterator, Tuple

import pytest
from fastapi.testclient import TestClient

from comfyvn.server.app import create_app
from comfyvn.translation import manager as translation_manager_module
from comfyvn.translation.manager import TranslationManager


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.fixture
def translation_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Tuple[TranslationManager, Path]]:
    config_path = tmp_path / "comfyvn.json"
    translations_dir = tmp_path / "i18n"

    _write_json(translations_dir / "en.json", {"strings": {"ui.greeting": "Hello"}})
    _write_json(translations_dir / "es.json", {"strings": {"ui.greeting": "Hola"}})

    manager = TranslationManager(
        fallback_language="en",
        config_path=config_path,
        translation_dirs=[translations_dir],
    )

    monkeypatch.setattr(translation_manager_module, "_MANAGER", manager)
    try:
        yield manager, config_path
    finally:
        monkeypatch.setattr(translation_manager_module, "_MANAGER", None)


def test_language_endpoints_and_batch_stub(
    translation_env: Tuple[TranslationManager, Path]
) -> None:
    manager, config_path = translation_env
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/i18n/lang")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] == "en"
        assert data["fallback"] == "en"
        assert "en" in data["available"]

        response = client.post("/api/i18n/lang", json={"lang": "es"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["active"] == "es"
        assert manager.get_active_language() == "es"

        response = client.post("/api/translate/batch", json=["Hola", "Adiós"])
        assert response.status_code == 200
        batch = response.json()
        assert batch["ok"] is True
        assert batch["items"] == [
            {"src": "Hola", "tgt": "Hola"},
            {"src": "Adiós", "tgt": "Adiós"},
        ]

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["i18n"]["active_language"] == "es"
