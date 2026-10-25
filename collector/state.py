"""Курсор инкрементального опроса (ТЗ п. 4.2, poll_state)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class CollectorState:
    last_seen_event_ids: List[str] = field(default_factory=list)
    last_success_at: Optional[str] = None
    next_cursor: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "last_seen_event_ids": self.last_seen_event_ids,
            "last_success_at": self.last_success_at,
            "next_cursor": self.next_cursor,
        }

    @classmethod
    def from_json(cls, data: dict) -> "CollectorState":
        return cls(
            last_seen_event_ids=list(data.get("last_seen_event_ids") or []),
            last_success_at=data.get("last_success_at"),
            next_cursor=data.get("next_cursor"),
        )


def load(path: Path) -> CollectorState:
    if path.exists():
        return CollectorState.from_json(json.loads(path.read_text(encoding="utf-8")))
    return CollectorState()


def save(path: Path, state: CollectorState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_json(), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def make_state(event_ids: List[str], ingested_at: str) -> CollectorState:
    return CollectorState(
        last_seen_event_ids=sorted(set(event_ids)), last_success_at=ingested_at
    )


def cursors_equal(a: CollectorState, b: CollectorState) -> bool:
    return (
        a.last_seen_event_ids == b.last_seen_event_ids
        and a.next_cursor == b.next_cursor
    )
