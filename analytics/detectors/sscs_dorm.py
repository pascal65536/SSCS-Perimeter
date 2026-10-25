from collections import defaultdict
from datetime import timedelta

from analytics.detectors.base import make_alert
from analytics.events import ev_time


def detect_sscs_dorm(events, dormant_days=180, min_history=2):
    """Исследовательский аналог SIEM-правила пробуждения спящего пакета."""
    releases = defaultdict(list)
    for event in events:
        if event.get("event", {}).get("action") == "package.release":
            name = (event.get("package") or {}).get("name")
            if name:
                releases[name].append(event)
    alerts = []
    for package, items in releases.items():
        items.sort(key=ev_time)
        for index in range(min_history, len(items)):
            previous, current = items[index - 1], items[index]
            gap = ev_time(current) - ev_time(previous)
            if gap >= timedelta(days=dormant_days):
                alerts.append(make_alert("SSCS-DORM", current, {
                    "package": package,
                    "dormant_days": gap.days,
                    "history_count": index,
                    "previous_release_at": ev_time(previous).isoformat(),
                }))
    return alerts
