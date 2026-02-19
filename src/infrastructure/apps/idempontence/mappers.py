# src/infrastructure/idempotency/mappers.py

from __future__ import annotations

from typing import Any, cast, Optional

from src.domain.idempotency.models import (
    IdempotencyKey as DomainIdempotencyKey,
    StoredResponse,
    IdempotencyStatus,
)
from src.infrastructure.apps.idempontence.models import IdempotencyKey as IdempotencyKeyModel


class IdempotencyKeyMapper:
    """
    Mapper between domain IdempotencyKey and Django ORM model.
    Fully async-safe: avoids deferred attribute access that triggers sync DB hits.
    """

    @staticmethod
    def to_domain(orm_model: IdempotencyKeyModel) -> DomainIdempotencyKey:
        """
        Convert Django ORM model to domain model.
        Uses direct attribute access ONLY on pre-fetched fields via .only() or .values().
        """
        response: Optional[StoredResponse] = None
        if orm_model.response_data:
            response = StoredResponse(
                status_code=orm_model.response_data.get("status_code"),
                headers=orm_model.response_data.get("headers", {}),
                body=orm_model.response_data.get("body", {}),
            )

        return DomainIdempotencyKey(
            key=orm_model.key,
            user_id=orm_model.user_id,
            fingerprint=orm_model.fingerprint,
            expires_at=orm_model.expires_at,
            status=IdempotencyStatus[orm_model.status],
            response=response,
            request_id=orm_model.request_id,
            correlation_id=orm_model.correlation_id,
            locked_until=orm_model.locked_until,
            locked_by=orm_model.locked_by,
            idempotency_id=orm_model.idempotency_id,
            created_at=orm_model.created_at,
            updated_at=orm_model.updated_at,
        )

    @staticmethod
    def to_orm(domain_key: DomainIdempotencyKey) -> IdempotencyKeyModel:
        response_data = None
        if domain_key.response is not None:
            response_data = cast(
                Any,
                {
                    "status_code": domain_key.response.status_code,
                    "headers": domain_key.response.headers,
                    "body": domain_key.response.body,
                },
            )

        return IdempotencyKeyModel(
            idempotency_id=domain_key.idempotency_id,
            key=domain_key.key,
            user_id=domain_key.user_id,
            fingerprint=domain_key.fingerprint,
            expires_at=domain_key.expires_at,
            status=domain_key.status.name,
            request_id=domain_key.request_id,
            correlation_id=domain_key.correlation_id,
            locked_until=domain_key.locked_until,
            locked_by=domain_key.locked_by,
            response_data=response_data,
        )