"""Единая обработка rate limit (K1-3): пауза только здесь."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class RateLimitState:
    simulated: bool = True
    _now: float = 0.0

    def sleep(self, seconds: float) -> None:
        if self.simulated:
            self._now += max(0.0, seconds)
        else:
            time.sleep(max(0.0, seconds))

    def now(self) -> float:
        return self._now if self.simulated else time.monotonic()


def _parse_retry_after(value: Optional[str], default: float = 60.0) -> float:
    if not value:
        return default
    try:
        return max(0.0, float(value))
    except ValueError:
        return default


def handle_status(
    status: int, headers: dict, state: RateLimitState
) -> Tuple[bool, Optional[float]]:
    """Возвращает (продолжить?, сколько_спал). Все паузы — через state.sleep()."""
    if status == 200:
        return True, None
    if status in (403, 429):
        wait = _parse_retry_after((headers or {}).get("Retry-After"))
        state.sleep(wait)
        return False, wait
    if status == 404:
        return False, None  # сущность исчезла — фиксируется как событие, не ошибка
    return False, None
