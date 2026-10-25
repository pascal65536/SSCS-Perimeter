import json

from gui.settings_client import SettingsClient
from settings_manager import SettingsManager, default_settings
from siem.gateway import OpenSearchGateway
from siem.provision import content_hash


def test_gui_add_package_writes_through_settings_manager(tmp_path):
    manager = SettingsManager(tmp_path / "settings.json")
    manager.save(default_settings("app"))
    client = SettingsClient(manager.path)
    client.add_package("Requests", "2.32.3")
    client.add_package("requests", "2.32.3")
    saved = manager.load()
    assert saved["project"]["roots"] == [{"name": "requests", "version": "2.32.3"}]
    assert "token" not in manager.path.read_text()


def test_bulk_uses_deterministic_event_id(monkeypatch):
    gateway = OpenSearchGateway("https://example.invalid")
    captured = {}

    def fake(method, path, body, content_type, **kwargs):
        captured["body"] = body.decode()
        return {"items": [{"create": {"status": 201}}, {"create": {"status": 409}}]}

    monkeypatch.setattr(gateway, "_request", fake)
    events = [{"event": {"id": "a"}}, {"event": {"id": "b"}}]
    assert gateway.send(events) == {"accepted": 1, "duplicates": 1, "errors": 0}
    assert '"_id":"a"' in captured["body"] and '"_id":"b"' in captured["body"]


def test_detector_content_hash_is_reproducible():
    assert content_hash() == content_hash()
    assert len(content_hash()) == 64
