from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Alert:
    rule_id: str
    package: str
    repo: str | None
    ts: datetime
    evidence: dict = field(default_factory=dict)
    count: int = 1


def make_alert(rule_id, ev, evidence):
    return Alert(
        rule_id=rule_id,
        package=(ev.get("package") or {}).get("name")
        or (ev.get("sscs") or {}).get("repo")
        or "<unknown>",
        repo=(ev.get("sscs") or {}).get("repo"),
        ts=ev["_ts"],
        evidence=evidence,
    )
