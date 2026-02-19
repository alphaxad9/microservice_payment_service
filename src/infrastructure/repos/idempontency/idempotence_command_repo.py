# src/infrastructure/idempotency/repository.py

from __future__ import annotations

from datetime import datetime, timedelta  # <-- Import timedelta here
from uuid import UUID
from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction
from django.utils import timezone as django_timezone

from src.domain.idempotency.models import (
    IdempotencyKey as DomainIdempotencyKey,
    IdempotencyStatus,
    StoredResponse,
)
from src.domain.idempotency.repository import (
    IdempotencyKeyCommandRepository,
    IdempotencyAcquiredResult,
    IdempotencyClaimResult,
    IdempotencyConflictResult,
    IdempotencyReplayResult,
)
from src.domain.idempotency.exceptions import (
    IdempotencyKeyAlreadyExistsError,
    IdempotencyKeyNotFoundError,
    IdempotencyKeyExpiredError,
    IdempotencyKeyAlreadyUsedError,
    IdempotencyKeyAlreadyLockedError,
    IdempotencyResponseMissingError,
)
from src.infrastructure.apps.idempontence.models import IdempotencyKey as IdempotencyKeyModel
from src.infrastructure.apps.idempontence.mappers import IdempotencyKeyMapper


class DjangoIdempotencyKeyCommandRepository(IdempotencyKeyCommandRepository):
    """
    Async-compatible Django ORM implementation of the command-side repository.
    Wraps synchronous transactional logic with sync_to_async for compatibility.
    """

    async def create(self, key: DomainIdempotencyKey) -> DomainIdempotencyKey:
        orm_model = IdempotencyKeyMapper.to_orm(key)
        try:
            await sync_to_async(orm_model.save)(force_insert=True)
        except IntegrityError as exc:
            raise IdempotencyKeyAlreadyExistsError(key=key.key, user_id=key.user_id) from exc
        return IdempotencyKeyMapper.to_domain(orm_model)

    async def update(self, key: DomainIdempotencyKey) -> DomainIdempotencyKey:
        @sync_to_async
        def _update():
            try:
                with transaction.atomic():
                    orm_model = IdempotencyKeyModel.objects.select_for_update().get(
                        key=key.key, user_id=key.user_id
                    )
                    orm_model.fingerprint = key.fingerprint
                    orm_model.expires_at = key.expires_at
                    orm_model.status = key.status.name
                    orm_model.locked_until = key.locked_until
                    orm_model.locked_by = key.locked_by
                    orm_model.request_id = key.request_id
                    orm_model.correlation_id = key.correlation_id

                    if key.response:
                        orm_model.response_data = {
                            "status_code": key.response.status_code,
                            "headers": key.response.headers,
                            "body": key.response.body,
                        }
                    else:
                        orm_model.response_data = None

                    orm_model.save()
                    return IdempotencyKeyMapper.to_domain(orm_model)
            except IdempotencyKeyModel.DoesNotExist as exc:
                raise IdempotencyKeyNotFoundError(key=key.key) from exc

        return await _update()

    async def lock(
        self,
        key: str,
        user_id: UUID,
        locker_id: str,
        lock_duration_seconds: int = 60,
    ) -> DomainIdempotencyKey:
        now = django_timezone.now()
        locked_until = now + timedelta(seconds=lock_duration_seconds)  # ✅ Correct

        @sync_to_async
        def _lock():
            try:
                with transaction.atomic():
                    orm_model = (
                        IdempotencyKeyModel.objects
                        .select_for_update(nowait=True)
                        .get(key=key, user_id=user_id)
                    )
            except IdempotencyKeyModel.DoesNotExist as exc:
                raise IdempotencyKeyNotFoundError(key=key) from exc

            if orm_model.expires_at <= now:
                raise IdempotencyKeyExpiredError(key=key)

            if orm_model.status in (IdempotencyStatus.COMPLETED.name, IdempotencyStatus.FAILED.name):
                raise IdempotencyKeyAlreadyUsedError(key=key)

            if orm_model.locked_until and orm_model.locked_until > now:
                raise IdempotencyKeyAlreadyLockedError(key=key, locked_by=orm_model.locked_by)

            orm_model.locked_until = locked_until
            orm_model.locked_by = locker_id
            orm_model.save(update_fields=["locked_until", "locked_by", "updated_at"])
            return IdempotencyKeyMapper.to_domain(orm_model)

        return await _lock()

    async def unlock(self, key: str, user_id: UUID) -> None:
        @sync_to_async
        def _unlock():
            try:
                with transaction.atomic():
                    orm_model = IdempotencyKeyModel.objects.select_for_update().get(
                        key=key, user_id=user_id
                    )
            except IdempotencyKeyModel.DoesNotExist as exc:
                raise IdempotencyKeyNotFoundError(key=key) from exc

            if not orm_model.locked_until or orm_model.locked_until <= django_timezone.now():
                raise ValueError(f"Idempotency key '{key}' is not currently locked")

            orm_model.locked_until = None
            orm_model.locked_by = None
            orm_model.save(update_fields=["locked_until", "locked_by", "updated_at"])

        await _unlock()

    async def force_unlock(self, key: str, user_id: UUID) -> None:
        @sync_to_async
        def _force_unlock():
            try:
                with transaction.atomic():
                    orm_model = IdempotencyKeyModel.objects.select_for_update().get(
                        key=key, user_id=user_id
                    )
            except IdempotencyKeyModel.DoesNotExist as exc:
                raise IdempotencyKeyNotFoundError(key=key) from exc

            if orm_model.locked_until and orm_model.locked_until > django_timezone.now():
                raise ValueError(f"Cannot force unlock non-expired lock for key '{key}'")

            orm_model.locked_until = None
            orm_model.locked_by = None
            orm_model.save(update_fields=["locked_until", "locked_by", "updated_at"])

        await _force_unlock()

    async def delete(self, key: str, user_id: UUID) -> None:
        @sync_to_async
        def _delete():
            try:
                orm_model = IdempotencyKeyModel.objects.get(key=key, user_id=user_id)
                orm_model.delete()
            except IdempotencyKeyModel.DoesNotExist as exc:
                raise IdempotencyKeyNotFoundError(key=key) from exc

        await _delete()

    async def delete_expired_before(self, cutoff: datetime) -> int:
        deleted_count, _ = await IdempotencyKeyModel.objects.filter(expires_at__lt=cutoff).adelete()
        return deleted_count

    async def delete_by_user(self, user_id: UUID) -> int:
        deleted_count, _ = await IdempotencyKeyModel.objects.filter(user_id=user_id).adelete()
        return deleted_count

    async def claim_or_replay(
        self,
        key: str,
        user_id: UUID,
        fingerprint: str,
        locker_id: str,
        lease_duration_seconds: int = 30,
    ) -> IdempotencyClaimResult:
        @sync_to_async
        def _claim_or_replay():
            now = django_timezone.now()
            try:
                with transaction.atomic():
                    orm_model = (
                        IdempotencyKeyModel.objects
                        .select_for_update(nowait=True)
                        .get(key=key, user_id=user_id)
                    )
            except IdempotencyKeyModel.DoesNotExist:
                # First use: create new pending key
                domain_key = DomainIdempotencyKey.create_new(
                    key=key,
                    user_id=user_id,
                    fingerprint=fingerprint,
                    expires_at=now + timedelta(hours=24),
                )
                domain_key.mark_in_progress(locker_id, lease_duration_seconds)
                orm_model = IdempotencyKeyMapper.to_orm(domain_key)
                orm_model.save(force_insert=True)
                return IdempotencyAcquiredResult(key=IdempotencyKeyMapper.to_domain(orm_model))

            # Key exists — validate state
            if orm_model.expires_at <= now:
                return IdempotencyConflictResult(reason="key_expired")

            if orm_model.status in (IdempotencyStatus.COMPLETED.name, IdempotencyStatus.FAILED.name):
                if orm_model.fingerprint != fingerprint:
                    return IdempotencyConflictResult(reason="fingerprint_mismatch")
                if not orm_model.response_data:
                    raise IdempotencyResponseMissingError(key=key)
                response = StoredResponse(
                    status_code=orm_model.response_data["status_code"],
                    headers=orm_model.response_data.get("headers", {}),
                    body=orm_model.response_data.get("body", {}),
                )
                return IdempotencyReplayResult(response=response)

            # At this point: status == PENDING
            if orm_model.fingerprint != fingerprint:
                return IdempotencyConflictResult(reason="fingerprint_mismatch")

            # Check lock status
            if orm_model.locked_until and orm_model.locked_until > now:
                # Active lock held by another (or crashed) request
                return IdempotencyConflictResult(reason="already_locked")

            # Lock is missing or expired → we can steal/recover it
            orm_model.locked_until = now + timedelta(seconds=lease_duration_seconds)
            orm_model.locked_by = locker_id
            orm_model.save(update_fields=["locked_until", "locked_by", "updated_at"])

            return IdempotencyAcquiredResult(key=IdempotencyKeyMapper.to_domain(orm_model))
        return await _claim_or_replay()