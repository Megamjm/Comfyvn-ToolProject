from __future__ import annotations

import os
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from comfyvn.core.notifier import notifier


class _StubServerBridge(QObject):
    warnings_updated = Signal(list)

    def __init__(self, base: str | None = None):
        super().__init__()
        self.base = base or "http://127.0.0.1:8001"

    def start_polling(self) -> None:  # pragma: no cover - stubbed
        pass

    def stop_polling(self) -> None:  # pragma: no cover - stubbed
        pass

    def ensure_online(self, autostart: bool = True) -> bool:
        return True

    def get_json(self, path: str, default=None, **_: object):
        return default if default is not None else {"ok": True}

    def get_warnings(self):
        return []


class _StubSceneRegistry:
    def __init__(self, project_id: str = "default") -> None:
        self.project_id = project_id
        self._scenes: list[dict] = []

    def list_scenes(self) -> list[dict]:
        return list(self._scenes)

    def upsert_scene(self, title: str, body: str, meta: dict, scene_id: int | None = None) -> int:
        if scene_id is None:
            scene_id = len(self._scenes) + 1
        record = {"id": scene_id, "title": title, "body": body, "meta": meta}
        self._scenes = [r for r in self._scenes if r["id"] != scene_id] + [record]
        return scene_id


class _StubCharacterRegistry:
    def __init__(self, project_id: str = "default") -> None:
        self.project_id = project_id
        self._characters: list[dict] = []

    def list_characters(self) -> list[dict]:
        return list(self._characters)

    def upsert_character(self, name: str, meta: dict | None = None) -> int:
        char_id = len(self._characters) + 1
        record = {"id": char_id, "name": name, "meta": meta or {}}
        self._characters.append(record)
        return char_id

    def append_scene_link(self, *_: object) -> None:  # pragma: no cover - stubbed
        pass


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_main_window_headless_smoke(monkeypatch: pytest.MonkeyPatch, qt_app):
    # Import inside the test so monkeypatching happens before instantiation.
    from comfyvn.gui.main_window import main_window as mw

    monkeypatch.setattr(mw, "ServerBridge", _StubServerBridge)
    monkeypatch.setattr(mw, "SceneRegistry", _StubSceneRegistry)
    monkeypatch.setattr(mw, "CharacterRegistry", _StubCharacterRegistry)

    window = mw.MainWindow()

    try:
        # Seed registry data
        window._scene_registry.upsert_scene("Intro", "{}", {})
        window._character_registry.upsert_character("Alice", {"origin": "demo"})

        window.open_scenes_panel()
        scenes_panel = window._scenes_panel.widget()
        assert scenes_panel.list_widget.count() == 1

        window.open_characters_panel()
        characters_panel = window._characters_panel.widget()
        assert characters_panel.list_widget.count() == 1

        history_len = len(notifier.history)
        window.bridge.warnings_updated.emit([
            {
                "id": "w-test",
                "level": "warn",
                "message": "Headless warning",
                "source": "test",
                "details": {},
                "timestamp": 0.0,
            }
        ])
        assert len(notifier.history) == history_len + 1
        assert notifier.history[-1]["msg"] == "Headless warning"
        assert window._warning_log[-1]["id"] == "w-test"

        # Ensure extension callbacks registered via menu registry.
        callback_items = [item for item in mw.menu_registry.items if item.callback is not None]
        assert callback_items, "Expected at least one callback-driven menu item"
    finally:
        window.close()
