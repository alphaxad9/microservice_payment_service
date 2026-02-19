# src/infrastructure/repos/idempontency/idempotence_query_repo.py
# (or src/infrastructure/idempotency/repository.py — adjust import paths as needed)

from __future__ import annotations

from typing import Optional, Dict, Any, Sequence
from uuid import UUID
from datetime import datetime

from asgiref.sync import sync_to_async

from src.domain.idempotency.models import (
    IdempotencyKey as DomainIdempotencyKey,
    IdempotencyStatus,
    StoredResponse,
)
from src.domain.idempotency.exceptions import IdempotencyKeyNotFoundError
from src.domain.idempotency.repository import IdempotencyKeyQueryRepository

from src.infrastructure.apps.idempontence.models import IdempotencyKey as IdempotencyKeyModel
from src.infrastructure.apps.idempontence.mappers import IdempotencyKeyMapper  # Adjust if path differs


class DjangoIdempotencyKeyQueryRepository(IdempotencyKeyQueryRepository):
    """
    Async-compatible Django ORM implementation of the IdempotencyKey query repository.
    All queries that lead to domain mapping use .only() with ALL fields required by the mapper
    to prevent deferred loading and SynchronousOnlyOperation errors in async contexts.
    """

    # List of all fields used in IdempotencyKeyMapper.to_domain()
    _DOMAIN_FIELDS = [
        "idempotency_id",
        "key",
        "user_id",
        "fingerprint",
        "expires_at",
        "status",
        "response_data",
        "request_id",
        "correlation_id",
        "locked_until",
        "locked_by",
        "created_at",
        "updated_at",
    ]

    async def get_by_key_and_user(self, key: str, user_id: UUID) -> DomainIdempotencyKey:
        try:
            orm_model = await (
                IdempotencyKeyModel.objects
                .only(*self._DOMAIN_FIELDS)
                .aget(key=key, user_id=user_id)
            )
        except IdempotencyKeyModel.DoesNotExist as exc:
            raise IdempotencyKeyNotFoundError(key=key) from exc

        return IdempotencyKeyMapper.to_domain(orm_model)

    async def get_replay_response(
        self, key: str, user_id: UUID
    ) -> Optional[StoredResponse]:
        """
        Fast-path for idempotency replay: checks if a completed/failed response can be replayed.
        """
        try:
            orm_model = await (
                IdempotencyKeyModel.objects
                .filter(key=key, user_id=user_id)
                .only(*self._DOMAIN_FIELDS)  # Critical: load all fields needed for domain model
                .aget()
            )
        except IdempotencyKeyModel.DoesNotExist:
            return None

        domain_key = IdempotencyKeyMapper.to_domain(orm_model)
        return domain_key.get_replay_response()

    async def get_used_key_response(self, key: str, user_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Legacy method — returns raw response dict if exists and key is terminal.
        Does not validate expiration (use get_replay_response for safer logic).
        """
        try:
            orm_model = await (
                IdempotencyKeyModel.objects
                .filter(key=key, user_id=user_id)
                .exclude(response_data__isnull=True)
                .filter(status__in=[IdempotencyStatus.COMPLETED.name, IdempotencyStatus.FAILED.name])
                .only("response_data")
                .aget()
            )
        except IdempotencyKeyModel.DoesNotExist:
            return None

        response_data = orm_model.response_data
        if response_data:
            return {
                "status_code": response_data.get("status_code"),
                "headers": response_data.get("headers", {}),
                "body": response_data.get("body", {}),
            }
        return None

    async def exists(self, key: str, user_id: UUID) -> bool:
        return await IdempotencyKeyModel.objects.filter(key=key, user_id=user_id).aexists()

    async def get_by_status(
        self,
        status: IdempotencyStatus,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[DomainIdempotencyKey]:
        queryset = IdempotencyKeyModel.objects.filter(status=status.name).order_by('-created_at')
        orm_models = await sync_to_async(list)(queryset[offset:offset + limit])
        # Even in bulk, we load all fields — Django fetches them in one query anyway
        return [IdempotencyKeyMapper.to_domain(m) for m in orm_models]

    async def get_expired_keys(
        self,
        cutoff: datetime,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[DomainIdempotencyKey]:
        queryset = IdempotencyKeyModel.objects.filter(expires_at__lt=cutoff).order_by('expires_at')
        orm_models = await sync_to_async(list)(queryset[offset:offset + limit])
        return [IdempotencyKeyMapper.to_domain(m) for m in orm_models]

    async def get_by_fingerprint(
        self,
        fingerprint: str,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> Sequence[DomainIdempotencyKey]:
        queryset = (
            IdempotencyKeyModel.objects
            .filter(fingerprint=fingerprint, user_id=user_id)
            .order_by('-created_at')
        )
        orm_models = await sync_to_async(list)(queryset[offset:offset + limit])
        return [IdempotencyKeyMapper.to_domain(m) for m in orm_models]

    async def count_by_user(self, user_id: UUID) -> int:
        return await IdempotencyKeyModel.objects.filter(user_id=user_id).acount()