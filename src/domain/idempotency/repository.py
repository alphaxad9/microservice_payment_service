# src/domain/idempotency/repository.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Sequence, Union
from uuid import UUID

from src.domain.idempotency.models import (
    IdempotencyKey,
    IdempotencyStatus,
    StoredResponse,
)

@dataclass(frozen=True)
class IdempotencyReplayResult:
    """Indicates a duplicate request: replay this response."""
    response: StoredResponse


@dataclass(frozen=True)
class IdempotencyAcquiredResult:
    """Indicates a new request: process it using this locked key."""
    key: IdempotencyKey


@dataclass(frozen=True)
class IdempotencyConflictResult:
    """Indicates an invalid request that cannot proceed."""
    reason: str  # e.g., "fingerprint_mismatch", "already_locked", "key_expired"


IdempotencyClaimResult = Union[
    IdempotencyReplayResult,
    IdempotencyAcquiredResult,
    IdempotencyConflictResult,
]


class IdempotencyKeyQueryRepository(ABC):
    @abstractmethod
    async def get_by_key_and_user(self, key: str, user_id: UUID) -> IdempotencyKey:
        raise NotImplementedError

    @abstractmethod
    async def get_used_key_response(self, key: str, user_id: UUID) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str, user_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_by_status(
        self,
        status: IdempotencyStatus,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[IdempotencyKey]:
        raise NotImplementedError
    @abstractmethod
    async def get_replay_response(
        self, key: str, user_id: UUID
    ) -> Optional[StoredResponse]:
        """
        Returns the stored response if the key is in a terminal state (COMPLETED or FAILED)
        and not expired. Returns None otherwise.
        This is the preferred method for the fast-path replay check.
        """
        raise NotImplementedError
    @abstractmethod
    async def get_expired_keys(
        self,
        cutoff: datetime,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[IdempotencyKey]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_fingerprint(
        self,
        fingerprint: str,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[IdempotencyKey]:
        raise NotImplementedError

    @abstractmethod
    async def count_by_user(self, user_id: UUID) -> int:
        raise NotImplementedError


class IdempotencyKeyCommandRepository(ABC):
    @abstractmethod
    async def create(self, key: IdempotencyKey) -> IdempotencyKey:
        raise NotImplementedError

    @abstractmethod
    async def update(self, key: IdempotencyKey) -> IdempotencyKey:
        raise NotImplementedError

    @abstractmethod
    async def lock(
        self,
        key: str,
        user_id: UUID,
        locker_id: str,
        lock_duration_seconds: int = 60
    ) -> IdempotencyKey:
        raise NotImplementedError

    @abstractmethod
    async def unlock(self, key: str, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def force_unlock(self, key: str, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str, user_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_expired_before(self, cutoff: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    async def delete_by_user(self, user_id: UUID) -> int:
        raise NotImplementedError

    @abstractmethod
    async def claim_or_replay(
        self,
        key: str,
        user_id: UUID,
        fingerprint: str,
        locker_id: str,
        lease_duration_seconds: int = 30,
    ) -> IdempotencyClaimResult:
        raise NotImplementedError