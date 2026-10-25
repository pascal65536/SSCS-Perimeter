from datetime import timedelta

from analytics.detectors.base import make_alert
from analytics.events import _parse_ts, ev_time


def detect_sscs_chain(events, max_account_age_days=30, release_window_days=14):
    """PR молодого аккаунта + critical files + no review + релиз <=14 дней."""
    releases = sorted(
        (e for e in events if e.get("event", {}).get("action") == "package.release"),
        key=ev_time,
    )
    alerts = []
    for pr_event in events:
        if pr_event.get("event", {}).get("action") != "repo.pull_request":
            continue
        package = (pr_event.get("package") or {}).get("name")
        pr = (pr_event.get("sscs") or {}).get("pr") or {}
        created_raw = pr.get("author_account_created_at")
        created = _parse_ts(created_raw) if created_raw else None
        if not package or not created or not pr.get("touches_critical"):
            continue
        if not pr.get("merged_at") or pr.get("review_count", 0) != 0:
            continue
        author = (pr_event.get("user") or {}).get("name")
        if author and author == pr.get("merged_by"):
            continue
        pr_time = ev_time(pr_event)
        if pr_time - created > timedelta(days=max_account_age_days):
            continue
        for release in releases:
            if (release.get("package") or {}).get("name") != package:
                continue
            delta = ev_time(release) - pr_time
            if timedelta(0) <= delta <= timedelta(days=release_window_days):
                alerts.append(make_alert("SSCS-CHAIN", release, {
                    "pr_number": pr.get("number"),
                    "author": author,
                    "account_age_days": (pr_time - created).days,
                    "release_after_days": delta.days,
                    "critical_files": True,
                    "review_count": 0,
                }))
                break
    return alerts
