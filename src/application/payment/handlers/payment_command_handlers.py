# src/application/payment/handlers/payment_command_handlers.py
# (Assuming this is the file path based on imports and context; adjust if needed)

from __future__ import annotations
from decimal import Decimal
from typing import Callable, Dict, Any, Optional
from uuid import UUID, uuid4
from collections.abc import Awaitable
import logging  # ← ADDED FOR LOGGING
from django.db import connection
from datetime import datetime  # ← ADDED IMPORT


from src.application.payment.services.interfaces.payment_command_service_interface import PaymentCommandServiceInterface
from src.application.payment.services.interfaces.payment_query_interface import PaymentQueryServiceInterface
from src.application.idempotency.handlers.idempotency_command_handlers import IdempotencyCommandHandler
from src.domain.apps.payment.models import PaymentView
from src.domain.apps.payment.exceptions import (
    PaymentDomainError,
)
from src.domain.idempotency.exceptions import (
    IdempotencyKeyReuseWithDifferentPayloadError,
    IdempotencyKeyInProgressError, # ← ADDED THIS IMPORT
)
from src.domain.idempotency.models import compute_fingerprint  # ← ADDED IMPORT FOR FINGERPRINT

logger = logging.getLogger(__name__)  # ← ADDED LOGGER SETUP

print("🔥🔥 USING DB:", connection.settings_dict["NAME"])

class IdempotentPaymentExecutor:
    """
    Async idempotency wrapper for payment creation commands (deposit, withdrawal, booking, refund).
    Ensures exactly-once semantics for payment initiation.
    """
    def __init__(self, idempotency_commands: IdempotencyCommandHandler):
        logger.info("[🔥] IdempotentPaymentExecutor initialized")
        self._idempotency = idempotency_commands
 # src/application/payment/handlers/payment_command_handlers.py
# (relevant part only — replace the execute_payment_creation method)



















    async def execute_payment_creation(
            self,
            *,
            idempotency_key: str,
            user_id: UUID,
            payload: Dict[str, Any],
            execute_command: Callable[[], Awaitable[UUID]],
            fetch_view: Callable[[UUID], Awaitable[PaymentView]],
        ) -> PaymentView:
            logger.info("[🔥🔥] Starting execute_payment_creation with idempotency_key %s", idempotency_key)
            locker_id = str(uuid4())
            logger.info("[🌟] Locker ID generated: %s", locker_id)
            
            fingerprint = compute_fingerprint(payload)
            logger.info("[⭐] Fingerprint computed: %s", fingerprint)
            
            try:
                logger.info("[🚀] Attempting to begin request processing")
                stored: Optional[Dict[str, Any]] = await self._idempotency.begin_request_processing(
                    key=idempotency_key,
                    user_id=user_id,
                    locker_id=locker_id,
                    fingerprint=fingerprint,
                )
                logger.info("[🌈] Request processing begun, stored: %s", stored)
            except IdempotencyKeyReuseWithDifferentPayloadError as e:
                logger.warning("[💥] Idempotency conflict: %s", str(e))
                raise PaymentDomainError(
                    "Idempotency conflict: request parameters do not match previous use of this key"
                ) from e
            except IdempotencyKeyInProgressError:
                logger.info("[🎉] Idempotency key in progress")
                raise PaymentDomainError(
                    "This request is already being processed. Please retry in a few seconds."
                ) from None
            except Exception as exc:
                logger.exception("[🔍] Unexpected idempotency error for key %s", idempotency_key)
                raise PaymentDomainError("Idempotency processing failed") from exc

            # ── Replay case ────────────────────────────────────────────────
            if stored is not None:
                logger.info("[📊] Stored response found, entering replay case")
                body: Dict[str, Any] = stored.get("body", {})
                if "error" in body:
                    logger.info("[✅] Replaying stored error")
                    raise PaymentDomainError(body["error"])
                if "payment_id" not in body:
                    logger.info("[❌] Invalid cached response: missing payment_id")
                    raise PaymentDomainError("Invalid cached response: missing payment_id")
                
                payment_id = UUID(body["payment_id"])
                logger.info("[🛡️] Payment ID from stored: %s", payment_id)
                return await fetch_view(payment_id)

            # ── First-time execution ───────────────────────────────────────
            try:
                logger.info("[💰] Entering first-time execution")
                payment_id: UUID = await execute_command()
                logger.info("[📦] Command executed, payment_id: %s", payment_id)
                
                # ✅ Build complete PaymentView with ALL required fields
                now = datetime.now()  # or use timezone.now() if using Django timezone support
                result_view = PaymentView(
                    payment_id=payment_id,
                    wallet_id=UUID(payload["wallet_id"]),          # ← Extract from payload
                    user_id=UUID(payload["user_id"]),              # ← Extract from payload
                    amount=payload["amount"],                      # Already stringified
                    currency=payload["currency"],
                    payment_type=payload.get("type", "deposit"),   # ← e.g., "deposit", "withdrawal"
                    payment_method=payload["payment_method"],      # ← Extract from payload
                    status="PENDING",
                    reference_id=UUID(payload["reference_id"]) if payload.get("reference_id") else None,
                    description=payload.get("description") or "",
                    created_at=now,
                    updated_at=now,
                )
                logger.info("[🛠️] Payment view constructed with all required fields")

                # Record success → unlock + enable future replay
                logger.info("[⚙️] Recording idempotency success for key %s", idempotency_key)
                await self._idempotency.record_successful_response(
                    key=idempotency_key,
                    user_id=user_id,
                    body={
                        "payment_id": str(result_view.payment_id),
                        "status": result_view.status,
                        "amount": str(result_view.amount),
                        "currency": result_view.currency,
                    },
                )
                logger.info("[🏆] Success recorded")
                return result_view

            except Exception as exc:
                logger.info("[🚫] Recording idempotency failure for key %s: %s", 
                            idempotency_key, str(exc))
                try:
                    await self._idempotency.record_failed_response(
                        key=idempotency_key,
                        user_id=user_id,
                        body={"error": str(exc)},
                    )
                    logger.info("[🔑] Failure recorded")
                except Exception:
                    logger.info("[🕵️] Failed to record failure, ignoring to not mask original error")
                    pass
                raise



class PaymentCommandHandler:
    """
    Async orchestration layer for payment commands.
    Applies idempotency only to *creation* commands (deposit, withdrawal, etc.).
    Other state transitions (succeed, fail, cancel) are inherently idempotent via domain rules.
    """
    def __init__(
        self,
        command_service: PaymentCommandServiceInterface,
        query_service: PaymentQueryServiceInterface,
        idempotency_commands: IdempotencyCommandHandler,
    ):
        logger.info("[🌻] PaymentCommandHandler initialized")
        self._commands = command_service
        self._queries = query_service
        self._idempotent_executor = IdempotentPaymentExecutor(idempotency_commands)
    async def create_deposit(
        self,
        *,
        idempotency_key: str,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        reference_id: Optional[UUID] = None,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> PaymentView:
        logger.info("[🌼] Starting create_deposit with idempotency_key %s", idempotency_key)
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "user_id": str(user_id),
            "amount": str(amount),
            "currency": currency,
            "payment_method": payment_method,
            "reference_id": str(reference_id) if reference_id else None,
            "description": description or "",
            "payment_id": str(payment_id) if payment_id else None,
            "type": "deposit",
        }
        logger.info("[🌹] Payload prepared for deposit")
        async def _execute() -> UUID:
            logger.info("[🥀] Preparing to execute create_deposit command")
            try:
                return await self._commands.create_deposit(
                    wallet_id=wallet_id,
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    payment_method=payment_method,
                    reference_id=reference_id,
                    description=description,
                    payment_id=payment_id,
                )
            except PaymentDomainError:
                logger.info("[🌷] PaymentDomainError in create_deposit")
                raise
            except Exception as exc:
                logger.info("[🌸] General exception in create_deposit: %s", str(exc))
                raise PaymentDomainError("Failed to create deposit") from exc
        logger.info("[🌺] Execute function defined for deposit")
        return await self._idempotent_executor.execute_payment_creation(
            idempotency_key=idempotency_key,
            user_id=user_id,
            payload=payload,
            execute_command=_execute,
            fetch_view=self._queries.get_payment,
        )
    async def create_withdrawal(
        self,
        *,
        idempotency_key: str,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        reference_id: Optional[UUID] = None,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> PaymentView:
        logger.info("[🍀] Starting create_withdrawal with idempotency_key %s", idempotency_key)
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "user_id": str(user_id),
            "amount": str(amount),
            "currency": currency,
            "payment_method": payment_method,
            "reference_id": str(reference_id) if reference_id else None,
            "description": description or "",
            "payment_id": str(payment_id) if payment_id else None,
            "type": "withdrawal",
        }
        logger.info("[🍁] Payload prepared for withdrawal")
        async def _execute() -> UUID:
            logger.info("[🍂] Preparing to execute create_withdrawal command")
            try:
                return await self._commands.create_withdrawal(
                    wallet_id=wallet_id,
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    payment_method=payment_method,
                    reference_id=reference_id,
                    description=description,
                    payment_id=payment_id,
                )
            except PaymentDomainError:
                logger.info("[🍃] PaymentDomainError in create_withdrawal")
                raise
            except Exception as exc:
                logger.info("[🍄] General exception in create_withdrawal: %s", str(exc))
                raise PaymentDomainError("Failed to create withdrawal") from exc
        logger.info("[🍅] Execute function defined for withdrawal")
        return await self._idempotent_executor.execute_payment_creation(
            idempotency_key=idempotency_key,
            user_id=user_id,
            payload=payload,
            execute_command=_execute,
            fetch_view=self._queries.get_payment,
        )
 

    async def create_payment_for_booking(
        self,
        *,
        idempotency_key: str,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        booking_id: UUID,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> PaymentView:
        logger.info("[🍀] Starting create_payment_for_booking with idempotency_key %s", idempotency_key)
        
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "user_id": str(user_id),
            "amount": str(amount),
            "currency": currency,
            "payment_method": payment_method,
            "booking_id": str(booking_id),
            "description": description or "",
            "payment_id": str(payment_id) if payment_id else None,
            "type": "booking_payment",
        }
        logger.info("[🍁] Payload prepared for booking payment")

        async def _execute() -> UUID:
            try:
                logger.info("[🥀] Executing create_payment_for_booking command")
                return await self._commands.create_payment_for_booking(
                    wallet_id=wallet_id,
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    payment_method=payment_method,
                    booking_id=booking_id,
                    description=description,
                    payment_id=payment_id,
                )
            except PaymentDomainError as domain_exc:
                logger.warning("[🌷] Domain error in booking payment: %s", str(domain_exc))
                raise
            except Exception as exc:
                # ── THIS IS THE CRITICAL CHANGE ──
                logger.exception("[🔥🔥 REAL ERROR] Failed in create_payment_for_booking command")
                # Optionally print full traceback to console for immediate visibility
                import traceback
                traceback.print_exc()
                # Re-raise the original exception so it bubbles up properly
                raise  # ← Do NOT wrap in PaymentDomainError here anymore

        logger.info("[🌺] Execute function defined for booking payment")
        
        return await self._idempotent_executor.execute_payment_creation(
            idempotency_key=idempotency_key,
            user_id=user_id,
            payload=payload,
            execute_command=_execute,
            fetch_view=self._queries.get_payment,
        )
    async def create_refund(
        self,
        *,
        idempotency_key: str,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        original_payment_id: UUID,
        refund_id: Optional[UUID] = None,
        description: Optional[str] = None,
    ) -> PaymentView:
        payload: Dict[str, Any] = {
            "wallet_id": str(wallet_id),
            "user_id": str(user_id),
            "amount": str(amount),
            "currency": currency,
            "original_payment_id": str(original_payment_id),
            "refund_id": str(refund_id) if refund_id else None,
            "description": description or "",
            "type": "refund",
        }

        async def _execute() -> UUID:
            try:
                return await self._commands.create_refund(
                    wallet_id=wallet_id,
                    user_id=user_id,
                    amount=amount,
                    currency=currency,
                    original_payment_id=original_payment_id,
                    refund_id=refund_id,
                    description=description,
                )
            except PaymentDomainError:
                raise
            except Exception as exc:
                raise PaymentDomainError("Failed to create refund") from exc

        return await self._idempotent_executor.execute_payment_creation(
            idempotency_key=idempotency_key,
            user_id=user_id,
            payload=payload,
            execute_command=_execute,
            fetch_view=self._queries.get_payment,
        )

    # -------------------------
    # Non-Creation Commands (no idempotency key needed)
    # -------------------------

    async def process_payment(self, payment_id: UUID) -> None:
        try:
            await self._commands.process_payment(payment_id)
        except PaymentDomainError:
            raise
        except Exception as exc:
            raise PaymentDomainError(f"Failed to process payment {payment_id}") from exc

    async def succeed_payment(self, payment_id: UUID) -> None:
        try:
            await self._commands.succeed_payment(payment_id)
        except PaymentDomainError:
            raise
        except Exception as exc:
            raise PaymentDomainError(f"Failed to succeed payment {payment_id}") from exc

    async def fail_payment(self, payment_id: UUID, reason: Optional[str] = None) -> None:
        try:
            await self._commands.fail_payment(payment_id, reason)
        except PaymentDomainError:
            raise
        except Exception as exc:
            raise PaymentDomainError(f"Failed to fail payment {payment_id}") from exc

    async def cancel_payment(self, payment_id: UUID) -> None:
        try:
            await self._commands.cancel_payment(payment_id)
        except PaymentDomainError:
            raise
        except Exception as exc:
            raise PaymentDomainError(f"Failed to cancel payment {payment_id}") from exc

    async def mark_payment_as_refunded(self, payment_id: UUID, refund_id: UUID) -> None:
        try:
            await self._commands.mark_payment_as_refunded(payment_id, refund_id)
        except PaymentDomainError:
            raise
        except Exception as exc:
            raise PaymentDomainError(
                f"Failed to mark payment {payment_id} as refunded by {refund_id}"
            ) from exc
        
