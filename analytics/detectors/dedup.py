from datetime import timedelta


def deduplicate(alerts, window_days=7):
    win = timedelta(days=window_days)
    groups = {}
    for a in sorted(alerts, key=lambda x: x.ts):
        key = (a.rule_id, a.package, a.repo)
        if key in groups and (a.ts - groups[key].ts) <= win:
            groups[key].count += 1
            continue
        groups[key] = a
    return list(groups.values())
