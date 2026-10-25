from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class NotesStore:
    """Локальные заметки пользователя; не входят в телеметрию и SIEM."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or Path.home() / ".sscs" / "notes.json").expanduser()

    def get(self, package: str) -> str:
        return str(self._read().get(package, ""))

    def set(self, package: str, text: str) -> None:
        data = self._read()
        if text.strip():
            data[package] = text
        else:
            data.pop(package, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".notes.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
