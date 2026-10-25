import json, sys

sys.path.insert(0, ".")
from datetime import datetime, timezone
from analytics.events import valid_events
from analytics.detectors.sscs_001 import detect_sscs_001, levenshtein
from analytics.detectors.sscs_002 import detect_sscs_002
from analytics.detectors.sscs_005 import detect_sscs_005
from analytics.detectors.sscs_006 import detect_sscs_006
from analytics.detectors.dedup import deduplicate
from analytics.scoring import score_alerts_per_package, composite_score, severity
from analytics.eval.metrics import (
    confusion,
    detection_latency,
    alerts_per_1000_pkg_weeks,
)

raw = [
    json.loads(l)
    for l in open("tests/fixtures/reference.jsonl", encoding="utf-8")
    if l.strip()
]
events, skipped = valid_events(raw)
assert len(events) == 21 and len(skipped) == 1 and "broken-ts" in skipped, (
    len(events),
    skipped,
)
print(f"[1] valid_events={len(events)} skipped={skipped}  OK")

refs = [
    e["package"]["name"]
    for e in events
    if e.get("sscs", {}).get("reference") and e.get("package", {}).get("name")
]
bad = [
    (a, b) for i, a in enumerate(refs) for b in refs[i + 1 :] if levenshtein(a, b) <= 2
]
assert not bad, bad
print(f"[2] pairwise reference distances > 2 ({len(refs)} names)  OK")

alerts = (
    detect_sscs_001(events, refs)
    + detect_sscs_002(events, burst_count=3)
    + detect_sscs_005(events)
    + detect_sscs_006(events)
)
alerts = deduplicate(alerts)
s1 = [a for a in alerts if a.rule_id == "SSCS-001"]
s2 = [a for a in alerts if a.rule_id == "SSCS-002"]
s6 = [a for a in alerts if a.rule_id == "SSCS-006"]
assert {a.package for a in s1} == {"reqeusts"} and all(
    h["name"] == "requests" for a in s1 for h in a.evidence["hits"]
)
assert (
    len(s2) == 1
    and s2[0].package == "burst-pkg"
    and s2[0].evidence["recent_releases"] == 3
)
assert len(s6) == 1 and s6[0].package == "junk-b" and s6[0].evidence["followers"] == 2
assert s6[0].evidence["packages"] == ["burst-pkg", "junk-a", "junk-b"]
print(f"[3] alerts: SSCS-001={len(s1)} SSCS-002={len(s2)} SSCS-006={len(s6)}  OK")

per_pkg = score_alerts_per_package(alerts)
high = {x["package"] for x in per_pkg if x["severity"] in ("high", "critical")}
assert high == {"junk-b", "reqeusts"}, high
burst = next(x for x in per_pkg if x["package"] == "burst-pkg")
assert burst["severity"] == "medium" and burst["rules"] == ["SSCS-002"]
jb = next(x for x in per_pkg if x["package"] == "junk-b")
rq = next(x for x in per_pkg if x["package"] == "reqeusts")
print(
    f"[4] junk-b={jb['severity']}({jb['score']:.3f}) reqeusts={rq['severity']}({rq['score']:.3f}) burst-pkg={burst['severity']}({burst['score']:.3f})  OK"
)

MALICIOUS = {"burst-pkg", "junk-b", "reqeusts"}
RULE_TH = {"SSCS-001": "high", "SSCS-002": "medium", "SSCS-006": "high"}
rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
fired = {
    x["package"]: any(
        rank[x["severity"]] >= rank[RULE_TH[r]] for r in RULE_TH if r in x["rules"]
    )
    for x in per_pkg
}
tp = sum(1 for p in MALICIOUS if fired.get(p))
fn = sum(1 for p in MALICIOUS if not fired.get(p))
fp = sum(1 for p, f in fired.items() if f and p not in MALICIOUS)
assert (tp, fn, fp) == (3, 0, 0), (tp, fn, fp)
m = confusion(
    {p: {"malicious": p in MALICIOUS} for p in fired},
    [{"package": x["package"], "severity": x["severity"]} for x in per_pkg],
    min_severity="medium",
)
assert m["precision"] == 1.0 and m["recall"] == 1.0, m
lat = detection_latency(
    datetime(2024, 2, 20, tzinfo=timezone.utc),
    [a for a in alerts if a.package == "junk-b"],
)
assert lat is not None and lat >= 0
apw = alerts_per_1000_pkg_weeks(len(alerts), package_weeks=16)
print(
    f"[5] confusion(tp,fn,fp)=({tp},{fn},{fp}) precision/recall=1.0 latency(junk-b)={lat}d alerts/1000pw={apw:.1f}  OK"
)


def _ev(ts, action, pkg=None, login=None, **extra):
    d = {"@timestamp": ts, "event": {"action": action}}
    if pkg:
        d["package"] = {"name": pkg, **({"author": login} if login else {})}
    if login:
        d.setdefault("user", {})["name"] = login
    d.setdefault("sscs", {}).update(extra.pop("sscs", {}))
    d.update(extra)
    return d


def _prep(evs):
    c, _ = valid_events(evs)
    return c


evs = _prep(
    [
        _ev("2024-01-01T00:00:00Z", "package.created", "a", "u"),
        _ev(
            "2024-01-02T00:00:00Z",
            "user.profile_snapshot",
            login="u",
            sscs={"user": {"followers": 2}},
        ),
        _ev("2024-01-03T00:00:00Z", "package.created", "b", "u"),
        _ev("2024-01-04T00:00:00Z", "package.created", "c", "u"),
    ]
)
a = detect_sscs_006(evs, require_profile=True)
assert len(a) == 1 and a[0].package == "c" and a[0].evidence["followers"] == 2
print("[6] N1: profile without package indexed, followers used  OK")

evs = _prep(
    [
        _ev("2024-01-01T00:00:00Z", "package.created", "burst-pkg", "m"),
        _ev(
            "2024-01-02T00:00:00Z",
            "user.profile_snapshot",
            login="m",
            sscs={"user": {"followers": 2}},
        ),
        _ev("2024-01-03T00:00:00Z", "package.created", "j1", "m"),
        _ev("2024-01-04T00:00:00Z", "package.created", "j2", "m"),
        _ev("2024-01-05T00:00:00Z", "package.created", "j3", "m"),
    ]
)
a = detect_sscs_006(evs)
assert "j2" in {x.package for x in a} and "j1" not in {x.package for x in a}
print("[7] PIT: future packages not visible at evaluation time  OK")

evs = _prep(
    [_ev(f"2024-01-{d:02d}T00:00:00Z", "package.release", "p", "m") for d in (1, 31)]
    + [
        _ev("2024-03-01T00:00:00Z", "package.release", "p", "m"),
        _ev("2024-03-02T06:00:00Z", "package.release", "p", "m"),
        _ev("2024-03-02T18:00:00Z", "package.release", "p", "m"),
    ]
)
a = detect_sscs_002(evs, burst_count=3)
assert len(a) == 1, [x.evidence for x in a]
print("[8] SSCS-002 fires exactly once  OK")

evs = _prep(
    [_ev(f"2024-01-0{i}T00:00:00Z", "package.created", f"p{i}", "u") for i in (1, 2, 3)]
)
assert detect_sscs_006(evs, require_profile=True) == []
assert len(detect_sscs_006(evs, require_profile=False)) == 1
print("[9] require_profile True/False semantics  OK")

evs = _prep(
    [
        _ev(f"2024-01-{d:02d}T12:00:00Z", "repo.commit", login="alice")
        for d in range(1, 11)
    ]
    + [_ev("2024-02-01T02:00:00Z", "repo.commit", login="bob")]
)
assert detect_sscs_005(evs) == []
evs = _prep(
    [
        _ev(f"2024-01-{d:02d}T12:00:00Z", "repo.commit", login="alice")
        for d in range(1, 11)
    ]
    + [_ev("2024-02-01T02:00:00Z", "repo.commit", login="alice")]
)
assert len(detect_sscs_005(evs)) == 1
print("[10] SSCS-005 warm-up by author  OK")

print()
print("ALL ORCHESTRATOR CHECKS PASSED")
