from collections import defaultdict
from analytics.detectors.base import make_alert
from analytics.events import ev_time


def detect_sscs_005(events, night_hours=(0, 1, 2, 3, 4, 5, 6, 23), warmup=10):
    commits_by_author = defaultdict(list)
    for ev in events:
        if ev.get("event", {}).get("action") == "repo.commit":
            login = (ev.get("user") or {}).get("name")
            if login:
                commits_by_author[login].append(ev)

    alerts = []
    night = set(night_hours)
    for login, commits in commits_by_author.items():
        commits.sort(key=ev_time)
        for i, ev in enumerate(commits):
            author_history = commits[:i]
            if len(author_history) < warmup:
                continue
            t = ev_time(ev)
            if t.hour not in night:
                continue
            author_hours = {ev_time(h).hour for h in author_history}
            if t.hour not in author_hours:
                alerts.append(
                    make_alert(
                        "SSCS-005",
                        ev,
                        {
                            "author": login,
                            "hour": t.hour,
                            "author_hours": sorted(author_hours),
                            "warmup": warmup,
                        },
                    )
                )
    return alerts
