# src/domain/idempotency/services/interfaces/interfaces.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Sequence
from uuid import UUID
from datetime import datetime

from src.domain.idempotency.models import IdempotencyKey, IdempotencyStatus
DEFAULT_TTL_HOURS = 24

# =========================
# COMMAND INTERFACE (Write Side)
# =========================
class IdempotencyCommandServiceInterface(ABC):
    """
    Abstract interface for the write-side of the idempotency domain.
    Defines all operations that mutate idempotency key state.

    Used by API middleware, request handlers, and idempotency coordinators.
    """

    @abstractmethod
    async def create_key(
            self,
            key: str,
            user_id: UUID,
            fingerprint: str,                    # ← Now receives pre-computed fingerprint
            ttl_hours: int = DEFAULT_TTL_HOURS,
            request_method: Optional[str] = None,
            request_path: Optional[str] = None,
            client_ip: Optional[str] = None,
        ) -> IdempotencyKey:
        raise NotImplementedError

    @abstractmethod
    async def process_request(
        self,
        key: str,
        user_id: UUID,
        locker_id: str,
        fingerprint: str = ""   # ← add parameter (can be empty during transition)
    ) -> Optional[Dict[str, Any]]:
        
        raise NotImplementedError

    @abstractmethod
    async def record_success(
        self,
        key: str,
        user_id: UUID,
        status_code: int,
        headers: Dict[str, str],
        body: Dict[str, Any],
    ) -> None:
        
        raise NotImplementedError

    @abstractmethod
    async def record_failure(
        self,
        key: str,
        user_id: UUID,
        status_code: int,
        headers: Dict[str, str],
        body: Dict[str, Any],
    ) -> None:
        
        raise NotImplementedError

    @abstractmethod
    async def cleanup_expired_keys(self, older_than_hours: int = 24) -> int:
       
        raise NotImplementedError

    @abstractmethod
    async def delete_user_keys(self, user_id: UUID) -> int:
        """
        Delete all idempotency keys for a user.
        Useful for user account deletion or GDPR compliance.

        Returns:
            Number of keys deleted
        """
        raise NotImplementedError


# =========================
# QUERY INTERFACE (Read Side)
# =========================
class IdempotencyQueryServiceInterface(ABC):
    """
    Abstract interface for the read-side of the idempotency domain.
    Defines all query operations on idempotency keys.

    Used by admin dashboards, monitoring systems, and debugging tools.
    """

    @abstractmethod
    async def get_key(self, key: str, user_id: UUID) -> IdempotencyKey:
        """
        Retrieve a full idempotency key domain object.

        Args:
            key: Idempotency key
            user_id: User ID

        Returns:
            IdempotencyKey domain object

        Raises:
            IdempotencyKeyNotFoundError: If key doesn't exist
        """
        raise NotImplementedError

    @abstractmethod
    async def key_exists(self, key: str, user_id: UUID) -> bool:
        """
        Check if an idempotency key exists.

        Args:
            key: Idempotency key
            user_id: User ID

        Returns:
            True if key exists, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    async def get_keys_by_status(
        self,
        status: IdempotencyStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve idempotency keys filtered by status.

        Args:
            status: Status to filter by
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of IdempotencyKey domain objects ordered by created_at (newest first)
        """
        raise NotImplementedError

    @abstractmethod
    async def get_expired_keys(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve expired idempotency keys.

        Args:
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of expired IdempotencyKey domain objects ordered by expires_at (oldest first)
        """
        raise NotImplementedError

    @abstractmethod
    async def get_keys_by_user(
        self,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve all idempotency keys for a user.

        Args:
            user_id: User ID
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of IdempotencyKey domain objects ordered by created_at (newest first)
        """
        raise NotImplementedError

    @abstractmethod
    async def get_keys_by_fingerprint(
        self,
        fingerprint: str,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve idempotency keys by request fingerprint.
        Useful for detecting request collisions or debugging.

        Args:
            fingerprint: SHA-256 fingerprint
            user_id: User ID
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of IdempotencyKey domain objects ordered by created_at (newest first)
        """
        raise NotImplementedError

    @abstractmethod
    async def count_keys_by_user(self, user_id: UUID) -> int:
        """
        Count total idempotency keys for a user.
        Useful for rate limiting and monitoring.

        Args:
            user_id: User ID

        Returns:
            Number of keys
        """
        raise NotImplementedError

    @abstractmethod
    async def get_key_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """
        Get metrics about idempotency key usage.

        Args:
            start_date: Start of time range
            end_date: End of time range

        Returns:
            Dictionary with metrics (e.g., total_keys, by_status, by_user)
        """
        raise NotImplementedError