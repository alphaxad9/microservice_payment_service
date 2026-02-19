# src/domain/outbox/repositories.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
from uuid import UUID
from src.domain.outbox.events import OutboxEvent


class OutboxRepository(ABC):
    """
    Domain contract for the transactional outbox pattern.
    Implemented by infrastructure (e.g., Django ORM).
    Used by ALL domains (User, ChatRoom, etc.).
    """

    @abstractmethod
    def save(self, event: OutboxEvent) -> None:
        """
        Persist event in the SAME DB transaction as domain state change.
        Called from domain services within transaction.atomic().
        """
        raise NotImplementedError

    @abstractmethod
    def get_unpublished_events(self, limit: int = 100) -> List[OutboxEvent]:
        """
        Fetch unpublished events for publishing.
        Must be concurrency-safe (e.g., SELECT FOR UPDATE SKIP LOCKED).
        """
        raise NotImplementedError

    @abstractmethod
    def mark_as_published(self, outbox_id: UUID) -> None:
        """
        Mark event as successfully published.
        Sets published_at and processed_at.
        """
        raise NotImplementedError

    @abstractmethod
    def mark_as_failed(self, outbox_id: UUID, error: str) -> None:
        """
        Mark event as failed (for retry/observability).
        Increments retry_count and records error.
        """
        raise NotImplementedError
    
