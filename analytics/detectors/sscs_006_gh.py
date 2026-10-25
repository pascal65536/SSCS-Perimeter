from collections import defaultdict
from datetime import timedelta
from analytics.detectors.base import make_alert
from analytics.events import ev_time, _parse_ts


def detect_sscs_006_gh(events, max_followers=5, max_account_age_days=730):
    profiles = defaultdict(list)
    for ev in events:
        if ev.get("event", {}).get("action") == "user.profile_snapshot":
            login = (ev.get("user") or {}).get("name")
            u = (ev.get("sscs") or {}).get("user") or {}
            if login and u.get("account_created_at"):
                profiles[login].append((ev_time(ev), u))

    seen = defaultdict(set)
    alerts = []
    for ev in events:
        if ev.get("event", {}).get("action") != "repo.commit":
            continue
        repo = (ev.get("sscs") or {}).get("repo") or "<unknown>"
        login = (ev.get("user") or {}).get("name")
        if not login or login in seen[repo]:
            continue
        seen[repo].add(login)
        t = ev_time(ev)
        pit = [(ts, u) for ts, u in profiles.get(login, []) if ts <= t]
        if not pit:
            continue
        _, u = pit[-1]
        created = _parse_ts(u["account_created_at"])
        young = created is not None and (t - created) <= timedelta(
            days=max_account_age_days
        )
        low = (u.get("followers") or 0) <= max_followers
        if young or low:
            alerts.append(
                make_alert(
                    "SSCS-006",
                    ev,
                    {
                        "login": login,
                        "repo": repo,
                        "followers": u.get("followers"),
                        "account_created_at": u.get("account_created_at"),
                        "first_commit_at": t.isoformat(),
                        "reason": "+".join(
                            r
                            for r, f in (("young", young), ("low_followers", low))
                            if f
                        ),
                    },
                )
            )
    return alerts
