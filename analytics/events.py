from datetime import datetime, timezone
from typing import Iterable


def _parse_ts(value):
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def ev_time(ev):
    t = ev.get("_ts")
    if not isinstance(t, datetime):
        raise TypeError(f"event._ts must be datetime: {ev.get('event',{}).get('id')}")
    return t


def valid_events(events: Iterable[dict]):
    clean, skipped = [], []
    for ev in events:
        ts = _parse_ts(ev.get("@timestamp"))
        if ts is None:
            skipped.append(ev.get("event", {}).get("id", "<no-id>"))
            continue
        ev["_ts"] = ts
        clean.append(ev)
    clean.sort(key=lambda e: e["_ts"])
    return clean, skipped
