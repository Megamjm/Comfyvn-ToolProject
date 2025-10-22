import json
from pathlib import Path
from typing import Iterator, Tuple

import pytest
from fastapi.testclient import TestClient

from comfyvn.server.app import create_app
from comfyvn.translation import manager as translation_manager_module
from comfyvn.translation.manager import TranslationManager
from comfyvn.translation.tm_store import (
    TranslationMemoryStore,
)
from comfyvn.translation.tm_store import (
    set_store as set_tm_store,
)


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
    tm_path = tmp_path / "tm.json"
    store = TranslationMemoryStore(store_path=tm_path)

    monkeypatch.setattr(translation_manager_module, "_MANAGER", manager)
    set_tm_store(store)
    try:
        yield manager, config_path, store
    finally:
        monkeypatch.setattr(translation_manager_module, "_MANAGER", None)
        set_tm_store(None)


def test_language_endpoints_and_batch_stub(
    translation_env: Tuple[TranslationManager, Path, TranslationMemoryStore]
) -> None:
    manager, config_path, _store = translation_env
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
        items = batch["items"]
        assert len(items) == 2
        assert {item["src"] for item in items} == {"Hola", "Adiós"}
        for item in items:
            assert item["lang"] == "es"
            assert item["source"] == "stub"
            assert item["tgt"] == item["src"]
            assert item["reviewed"] is False
            assert item["confidence"] == pytest.approx(0.35)

        second = client.post("/api/translate/batch", json=["Hola"])
        assert second.status_code == 200
        second_payload = second.json()
        assert second_payload["items"][0]["source"] == "tm"
        assert second_payload["items"][0]["tgt"] == "Hola"
        assert second_payload["items"][0]["lang"] == "es"
        assert second_payload["items"][0]["reviewed"] is False

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["i18n"]["active_language"] == "es"


def test_review_queue_approve_and_exports(
    translation_env: Tuple[TranslationManager, Path, TranslationMemoryStore]
) -> None:
    manager, _config_path, _store = translation_env
    app = create_app()

    with TestClient(app) as client:
        payload = client.post("/api/translate/batch", json=["Welcome"])
        assert payload.status_code == 200
        first_item = payload.json()["items"][0]
        assert first_item["source"] == "stub"

        queue = client.get("/api/translate/review/pending")
        assert queue.status_code == 200
        queue_payload = queue.json()
        assert queue_payload["total"] == 1
        entry = queue_payload["items"][0]
        assert entry["lang"] == manager.get_active_language()
        assert entry["reviewed"] is False

        approve = client.post(
            "/api/translate/review/approve",
            json={"id": entry["id"], "translation": "Bienvenido"},
        )
        assert approve.status_code == 200
        approve_payload = approve.json()
        assert approve_payload["entry"]["reviewed"] is True
        assert approve_payload["entry"]["target"] == "Bienvenido"

        queue_after = client.get("/api/translate/review/pending")
        assert queue_after.status_code == 200
        assert queue_after.json()["total"] == 0

        exported = client.get("/api/translate/export/json")
        assert exported.status_code == 200
        exported_payload = exported.json()
        assert exported_payload["ok"] is True
        assert exported_payload["entries"][0]["target"] == "Bienvenido"
        assert exported_payload["entries"][0]["lang"] == manager.get_active_language()

        exported_po = client.get("/api/translate/export/po")
        assert exported_po.status_code == 200
        assert 'msgstr "Bienvenido"' in exported_po.text
