# src/application/idempotency/handlers/command_handlers.py
from __future__ import annotations

from typing import Dict, Any, Optional
from uuid import UUID

import logging

from src.application.idempotency.services.interfaces.idempotency_interface import (
    IdempotencyCommandServiceInterface,
)
from src.domain.idempotency.models import IdempotencyKey, compute_fingerprint
from src.domain.idempotency.exceptions import (
    IdempotencyKeyNotFoundError,
    IdempotencyKeyReuseWithDifferentPayloadError,
    IdempotencyKeyInProgressError
)

logger = logging.getLogger(__name__)

class IdempotencyCommandHandler:
    """
    Async-only command handler for idempotency operations.
    Delegates all logic to the injected async service interface.
    """

    def __init__(self, command_service: IdempotencyCommandServiceInterface):
        logger.info("[⚡] IdempotencyCommandHandler initialized")
        self._commands = command_service

    async def create_idempotency_key(
        self,
        key: str,
        user_id: UUID,
        payload: Dict[str, Any],
        ttl_hours: int = 24,
        request_method: str | None = None,
        request_path: str | None = None,
        client_ip: str | None = None,
    ) -> IdempotencyKey:
        """
        DEPRECATED: This method exists only for manual/administrative use or legacy compatibility.
        In normal business flows, prefer using begin_request_processing() which handles creation
        and validation in a single atomic step and avoids race conditions.
        """
        logger.warning(
            "[⚠️ DEPRECATED] create_idempotency_key() called for key: %s - "
            "Use begin_request_processing() instead for production flows", key
        )

        fingerprint = compute_fingerprint(payload)
        logger.info("[🔑] Fingerprint generated for deprecated creation: %s", fingerprint)

        try:
            logger.info("[🛠️] Attempting to create idempotency key (deprecated path)")
            result = await self._commands.create_key(
                key=key,
                user_id=user_id,
                fingerprint=fingerprint,
                ttl_hours=ttl_hours,
                request_method=request_method,
                request_path=request_path,
                client_ip=client_ip,
            )
            logger.info("[✅] Deprecated key creation successful for key: %s", key)
            return result
        except IdempotencyKeyReuseWithDifferentPayloadError:
            logger.warning("[❌] Fingerprint mismatch in deprecated creation for key: %s", key)
            raise
        except Exception as exc:
            logger.exception("[💥] Failed in deprecated create_idempotency_key for key %s", key)
            raise RuntimeError(
                f"Failed to create idempotency key '{key}' for user {user_id}"
            ) from exc

    async def begin_request_processing(
        self,
        key: str,
        user_id: UUID,
        locker_id: str,
        fingerprint: str = ""   # Default empty for transition/compatibility
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to claim and begin processing using an idempotency key.
        """
        logger.info("[🚀 BEGIN] Starting begin_request_processing for key: %s | user: %s | locker: %s",
                    key, user_id, locker_id)
        print("🔥🔥 BEGIN PROCESSING KEY:", key)

        if fingerprint:
            logger.info("[🔍] Fingerprint provided: %s", fingerprint)
        else:
            logger.info("[ℹ️] No fingerprint provided (transition mode)")

        try:
            logger.info("[🔒] Calling process_request in service layer")
            result = await self._commands.process_request(
                key=key,
                user_id=user_id,
                locker_id=locker_id,
                fingerprint=fingerprint
            )
            logger.info("[🌟] process_request completed successfully for key: %s | result: %s",
                        key, "cached" if result is not None else "new/locked")
            return result
        except IdempotencyKeyInProgressError:
            logger.info("[⏳] Key already in progress: %s", key)
            raise
        except IdempotencyKeyNotFoundError:
            logger.info("[🆕] Key not found → will be created: %s", key)
            raise
        except IdempotencyKeyReuseWithDifferentPayloadError:
            logger.warning("[⚡ CONFLICT] Fingerprint mismatch for existing key: %s", key)
            raise
        except Exception as exc:
            logger.exception("[💣] Unexpected error in begin_request_processing for key %s", key)
            raise RuntimeError(
                f"Idempotency processing failed for key '{key}' (user {user_id})"
            ) from exc

    async def record_successful_response(
        self,
        key: str,
        user_id: UUID,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a successful outcome and unlock the key."""
        logger.info("[🏆 SUCCESS] Recording successful response for key: %s", key)
        if headers is None:
            headers = {}
        if body is None:
            body = {}

        try:
            logger.info("[📝] Calling record_success in service")
            await self._commands.record_success(
                key=key,
                user_id=user_id,
                status_code=status_code,
                headers=headers,
                body=body,
            )
            logger.info("[🔓] Success recorded and key unlocked: %s", key)
        except IdempotencyKeyNotFoundError:
            logger.warning("[⚠️] Key not found when trying to record success: %s", key)
            raise
        except Exception as exc:
            logger.exception("[❗] Failed to record success for key %s", key)
            raise RuntimeError(
                f"Failed to record success for idempotency key '{key}'"
            ) from exc

    async def record_failed_response(
        self,
        key: str,
        user_id: UUID,
        status_code: int = 400,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a failed outcome (still replayable) and unlock."""
        logger.info("[❌ FAILURE] Recording failed response for key: %s", key)
        if headers is None:
            headers = {}
        if body is None:
            body = {"error": "Processing failed"}

        try:
            logger.info("[📝] Calling record_failure in service")
            await self._commands.record_failure(
                key=key,
                user_id=user_id,
                status_code=status_code,
                headers=headers,
                body=body,
            )
            logger.info("[🔓] Failure recorded and key unlocked: %s", key)
        except IdempotencyKeyNotFoundError:
            logger.warning("[⚠️] Key not found when trying to record failure: %s", key)
            raise
        except Exception as exc:
            logger.exception("[❗] Failed to record failure for key %s", key)
            raise RuntimeError(
                f"Failed to record failure for idempotency key '{key}'"
            ) from exc

    async def cleanup_expired_keys(self, older_than_hours: int = 24) -> int:
        """Delete expired keys older than given hours. Useful for cron jobs."""
        logger.info("[🧹 CLEANUP] Starting cleanup of keys older than %s hours", older_than_hours)
        try:
            count = await self._commands.cleanup_expired_keys(older_than_hours=older_than_hours)
            logger.info("[🧹 DONE] Cleaned up %s expired idempotency keys", count)
            return count
        except Exception as exc:
            logger.exception("[💥] Cleanup of expired keys failed")
            raise RuntimeError("Failed to clean up expired idempotency keys") from exc

    async def delete_all_keys_for_user(self, user_id: UUID) -> int:
        """Delete all idempotency keys belonging to a user (e.g., on account deletion)."""
        logger.info("[🗑️ DELETE] Deleting ALL idempotency keys for user: %s", user_id)
        try:
            count = await self._commands.delete_user_keys(user_id=user_id)
            logger.info("[🗑️ DONE] Deleted %s keys for user %s", count, user_id)
            return count
        except Exception as exc:
            logger.exception("[💥] Failed to delete keys for user %s", user_id)
            raise RuntimeError(f"Failed to delete keys for user {user_id}") from exc