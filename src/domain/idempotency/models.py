# src/domain/idempotency/models.py
from __future__ import annotations
from datetime import timedelta
import json
from datetime import datetime, timezone
from enum import Enum, auto
from hashlib import sha256
from typing import Any, Dict, Optional, Set
from uuid import UUID, uuid4
from dataclasses import dataclass, field

from src.domain.idempotency.exceptions import IdempotencyInvalidStateTransitionError


def _now_utc() -> datetime:
    """Helper to always return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def compute_fingerprint(payload: Dict[str, Any]) -> str:
    """
    Create a canonical SHA-256 fingerprint of the request payload.
    Ensures the same idempotency key cannot be reused with different data.
    """
    canonical_json = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return sha256(canonical_json.encode("utf-8")).hexdigest()


class IdempotencyStatus(Enum):
    """Explicit, finite state machine for idempotency key lifecycle."""
    PENDING = auto()
    COMPLETED = auto()
    FAILED = auto()  # Treat as final; replay exact response


# Define allowed transitions (PENDING → terminal states only)
_ALLOWED_TRANSITIONS: Dict[IdempotencyStatus, Set[IdempotencyStatus]] = {
    IdempotencyStatus.PENDING: {IdempotencyStatus.COMPLETED, IdempotencyStatus.FAILED},
    IdempotencyStatus.COMPLETED: set(),
    IdempotencyStatus.FAILED: set(),
}


@dataclass(frozen=True)
class StoredResponse:
    """
    Immutable container for full HTTP response to enable exact replay.
    Includes headers for content-type, location, etc.
    """
    status_code: int
    headers: Dict[str, str]  # e.g., {"Content-Type": "application/json"}
    body: Dict[str, Any]


@dataclass
class IdempotencyKey:
    """
    Domain model (aggregate root) for idempotency.
    """
    key: str
    user_id: UUID
    fingerprint: str
    expires_at: datetime
    # State
    status: IdempotencyStatus = IdempotencyStatus.PENDING
    response: Optional[StoredResponse] = None
    # Operational traceability
    request_id: Optional[UUID] = None
    correlation_id: Optional[UUID] = None
    # Concurrency control (lease-based locking)
    locked_until: Optional[datetime] = None
    locked_by: Optional[str] = None
    # Metadata
    idempotency_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now_utc)
    updated_at: datetime = field(default_factory=_now_utc)

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("Idempotency key must be a non-empty string")
        object.__setattr__(self, "updated_at", self.created_at)

    def _transition_to(self, new_status: IdempotencyStatus) -> None:
        """Enforce state machine transitions."""
        allowed = _ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise IdempotencyInvalidStateTransitionError(
                key=self.key,
                current_status=self.status.name,
                attempted_action=f"transition to {new_status.name}",
            )

    def is_lock_expired(self) -> bool:
        """True if lock has expired or was never set."""
        if self.locked_until is None:
            return True
        return _now_utc() >= self.locked_until

    def is_expired(self) -> bool:
        return _now_utc() >= self.expires_at

    def is_pending(self) -> bool:
        return self.status == IdempotencyStatus.PENDING

    def is_completed(self) -> bool:
        return self.status == IdempotencyStatus.COMPLETED

    def is_failed(self) -> bool:
        return self.status == IdempotencyStatus.FAILED

    def has_response(self) -> bool:
        return self.response is not None

    def mark_in_progress(self, locker_id: str, lease_duration_seconds: int = 30) -> None:
        """
        Called when claiming a key for processing.
        Only valid if currently unlocked or lock is expired.
        """
        if not self.is_pending():
            raise IdempotencyInvalidStateTransitionError(
                key=self.key,
                current_status=self.status.name,
                attempted_action="mark in progress",
            )
        if self.locked_until is not None and not self.is_lock_expired():
            raise ValueError("Key is currently locked by another worker")

        now = _now_utc()
        object.__setattr__(
            self, "locked_until", now.replace(microsecond=0) + timedelta(seconds=lease_duration_seconds)
        )
        object.__setattr__(self, "locked_by", locker_id)
        object.__setattr__(self, "updated_at", now)

    def _clear_lock(self) -> None:
        """Internal helper to clear lock fields on finalization."""
        object.__setattr__(self, "locked_until", None)
        object.__setattr__(self, "locked_by", None)

    def record_success(self, status_code: int, headers: Dict[str, str], body: Dict[str, Any]) -> None:
        """Record final successful outcome—idempotent replay enabled."""
        self._transition_to(IdempotencyStatus.COMPLETED)
        object.__setattr__(self, "status", IdempotencyStatus.COMPLETED)
        object.__setattr__(self, "response", StoredResponse(status_code, headers, body))
        self._clear_lock()
        object.__setattr__(self, "updated_at", _now_utc())

    def record_failure(self, status_code: int, headers: Dict[str, str], body: Dict[str, Any]) -> None:
        """Record final failure outcome—replayed exactly on duplicates."""
        self._transition_to(IdempotencyStatus.FAILED)
        object.__setattr__(self, "status", IdempotencyStatus.FAILED)
        object.__setattr__(self, "response", StoredResponse(status_code, headers, body))
        self._clear_lock()
        object.__setattr__(self, "updated_at", _now_utc())

    def get_replay_response(self) -> Optional[StoredResponse]:
        """Return stored response if available and not expired."""
        if self.is_expired():
            return None
        if self.is_completed() or self.is_failed():
            return self.response
        return None

    @staticmethod
    def create_new(
        key: str,
        user_id: UUID,
        fingerprint: str,
        expires_at: datetime,
        request_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
    ) -> "IdempotencyKey":
        if not key or not key.strip():
            raise ValueError("Idempotency key must be a non-empty string")
        now = _now_utc()
        if expires_at <= now:
            raise ValueError("Expiration time must be in the future")
        return IdempotencyKey(
            key=key.strip(),
            user_id=user_id,
            fingerprint=fingerprint,
            expires_at=expires_at,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    def __repr__(self) -> str:
        return (
            f"IdempotencyKey(id={self.idempotency_id}, key='{self.key}', "
            f"user={self.user_id}, status={self.status.name}, "
            f"expired={self.is_expired()}, has_response={self.has_response()})"
        )