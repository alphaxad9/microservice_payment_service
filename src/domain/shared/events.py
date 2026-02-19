# src/domain/events.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Type, TypeVar
from uuid import UUID, uuid4

# -----------------------
# Self-referencing TypeVar for proper subclass typing
# -----------------------
_DomainEventT = TypeVar("_DomainEventT", bound="DomainEvent")


# -----------------------
# Generic Domain Event (Abstract Base)
# -----------------------
@dataclass(frozen=True, kw_only=True)
class DomainEvent(ABC):
    """
    Abstract base class for all domain events across any bounded context.
    Provides common structure: identity, timestamp, versioning, and serialization.
    """
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = 1

    @property
    @abstractmethod
    def event_type(self) -> str:
        """
        Unique string identifier for the event type (e.g., 'payment.initiated').
        Should be stable and canonical for serialization and routing.
        """
        raise NotImplementedError("Subclasses must define event_type")

    def payload(self) -> Dict[str, Any]:
        """Return event-specific data for serialization (excluding metadata)."""
        return {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the event into a JSON-compatible dictionary."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload(),
        }

    @classmethod
    @abstractmethod
    def from_dict(cls: Type[_DomainEventT], data: Dict[str, Any]) -> _DomainEventT:
        """
        Reconstructs the event from a dictionary.
        Must be implemented by each concrete subclass.
        """
        raise NotImplementedError("Subclasses must implement from_dict")