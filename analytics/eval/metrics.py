def detection_latency(incident_date, alerts_for_pkg):
    if not alerts_for_pkg:
        return None
    first = min(a.ts for a in alerts_for_pkg if a.ts >= incident_date)
    return (first - incident_date).days


def confusion(labeled, alerts, min_severity="high"):
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    tp = fp = fn = 0
    for pkg, truth in labeled.items():
        fired = any(
            a["package"] == pkg and rank[a["severity"]] >= rank[min_severity]
            for a in alerts
        )
        if truth["malicious"] and fired:
            tp += 1
        elif truth["malicious"]:
            fn += 1
        elif fired:
            fp += 1
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def alerts_per_1000_pkg_weeks(n_alerts, package_weeks):
    return n_alerts / package_weeks * 1000 if package_weeks else 0.0
