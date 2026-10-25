from analytics.detectors.base import make_alert

def detect_sscs_004(events):
    alerts = []
    for ev in events:
        if ev.get("event", {}).get("action") != "repo.pull_request":
            continue
        pr = (ev.get("sscs") or {}).get("pr") or {}
        if not pr.get("merged_at"):
            continue
        if pr.get("review_count", 0) != 0:
            continue
        author = (ev.get("user") or {}).get("name")
        if author and pr.get("merged_by") and author == pr.get("merged_by"):
            continue  # self-merge мейнтейнера — не аномалия
        alerts.append(make_alert("SSCS-004", ev, {
            "author": author, "merged_by": pr.get("merged_by"),
            "pr_number": pr.get("number"), "review_count": 0,
        }))
    return alerts
