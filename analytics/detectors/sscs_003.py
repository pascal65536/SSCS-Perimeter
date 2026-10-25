from datetime import timedelta
from analytics.detectors.base import make_alert
from analytics.events import _parse_ts

def detect_sscs_003(events, days=30):
    alerts = []
    for ev in events:
        if ev.get("event", {}).get("action") != "repo.pull_request":
            continue
        pr = (ev.get("sscs") or {}).get("pr") or {}
        first = pr.get("author_first_contrib_at")
        if not first or not pr.get("touches_critical"):
            continue
        first_ts = _parse_ts(first)
        if first_ts is None:
            continue
        if timedelta(0) <= (ev["_ts"] - first_ts) <= timedelta(days=days):
            alerts.append(make_alert("SSCS-003", ev, {
                "author": (ev.get("user") or {}).get("name"),
                "pr_number": pr.get("number"),
                "days_since_first_contrib": (ev["_ts"] - first_ts).days,
                "touches_critical": True,
            }))
    return alerts
