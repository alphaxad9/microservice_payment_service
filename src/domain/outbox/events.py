import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional


def _safe_json(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_json(v) for v in obj]
    return obj


@dataclass(frozen=True)
class OutboxEvent:
    event_type: str
    event_payload: Dict[str, Any]
    aggregate_id: uuid.UUID
    aggregate_type: str

    trace_id: Optional[uuid.UUID] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self):
        object.__setattr__(self, "event_payload", _safe_json(self.event_payload))

        if not isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", dict(self.metadata))

        if self.created_at.tzinfo is None:
            object.__setattr__(
                self,
                "created_at",
                self.created_at.replace(tzinfo=timezone.utc)
            )

        # Normalize metadata
        object.__setattr__(self, "metadata", _safe_json(self.metadata))
