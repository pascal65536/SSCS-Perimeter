from collections import defaultdict
from analytics.detectors.base import make_alert
from analytics.events import ev_time


def _login_of(ev):
    act = ev.get("event", {}).get("action")
    if act == "user.profile_snapshot":
        return (ev.get("user") or {}).get("name")
    return (ev.get("package") or {}).get("author")


def _package_of(ev):
    return (ev.get("package") or {}).get("name")


def detect_sscs_006(events, min_packages=3, max_followers=5, require_profile=True):
    by_login = defaultdict(set)
    profiles = defaultdict(list)
    alerts = []

    for ev in events:
        t = ev_time(ev)
        act = ev.get("event", {}).get("action")
        login = _login_of(ev)
        name = _package_of(ev)

        if act == "user.profile_snapshot":
            prof = (ev.get("sscs") or {}).get("user") or {}
            if login and "followers" in prof:
                profiles[login].append((t, prof["followers"]))
            continue

        if act == "package.created" and login and name:
            pkgs_before = set(by_login[login])
            if len(pkgs_before) >= min_packages - 1:
                pit_profiles = [(ts, f) for ts, f in profiles[login] if ts <= t]
                if not pit_profiles:
                    if not require_profile:
                        alerts.append(
                            make_alert(
                                "SSCS-006",
                                ev,
                                {
                                    "login": login,
                                    "packages": sorted(pkgs_before | {name}),
                                    "profile_unavailable": True,
                                },
                            )
                        )
                else:
                    _, followers = pit_profiles[-1]
                    if followers <= max_followers:
                        alerts.append(
                            make_alert(
                                "SSCS-006",
                                ev,
                                {
                                    "login": login,
                                    "packages": sorted(pkgs_before | {name}),
                                    "followers": followers,
                                },
                            )
                        )

        if act in ("package.created", "package.release") and login and name:
            by_login[login].add(name)

    return alerts
