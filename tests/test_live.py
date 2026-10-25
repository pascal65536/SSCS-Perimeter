from collector.live import PerimeterCollector
from settings_manager import default_settings
from spool import DiskSpool


def test_404_semantics_distinguish_github_and_pypi(tmp_path):
    settings = default_settings("app")
    collector = PerimeterCollector(settings, DiskSpool(tmp_path / "spool"), tmp_path / "state.json")
    package = {"name": "requests", "repo": "psf/requests", "perimeter_root": ["app"]}
    pypi = collector._removed(package, "2026-10-25T00:00:00Z")
    github = collector._removed(package, "2026-10-25T00:00:00Z", github=True)
    assert pypi["event"]["action"] == "package.removed"
    assert github["event"]["action"] == "repo.removed"
    assert github["source"]["service"] == "github-api"


def test_incomplete_gateway_result_does_not_ack(tmp_path):
    from tests.test_spool import event
    spool = DiskSpool(tmp_path / "spool")
    spool.enqueue(event(1))
    spool.enqueue(event(2))

    class Incomplete:
        def send(self, events):
            return {"accepted": 1, "duplicates": 0, "errors": 0}

    try:
        spool.deliver(Incomplete(), batch_size=2)
    except RuntimeError as exc:
        assert "ack не выполнен" in str(exc)
    else:
        raise AssertionError("Неполный ответ не должен подтверждаться")
    assert spool.count == 2
