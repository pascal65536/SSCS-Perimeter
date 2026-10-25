from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = "1.0"


def load_snapshot(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("snapshot_version") != SNAPSHOT_VERSION:
        raise ValueError("Неподдерживаемая версия снапшота")
    if not isinstance(data.get("project"), dict) or not isinstance(data.get("packages"), list):
        raise ValueError("Снапшот должен содержать project и packages")
    data.setdefault("findings", [])
    return data


def save_snapshot(data: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def snapshot_from_settings(settings: dict[str, Any], *, findings: list[dict] | None = None) -> dict[str, Any]:
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": settings["project"],
        "packages": settings["perimeter"]["packages"],
        "findings": findings or [],
    }
