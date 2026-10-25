from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from collector.ids import normalize_ts

LOG = logging.getLogger(__name__)


class EventValidationError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_event(event: dict[str, Any], *, now: datetime | None = None, future_tolerance_s: int = 300) -> None:
    if not isinstance(event, dict):
        raise EventValidationError("Событие должно быть JSON-объектом")
    try:
        timestamp = normalize_ts(event["@timestamp"])
        event_id = event["event"]["id"]
        action = event["event"]["action"]
        watchlist = event["sscs"]["watchlist"]
        source = event["source"]["service"]
    except (KeyError, TypeError, ValueError) as exc:
        raise EventValidationError(f"Нарушен конверт sscs-event/1.0: {exc}") from exc
    if not all(isinstance(x, str) and x for x in (event_id, action, source)):
        raise EventValidationError("event.id, event.action и source.service обязательны")
    if watchlist not in {"monitored", "reference", "ground_truth"}:
        raise EventValidationError(f"Недопустимый watchlist: {watchlist!r}")
    for key in ("kind", "category", "type"):
        if not isinstance(event["event"].get(key), str) or not event["event"][key]:
            raise EventValidationError(f"event.{key} обязателен")
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if dt > (now or _utc_now()):
        from datetime import timedelta
        if dt - (now or _utc_now()) > timedelta(seconds=future_tolerance_s):
            raise EventValidationError("Метка события находится в будущем")
    event["@timestamp"] = timestamp


class DiskSpool:
    """Ограниченная JSONL-очередь с ack и dead letter queue.

    При переполнении удаляются самые старые записи. Единственное назначение
    файла — пережить временную недоступность SIEM; резервное копирование не
    предусмотрено. Операции внутри процесса сериализуются блокировкой.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        max_bytes: int = 64 * 1024 * 1024,
        now: Callable[[], datetime] | None = None,
    ):
        if max_bytes < 1024:
            raise ValueError("max_bytes должен быть не меньше 1024")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.queue_path = self.directory / "queue.jsonl"
        self.dlq_path = self.directory / "dead-letter.jsonl"
        self.max_bytes = max_bytes
        self.now = now or _utc_now
        self._lock = threading.RLock()

    def enqueue(self, event: dict[str, Any]) -> bool:
        with self._lock:
            try:
                validate_event(event, now=self.now())
            except EventValidationError as exc:
                self._dead_letter(event, str(exc))
                return False
            line = self._line(event)
            if len(line) > self.max_bytes:
                self._dead_letter(event, "Размер события превышает весь лимит Spool")
                return False
            lines = self._read_lines()
            lines.append(line)
            dropped = 0
            while sum(map(len, lines)) > self.max_bytes and len(lines) > 1:
                lines.pop(0)
                dropped += 1
            if dropped:
                LOG.warning("Spool переполнен: отброшено старых событий: %d", dropped)
            self._write_lines(lines)
            return True

    def extend(self, events) -> dict[str, int]:
        stats = {"accepted": 0, "rejected": 0}
        for event in events:
            stats["accepted" if self.enqueue(event) else "rejected"] += 1
        return stats

    def peek(self, limit: int = 500) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            return [json.loads(line) for line in self._read_lines()[:limit]]

    def ack(self, count: int) -> None:
        if count < 0:
            raise ValueError("count не может быть отрицательным")
        with self._lock:
            lines = self._read_lines()
            if count > len(lines):
                raise ValueError("Нельзя подтвердить больше событий, чем находится в очереди")
            self._write_lines(lines[count:])

    def deliver(self, gateway, *, batch_size: int = 500) -> dict[str, int]:
        batch = self.peek(batch_size)
        if not batch:
            return {"accepted": 0, "duplicates": 0, "errors": 0, "remaining": 0}
        result = gateway.send(batch)
        accounted = result.get("accepted", 0) + result.get("duplicates", 0) + result.get("errors", 0)
        if result.get("errors", 0) or accounted != len(batch):
            raise RuntimeError(f"SIEM подтвердил {accounted} из {len(batch)} событий; ack не выполнен")
        self.ack(len(batch))
        return {**result, "remaining": self.count}

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._read_lines())

    @property
    def size_bytes(self) -> int:
        with self._lock:
            return self.queue_path.stat().st_size if self.queue_path.exists() else 0

    def _dead_letter(self, event: Any, reason: str) -> None:
        record = {
            "dropped_at": self.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason": reason,
            "event": event,
        }
        with self.dlq_path.open("a", encoding="utf-8") as stream:
            stream.write(self._line(record).decode("utf-8"))
        LOG.error("Событие направлено в DLQ: %s", reason)

    def _read_lines(self) -> list[bytes]:
        if not self.queue_path.exists():
            return []
        return [line for line in self.queue_path.read_bytes().splitlines(keepends=True) if line.strip()]

    def _write_lines(self, lines: list[bytes]) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=".queue.", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.writelines(lines)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, self.queue_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def _line(value: Any) -> bytes:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
