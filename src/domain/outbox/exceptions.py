# src/domain/outbox/exceptions.py
from __future__ import annotations
from uuid import UUID


class OutboxError(Exception):
    """Base exception for all outbox-related errors."""
    pass


class OutboxSaveError(OutboxError):
    """
    Raised when an event fails to be saved to the outbox.
    Typically due to database constraints, serialization issues, or transaction failures.
    """
    def __init__(self, event_type: str, aggregate_id: UUID, reason: str):
        self.event_type = event_type
        self.aggregate_id = aggregate_id
        self.reason = reason
        super().__init__(
            f"Failed to save outbox event '{event_type}' for {aggregate_id}: {reason}"
        )


class OutboxNotFoundError(OutboxError):
    """
    Raised when an outbox entry is not found (e.g., during mark_as_published/failed).
    Indicates a possible race condition, double-processing, or data corruption.
    """
    def __init__(self, outbox_id: UUID):
        self.outbox_id = outbox_id
        super().__init__(f"Outbox event with ID {outbox_id} not found.")


class OutboxPublishError(OutboxError):
    """
    Raised when the infrastructure fails to publish an event to the message broker
    (e.g., RabbitMQ connection loss, serialization error).
    This is typically caught by the publisher to trigger mark_as_failed().
    """
    def __init__(self, outbox_id: UUID, event_type: str, broker_error: str):
        self.outbox_id = outbox_id
        self.event_type = event_type
        self.broker_error = broker_error
        super().__init__(
            f"Failed to publish outbox event {outbox_id} ('{event_type}'): {broker_error}"
        )


class OutboxConcurrencyError(OutboxError):
    """
    Raised when concurrent access causes an unexpected state 
    (e.g., optimistic locking failure, version conflict).
    Rare in outbox pattern but possible in high-load scenarios.
    """
    def __init__(self, outbox_id: UUID, message: str = "Concurrency conflict detected"):
        self.outbox_id = outbox_id
        super().__init__(f"{message} for outbox ID {outbox_id}")


class OutboxMaxRetriesExceededError(OutboxError):
    """
    Raised when an event has exceeded the maximum allowed retry attempts.
    Signals that manual intervention or dead-letter handling may be needed.
    """
    def __init__(self, outbox_id: UUID, max_retries: int, last_error: str):
        self.outbox_id = outbox_id
        self.max_retries = max_retries
        self.last_error = last_error
        super().__init__(
            f"Outbox event {outbox_id} exceeded max retries ({max_retries}): {last_error}"
        )