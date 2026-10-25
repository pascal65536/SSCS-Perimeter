from pathlib import Path

import pytest

from gui.datalayer import BackendError, DemoBackend, LiveBackend
from gui.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parent.parent


def test_embedded_demo_supports_tree_details_and_offline_restrictions(tmp_path):
    backend = DemoBackend(ROOT / "gui" / "demo_snapshot.json")
    assert backend.projects() == ["my-flask-app"]
    assert len(backend.packages("my-flask-app")) == 12
    jinja = backend.node("jinja2")
    assert [p["name"] for p in backend.children("jinja2")] == ["markupsafe"]
    assert backend.details("certifi")["findings"]
    with pytest.raises(BackendError):
        backend.mark_finding("demo-certifi-1", "true_positive")
    output = tmp_path / "snapshot.json"
    backend.export_snapshot(output)
    assert load_snapshot(output)["snapshot_version"] == "1.0"


class FakeOpenSearch:
    def info(self):
        return {"version": {"number": "3.0.0"}}

    def search(self, index, body):
        package = body["query"]["term"]["package.name.keyword"]
        if "scores" in index:
            return {"hits": {"hits": [{"_source": {"risk": {"severity": "high", "score": 0.8, "rules": ["SSCS-003"]}}}]}}
        return {"hits": {"hits": [{"_id": "finding-1", "_source": {"@timestamp": "2026-10-24T00:00:00Z", "rule_id": "SSCS-003", "severity": "high"}}]}}

    def index(self, **kwargs):
        self.feedback = kwargs
        return {"result": "updated"}


def test_live_backend_reads_risk_and_writes_only_feedback():
    from settings_manager import SettingsManager
    settings = SettingsManager(ROOT / "settings.json").load()
    client = FakeOpenSearch()
    backend = LiveBackend(settings, client=client)
    backend.healthcheck()
    assert backend.node("certifi")["risk"]["severity"] == "high"
    assert backend.findings("certifi")[0]["id"] == "finding-1"
    backend.mark_finding("finding-1", "false_positive", "ok")
    assert client.feedback["index"] == "sscs-feedback"
    assert client.feedback["body"]["label"] == "false_positive"
