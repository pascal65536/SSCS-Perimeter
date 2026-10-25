from __future__ import annotations

from pathlib import Path

from perimeter import PerimeterBuilder
from settings_manager import SettingsManager


class SettingsClient:
    """GUI не редактирует JSON напрямую: все записи проходят SettingsManager."""

    def __init__(self, path: str | Path):
        self.manager = SettingsManager(path)

    def add_package(self, name: str, version: str | None = None):
        return self.manager.add_root(name, version or None)

    def recalculate(self, *, generated_at: str | None = None):
        return PerimeterBuilder().rebuild(str(self.manager.path), generated_at=generated_at)
