import json, sys
from collections import Counter

sys.path.insert(0, ".")
from analytics.events import valid_events
from analytics.detectors.sscs_004 import detect_sscs_004

raw = [json.loads(l) for l in open("pilot/events_gh.jsonl") if l.strip()]
ev, _ = valid_events(raw)
alerts = detect_sscs_004(ev)  # без deduplicate — raw

print(f"raw-алертов SSCS-004: {len(alerts)}")
by_repo = Counter(a.repo for a in alerts)
print("по репозиториям:", dict(by_repo))

# Структура FP: разложение по механистике
decomp = Counter()
for a in alerts:
    merged = a.evidence.get("merged_by")
    author = a.evidence.get("author")
    if not merged:
        decomp["not_merged"] += 1
    elif author == merged:
        decomp["self_merge"] += 1
    else:
        decomp["merged_by_other"] += 1
print("механистика:", dict(decomp))

TEAM = {
    "glenn-jocher",
    "pderrenger",
    "Laughing-q",
    "Y-T-G",
    "RizwanMunawar",
    "lakshanthad",
    "WangQvQ",
    "dependabot[bot]",
}
ext = [
    a
    for a in alerts
    if a.evidence.get("merged_by")
    and a.evidence.get("author") != a.evidence.get("merged_by")
    and a.evidence.get("author") not in TEAM
]
print(f"merge чужим PR без ревью от ВНЕШНИХ авторов: {len(ext)}")
for a in ext[:10]:
    print(
        f"  {a.repo} #{a.evidence['pr_number']} author={a.evidence['author']} "
        f"merged_by={a.evidence['merged_by']} {a.ts.date()}"
    )
