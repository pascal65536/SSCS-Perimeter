import json

import pytest

from settings_manager import SettingsError, SettingsManager, default_settings


def test_atomic_save_is_deterministic_and_add_root_idempotent(tmp_path):
    manager = SettingsManager(tmp_path / "settings.json")
    data = default_settings("demo")
    manager.save(data)
    first = manager.path.read_bytes()
    manager.save(data)
    assert manager.path.read_bytes() == first
    manager.add_root("Requests", "2.32.3")
    after = manager.path.read_bytes()
    manager.add_root("requests", "2.32.3")
    assert manager.path.read_bytes() == after
    assert manager.load()["project"]["roots"] == [{"name": "requests", "version": "2.32.3"}]


def test_secret_is_rejected(tmp_path):
    data = default_settings()
    data["siem"]["token"] = "must-not-be-here"
    with pytest.raises(SettingsError, match="Секреты запрещены"):
        SettingsManager(tmp_path / "settings.json").save(data)


def test_dangling_dependency_is_rejected(tmp_path):
    data = default_settings()
    data["perimeter"]["packages"] = [{
        "name": "root", "version": "1", "level": "SELF", "dependencies": ["missing"],
        "perimeter_root": ["demo"], "repo": None,
    }]
    with pytest.raises(SettingsError, match="Неизвестная зависимость"):
        SettingsManager(tmp_path / "settings.json").save(data)
