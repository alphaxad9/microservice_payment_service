# src/domain/idempotency/services/idempotency_command_service.py

from __future__ import annotations

from abc import ABC
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

from src.domain.idempotency.models import (
    IdempotencyKey,
    compute_fingerprint,
)
from src.domain.idempotency.exceptions import (
    InvalidIdempotencyKeyFormatError,
    IdempotencyKeyTooLongError,
    IdempotencyKeyExpiredError,
    IdempotencyKeyAlreadyUsedError,
    IdempotencyKeyInProgressError,
    IdempotencyKeyReuseWithDifferentPayloadError,
    IdempotencyKeyExpirationInPastError,
)
from src.application.idempotency.services.interfaces.idempotency_interface import (
    IdempotencyCommandServiceInterface,
)
from src.domain.idempotency.repository import (
    IdempotencyKeyCommandRepository,
)
from src.domain.idempotency.repository import (
    IdempotencyKeyQueryRepository,StoredResponse, IdempotencyReplayResult, IdempotencyConflictResult
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyCommandService(IdempotencyCommandServiceInterface, ABC):
    """
    Concrete implementation of the write-side idempotency service.
    Coordinates between command & query repositories while enforcing domain rules.
    """

    MAX_KEY_LENGTH = 255
    DEFAULT_TTL_HOURS = 24
    DEFAULT_LOCK_LEASE_SECONDS = 30

    def __init__(
        self,
        command_repo: IdempotencyKeyCommandRepository,
        query_repo: IdempotencyKeyQueryRepository,
    ) -> None:
        self.command_repo = command_repo
        self.query_repo = query_repo

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
            """
            Create a new idempotency key entry with a given fingerprint.
            This method is now intended mainly for administrative/manual use.
            Normal flows should use begin_request_processing() instead.
            """
            if not key or not key.strip():
                raise InvalidIdempotencyKeyFormatError(key=key)

            key = key.strip()
            if len(key) > self.MAX_KEY_LENGTH:
                raise IdempotencyKeyTooLongError(key=key, max_length=self.MAX_KEY_LENGTH)

            expires_at = _now_utc() + timedelta(hours=ttl_hours)
            if expires_at <= _now_utc():
                raise IdempotencyKeyExpirationInPastError(expires_at=expires_at.isoformat())

            new_key = IdempotencyKey.create_new(
                key=key,
                user_id=user_id,
                fingerprint=fingerprint,
                expires_at=expires_at,
                # You may also want to store request metadata if needed:
                # request_id=..., correlation_id=...
            )

            try:
                return await self.command_repo.create(new_key)
            except Exception as exc:
                # Race condition: someone created it meanwhile
                existing = await self.query_repo.get_by_key_and_user(key=key, user_id=user_id)
                if existing is None:
                    # Very unlikely — re-raise original error
                    raise

                if existing.fingerprint != fingerprint:
                    raise IdempotencyKeyReuseWithDifferentPayloadError(key=key) from exc

                # Same fingerprint → safe to return existing
                return existing

    async def process_request(
        self,
        key: str,
        user_id: UUID,
        locker_id: str,
        fingerprint: str = ""   # ← add parameter (can be empty during transition)
    ) -> Optional[Dict[str, Any]]:
        # Fast-path: check for replayable response without locking
        replay_response = await self.query_repo.get_replay_response(
            key=key, user_id=user_id
        )
        if replay_response is not None:
            return {
                "status_code": replay_response.status_code,
                "headers": replay_response.headers,
                "body": replay_response.body,
            }

        # Attempt atomic claim — now pass real fingerprint
        result = await self.command_repo.claim_or_replay(
            key=key,
            user_id=user_id,
            fingerprint=fingerprint,          # ← most important change!
            locker_id=locker_id,
            lease_duration_seconds=self.DEFAULT_LOCK_LEASE_SECONDS,
        )

        # Handle replay from claim_or_replay (in case race condition)
        if isinstance(result, IdempotencyReplayResult):
            resp = result.response
            return {
                "status_code": resp.status_code,
                "headers": resp.headers,
                "body": resp.body,
            }

        if isinstance(result, IdempotencyConflictResult):
            if result.reason == "already_locked":
                raise IdempotencyKeyInProgressError(key=key)
            # Other conflicts (expired, mismatch) should be treated as client errors
            if result.reason == "key_expired":
                raise IdempotencyKeyExpiredError(key=key)
            if result.reason == "fingerprint_mismatch":
                raise IdempotencyKeyReuseWithDifferentPayloadError(key=key)
            # Fallback
            raise IdempotencyKeyInProgressError(key=key)  # safe default

        # Successfully acquired (IdempotencyAcquiredResult)
        return None

    async def record_success(
        self,
        key: str,
        user_id: UUID,
        status_code: int,
        headers: Dict[str, str],
        body: Dict[str, Any],
    ) -> None:
        ikey = await self.query_repo.get_by_key_and_user(key=key, user_id=user_id)

        if ikey.is_expired():
            raise IdempotencyKeyExpiredError(key=key)
        if not ikey.is_pending():
            raise IdempotencyKeyAlreadyUsedError(key=key)

        ikey.record_success(status_code=status_code, headers=headers, body=body)
        await self.command_repo.update(ikey)

    async def record_failure(
        self,
        key: str,
        user_id: UUID,
        status_code: int,
        headers: Dict[str, str],
        body: Dict[str, Any],
    ) -> None:
        ikey = await self.query_repo.get_by_key_and_user(key=key, user_id=user_id)

        if ikey.is_expired():
            raise IdempotencyKeyExpiredError(key=key)
        if not ikey.is_pending():
            raise IdempotencyKeyAlreadyUsedError(key=key)

        ikey.record_failure(status_code=status_code, headers=headers, body=body)
        await self.command_repo.update(ikey)

    async def cleanup_expired_keys(self, older_than_hours: int = 24) -> int:
        cutoff = _now_utc() - timedelta(hours=older_than_hours)
        return await self.command_repo.delete_expired_before(cutoff=cutoff)

    async def delete_user_keys(self, user_id: UUID) -> int:
        return await self.command_repo.delete_by_user(user_id=user_id)