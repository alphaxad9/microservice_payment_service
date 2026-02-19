# src/domain/commands.py

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    ConfigDict,
)


# ------------------------
# Generic Domain Command Base
# ------------------------
class DomainCommand(BaseModel):
    """
    Immutable, traceable base command for any domain.
    Enforces UTC timestamps, frozen state, and clean serialization.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: Optional[UUID] = Field(
        default=None,
        description="Correlation ID (e.g., saga ID, aggregate ID, or request ID)."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of command creation."
    )

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC).")
        return v.astimezone(timezone.utc)

    def dict(self, *args, **kwargs) -> Dict[str, Any]:
        """Ensure consistent access to serialized form via .dict()."""
        return self.model_dump(*args, **kwargs)


# Optional: TypeVar for typed command reconstruction (if needed later)
_DomainCommandT = TypeVar("_DomainCommandT", bound=DomainCommand)