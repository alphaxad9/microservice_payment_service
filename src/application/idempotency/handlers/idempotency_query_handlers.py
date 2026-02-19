# src/application/idempotency/handlers/query_handler.py
from __future__ import annotations

from datetime import datetime
from typing import Sequence, Dict, Any
from uuid import UUID

from src.application.idempotency.services.interfaces.idempotency_interface import (
    IdempotencyQueryServiceInterface,
)
from src.domain.idempotency.models import IdempotencyKey, IdempotencyStatus
from src.domain.idempotency.exceptions import IdempotencyKeyNotFoundError


class IdempotencyQueryHandler:

    def __init__(self, idempotency_queries: IdempotencyQueryServiceInterface):
        self._queries = idempotency_queries

    async def get_key(self, key: str, user_id: UUID) -> IdempotencyKey:
        """Retrieve a single idempotency key. Raises if not found."""
        try:
            return await self._queries.get_key(key=key, user_id=user_id)
        except IdempotencyKeyNotFoundError:
            raise
        except Exception as exc:
            raise IdempotencyKeyNotFoundError(
                message=f"Failed to retrieve idempotency key '{key}' for user {user_id}"
            ) from exc

    async def key_exists(self, key: str, user_id: UUID) -> bool:
        """Fast existence check – useful for middleware pre-flight."""
        try:
            return await self._queries.key_exists(key=key, user_id=user_id)
        except Exception:
            # Existence checks should be resilient; default to False on error
            return False

    async def get_keys_by_user(
        self,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        """
        Get all idempotency keys for a specific user (across all statuses),
        newest first, with pagination.
        """
        try:
            return await self._queries.get_keys_by_user(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to retrieve idempotency keys for user {user_id}"
            ) from exc

    async def get_keys_by_status(
        self,
        status: IdempotencyStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        try:
            return await self._queries.get_keys_by_status(
                status=status, limit=limit, offset=offset
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to retrieve keys with status {status.value}"
            ) from exc

    async def get_expired_keys(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        try:
            return await self._queries.get_expired_keys(limit=limit, offset=offset)
        except Exception as exc:
            raise RuntimeError("Failed to retrieve expired idempotency keys") from exc

    async def get_keys_by_fingerprint(
        self,
        fingerprint: str,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[IdempotencyKey]:
        try:
            return await self._queries.get_keys_by_fingerprint(
                fingerprint=fingerprint,
                user_id=user_id,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to retrieve keys for fingerprint {fingerprint}"
            ) from exc

    async def count_keys_by_user(self, user_id: UUID) -> int:
        try:
            return await self._queries.count_keys_by_user(user_id=user_id)
        except Exception as exc:
            raise RuntimeError(
                f"Unable to count idempotency keys for user {user_id}"
            ) from exc

    async def get_key_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        try:
            return await self._queries.get_key_metrics(
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            raise RuntimeError("Failed to compute idempotency key metrics") from exc