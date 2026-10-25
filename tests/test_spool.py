import json
from datetime import datetime, timezone

from spool import DiskSpool

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


def event(number=0):
    return {
        "@timestamp": "2026-10-24T10:00:00Z",
        "event": {"id": f"event-{number}", "kind": "event", "category": "package", "type": "creation", "action": "package.release"},
        "source": {"service": "pypi-api"},
        "package": {"name": "demo"},
        "sscs": {"watchlist": "monitored", "schema_version": "1.0"},
    }


def test_invalid_and_future_events_go_to_dlq(tmp_path):
    spool = DiskSpool(tmp_path, now=lambda: NOW)
    broken = event()
    broken["@timestamp"] = None
    future = event(2)
    future["@timestamp"] = "2027-01-01T00:00:00Z"
    assert not spool.enqueue(broken)
    assert not spool.enqueue(future)
    assert spool.count == 0
    assert len(spool.dlq_path.read_text().splitlines()) == 2


def test_rotation_discards_oldest_and_delivery_ack(tmp_path):
    spool = DiskSpool(tmp_path, max_bytes=1400, now=lambda: NOW)
    for i in range(12):
        assert spool.enqueue(event(i))
    assert 0 < spool.count < 12
    remaining_ids = [e["event"]["id"] for e in spool.peek(100)]
    assert "event-0" not in remaining_ids

    class Gateway:
        def send(self, events):
            return {"accepted": len(events) - 1, "duplicates": 1, "errors": 0}

    before = spool.count
    result = spool.deliver(Gateway(), batch_size=2)
    assert result["accepted"] == 1
    assert spool.count == before - 2
