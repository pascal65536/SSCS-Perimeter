from datetime import datetime, timezone

from analytics.detectors.base import Alert
from analytics.detectors.sscs_chain import detect_sscs_chain
from analytics.detectors.sscs_dorm import detect_sscs_dorm
from analytics.events import valid_events
from analytics.scoring import score_alerts_per_package, severity


def alert(rule):
    return Alert(rule, "pkg", None, datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_critical_requires_score_and_three_distinct_rules():
    assert severity(0.95, 2) == "high"
    assert severity(0.95, 3) == "critical"
    scored = score_alerts_per_package([alert("SSCS-003"), alert("SSCS-004"), alert("SSCS-006")])[0]
    assert scored["score"] >= 0.9 and scored["severity"] == "critical"


def ts(value):
    return {"@timestamp": value, "event": {"action": "package.release"}, "package": {"name": "ctx"}, "sscs": {}}


def test_dorm_requires_history_and_180_days():
    raw = [ts("2022-01-01T00:00:00Z"), ts("2022-02-01T00:00:00Z"), ts("2023-01-01T00:00:00Z")]
    events, _ = valid_events(raw)
    alerts = detect_sscs_dorm(events)
    assert len(alerts) == 1 and alerts[0].evidence["dormant_days"] == 334


def test_chain_correlates_pr_and_release():
    raw = [{
        "@timestamp": "2024-01-10T00:00:00Z", "event": {"action": "repo.pull_request"},
        "package": {"name": "pkg"}, "user": {"name": "mallory"},
        "sscs": {"pr": {"number": 7, "merged_at": "2024-01-10T01:00:00Z", "merged_by": "owner", "review_count": 0, "touches_critical": True, "author_account_created_at": "2024-01-01T00:00:00Z"}},
    }, {
        "@timestamp": "2024-01-20T00:00:00Z", "event": {"action": "package.release"}, "package": {"name": "pkg"}, "sscs": {},
    }]
    events, _ = valid_events(raw)
    alerts = detect_sscs_chain(events)
    assert len(alerts) == 1 and alerts[0].evidence["release_after_days"] == 10
