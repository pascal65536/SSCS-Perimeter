from datetime import timedelta
from statistics import median
from collections import defaultdict
from analytics.detectors.base import make_alert
from analytics.events import ev_time


def detect_sscs_002(events, burst_count=3, window_days=7, interval_ratio=0.25):
    by_pkg = defaultdict(list)
    for ev in events:
        if ev.get("event", {}).get("action") == "package.release":
            by_pkg[(ev.get("package") or {}).get("name")].append(ev)

    alerts = []
    win = timedelta(days=window_days)
    for pkg, rels in by_pkg.items():
        rels.sort(key=ev_time)
        for i, ev in enumerate(rels):
            history = rels[:i]
            if len(history) < burst_count:
                continue
            t = ev_time(ev)
            recent = [r for r in history if t - ev_time(r) <= win]
            if len(recent) + 1 < burst_count:
                continue
            intervals = [
                (ev_time(b) - ev_time(a)).total_seconds()
                for a, b in zip(history, history[1:])
            ]
            med = median(intervals) if intervals else float("inf")
            cur = (t - ev_time(history[-1])).total_seconds()
            if med and cur <= interval_ratio * med:
                alerts.append(
                    make_alert(
                        "SSCS-002",
                        ev,
                        {
                            "recent_releases": len(recent) + 1,
                            "median_interval_s": med,
                            "current_interval_s": cur,
                            "ratio": cur / med,
                        },
                    )
                )
    return alerts
