"""Временная файловая очередь телеметрии, не являющаяся хранилищем истории."""

from .queue import DiskSpool, EventValidationError, validate_event

__all__ = ["DiskSpool", "EventValidationError", "validate_event"]
