"""Интеграция с OpenSearch без хранения аналитических активов в агенте."""

from .gateway import OpenSearchGateway, SIEMError

__all__ = ["OpenSearchGateway", "SIEMError"]
