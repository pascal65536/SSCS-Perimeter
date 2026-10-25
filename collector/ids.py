"""event.id по контракту Приложение А.3 / рулинги R1, R8, R9."""

from __future__ import annotations

import re
from datetime import datetime, timezone

_TS_FAST = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def normalize_id(s: str) -> str:
    return s.strip().lower()


def normalize_ts(raw: str) -> str:
    """Канонический ISO 8601 UTC: YYYY-MM-DDTHH:MM:SSZ. Рулинг R1:
    lower/trim применяется только к идентификаторам, регистр T/Z сохраняется."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty timestamp")
    if _TS_FAST.match(raw):
        return raw
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise ValueError(f"bad ISO timestamp: {raw!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ts_only(raw: str) -> str:
    return normalize_ts(raw)[11:19]


def created_id(name: str, first_release_at: str) -> str:
    """R9: pypi:{name}:{first_release_at} (без сегмента 'created')."""
    return f"pypi:{normalize_id(name)}:{normalize_ts(first_release_at)}"


def release_id(name: str, version: str, released_at: str) -> str:
    return f"pypi:{normalize_id(name)}:{version}:{normalize_ts(released_at)}"


def yank_id(name: str, version: str, observed_at: str) -> str:
    return f"pypi:{normalize_id(name)}:{version}:yank:{normalize_ts(observed_at)[:10].replace('-', '')}"


def commit_id(repo: str, sha: str) -> str:
    return f"gh:{normalize_id(repo)}:commit:{sha.strip().lower()}"


def pr_id(repo: str, number: int) -> str:
    return f"gh:{normalize_id(repo)}:pr:{int(number)}"


def membership_id(repo: str, login: str, event_at: str, change_type: str) -> str:
    """Рулинг R8."""
    d = normalize_ts(event_at)[:10].replace("-", "")
    return f"gh:{normalize_id(repo)}:member:{normalize_id(login)}:{d}:{change_type}"


def user_profile_id(login: str, date: str) -> str:
    return f"github-api:{normalize_id(login)}:metric:{date}"


def repo_snapshot_id(repo: str, date: str) -> str:
    return f"gh:{normalize_id(repo)}:metric:{date}"


def dedupe_key(doc: dict) -> str:
    return doc["event"]["id"]
