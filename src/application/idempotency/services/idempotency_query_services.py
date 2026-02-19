# src/application/idempotency/services/query_service.py

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Sequence
from uuid import UUID

from django.utils import timezone as django_timezone

from src.domain.idempotency.models import IdempotencyKey, IdempotencyStatus
from src.application.idempotency.services.interfaces.idempotency_interface import IdempotencyQueryServiceInterface
from src.domain.idempotency.repository import IdempotencyKeyQueryRepository
from src.domain.idempotency.exceptions import IdempotencyKeyNotFoundError


class IdempotencyQueryService(IdempotencyQueryServiceInterface):
    """
    Concrete implementation of the read-side query service for idempotency keys.
    Delegates to the underlying async query repository.
    """

    def __init__(self, query_repository: IdempotencyKeyQueryRepository):
        self.query_repository = query_repository

    async def get_key(self, key: str, user_id: UUID) -> IdempotencyKey:
        """
        Retrieve a full idempotency key domain object.

        Raises:
            IdempotencyKeyNotFoundError: If key doesn't exist
        """
        try:
            return await self.query_repository.get_by_key_and_user(key=key, user_id=user_id)
        except Exception as e:
            # Repository may raise generic exception; normalize to domain error
            raise IdempotencyKeyNotFoundError(key=key) from e

    async def key_exists(self, key: str, user_id: UUID) -> bool:
        """
        Check if an idempotency key exists.
        """
        return await self.query_repository.exists(key=key, user_id=user_id)

    async def get_keys_by_status(
        self,
        status: IdempotencyStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve idempotency keys filtered by status.
        Ordered by created_at descending (newest first).
        """
        return await self.query_repository.get_by_status(status=status, limit=limit, offset=offset)

    async def get_expired_keys(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve expired idempotency keys.
        Ordered by expires_at ascending (oldest first).
        """
        cutoff = django_timezone.now()
        return await self.query_repository.get_expired_keys(cutoff=cutoff, limit=limit, offset=offset)

    async def get_keys_by_user(
        self,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve all idempotency keys for a specific user across all statuses.
        Ordered by created_at descending (newest first).
        """
        # Efficient approach: delegate filtering to repository if possible.
        # If your repository doesn't support cross-status user queries,
        # this fallback combines results from all statuses.
        pending = await self.query_repository.get_by_status(
            status=IdempotencyStatus.PENDING, limit=1000, offset=0
        )
        completed = await self.query_repository.get_by_status(
            status=IdempotencyStatus.COMPLETED, limit=1000, offset=0
        )
        failed = await self.query_repository.get_by_status(
            status=IdempotencyStatus.FAILED, limit=1000, offset=0
        )

        # Merge and filter by user
        all_keys = [k for k in (*pending, *completed, *failed) if k.user_id == user_id]

        # Sort by created_at (newest first) and paginate
        sorted_keys = sorted(all_keys, key=lambda k: k.created_at, reverse=True)
        return sorted_keys[offset : offset + limit]

    async def get_keys_by_fingerprint(
        self,
        fingerprint: str,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Retrieve idempotency keys by request fingerprint.
        """
        return await self.query_repository.get_by_fingerprint(
            fingerprint=fingerprint, user_id=user_id, limit=limit, offset=offset
        )

    async def count_keys_by_user(self, user_id: UUID) -> int:
        """
        Count total idempotency keys for a user.
        """
        return await self.query_repository.count_by_user(user_id=user_id)

    async def get_key_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """
        Aggregates basic metrics about idempotency key usage in a time range.
        Note: This naive implementation may be inefficient at scale.
        For production, consider raw SQL or materialized views.
        """
        # Fetch counts per status (assumes repository filters by time — if not, adjust accordingly)
        # ⚠️ Your current repository interface does NOT support time-range filtering in get_by_status.
        # So this implementation gives global counts, not time-bounded ones.
        # You may want to extend the repository later for true time-scoped metrics.

        pending = len(await self.query_repository.get_by_status(IdempotencyStatus.PENDING))
        completed = len(await self.query_repository.get_by_status(IdempotencyStatus.COMPLETED))
        failed = len(await self.query_repository.get_by_status(IdempotencyStatus.FAILED))

        total = pending + completed + failed

        return {
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_keys": total,
            "by_status": {
                "pending": pending,
                "completed": completed,
                "failed": failed,
            },
            "replay_rate": (completed + failed) / total if total > 0 else 0.0,
        }