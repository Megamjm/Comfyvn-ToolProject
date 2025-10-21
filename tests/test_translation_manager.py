import json
from pathlib import Path

from comfyvn.translation.manager import TranslationManager


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_translation_lookup_with_fallback(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    translations_dir = tmp_path / "i18n"

    _write_json(
        translations_dir / "en.json",
        {"strings": {"ui.greeting": "Hello", "ui.farewell": "Goodbye"}},
    )
    _write_json(translations_dir / "es.json", {"strings": {"ui.farewell": "Adiós"}})

    manager = TranslationManager(
        fallback_language="en",
        config_path=config_path,
        translation_dirs=[translations_dir],
    )

    assert manager.get_active_language() == "en"
    assert manager.t("ui.greeting") == "Hello"

    manager.set_active_language("es")

    assert manager.get_active_language() == "es"
    assert manager.t("ui.farewell") == "Adiós"  # direct hit
    assert (
        manager.t("ui.greeting") == "Hello"
    )  # falls back to English when missing in Spanish

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["i18n"]["active_language"] == "es"
    assert saved["i18n"]["fallback_language"] == "en"


def test_available_languages_discovers_files(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.json"
    translations_dir = tmp_path / "i18n"

    _write_json(translations_dir / "en.json", {"strings": {"ui.title": "Comfy"}})
    _write_json(translations_dir / "vi.json", {"strings": {"ui.title": "Thoải mái"}})

    manager = TranslationManager(
        fallback_language="en",
        config_path=config_path,
        translation_dirs=[translations_dir],
    )

    langs = manager.available_languages()
    assert "en" in langs
    assert "vi" in langs
