from analytics.detectors.base import make_alert


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def detect_sscs_001(events, reference_names, max_distance=2):
    alerts = []
    for ev in events:
        if ev.get("event", {}).get("action") != "package.created":
            continue
        name = (ev.get("package") or {}).get("name")
        if not name:
            continue
        hits = []
        for ref in reference_names:
            if ref == name:
                continue
            d = levenshtein(name, ref)
            if d <= max_distance:
                hits.append({"name": ref, "distance": d})
        if hits:
            alerts.append(
                make_alert("SSCS-001", ev, {"hits": hits, "max_distance": max_distance})
            )
    return alerts
