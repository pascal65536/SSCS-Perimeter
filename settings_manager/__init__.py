"""Целостное управление конфигурацией SSCS-Perimeter."""

from .manager import SettingsError, SettingsManager, canonical_name, default_settings

__all__ = ["SettingsError", "SettingsManager", "canonical_name", "default_settings"]
