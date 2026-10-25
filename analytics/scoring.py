from analytics.config import DEFAULT_WEIGHTS, SEV_BOUNDS


def composite_score(rule_ids, weights=None):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    prod = 1.0
    for r in rule_ids:
        prod *= 1.0 - w[r]
    return 1.0 - prod


def severity(score, distinct_rules=1):
    # Critical требует одновременно score>=0.9 и >=3 разнородных правил (ТЗ 5.4).
    if score >= SEV_BOUNDS["critical"] and distinct_rules >= 3:
        return "critical"
    if score >= SEV_BOUNDS["high"]:
        return "high"
    if score >= SEV_BOUNDS["medium"]:
        return "medium"
    return "low"


def score_alerts_per_package(alerts, weights=None):
    by_pkg = {}
    for a in alerts:
        by_pkg.setdefault(a.package, []).append(a)
    out = []
    for pkg, lst in by_pkg.items():
        rule_ids = sorted({a.rule_id for a in lst})
        s = composite_score(rule_ids, weights)
        out.append(
            {
                "package": pkg,
                "rules": rule_ids,
                "score": s,
                "severity": severity(s, len(rule_ids)),
                "count": sum(a.count for a in lst),
            }
        )
    return sorted(out, key=lambda x: -x["score"])
