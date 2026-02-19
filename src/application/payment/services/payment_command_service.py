# src/application/payment/services/payment_command_service.py

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from src.domain.apps.payment.aggregate import PaymentAggregate
from src.domain.apps.payment.models import PaymentMethod  # <-- ADD THIS IMPORT
from src.domain.apps.payment.exceptions import (
    PaymentDomainError,
    PaymentNotFoundError,
    InvalidPaymentAmountError,
    PaymentMethodNotSupportedError,
    PaymentAlreadyProcessedError,
    PaymentNotProcessableError,
    RefundAmountExceedsOriginalError,  # <-- Also needed for refund validation
)
from src.domain.apps.payment.repository import PaymentCommandRepository
from src.application.payment.services.interfaces.payment_command_service_interface import PaymentCommandServiceInterface

logger = logging.getLogger(__name__)


class PaymentCommandService(PaymentCommandServiceInterface):
    """
    Concrete implementation of the command-side payment service with full domain validation
    and coordination between aggregates and the command repository.
    """

    def __init__(self, repo: PaymentCommandRepository):
        self._repo = repo

    def _parse_payment_method(self, method_str: str) -> PaymentMethod:
        """Convert string to PaymentMethod enum, with clear error."""
        try:
            return PaymentMethod(method_str)
        except ValueError as e:
            raise ValueError(f"Invalid payment method: '{method_str}'. Must be one of: {[m.value for m in PaymentMethod]}") from e

    # ----------------------------
    # Creation Commands
    # ----------------------------

    async def create_deposit(
        self,
        *,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        reference_id: Optional[UUID] = None,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> UUID:
        logger.info("[🌻] am called to create a payment")
        if not wallet_id or not user_id:
            raise ValueError("wallet_id and user_id are required")
        if not currency or not currency.strip():
            raise ValueError("Currency is required")
        if not payment_method or not payment_method.strip():
            raise ValueError("Payment method is required")

        parsed_method = self._parse_payment_method(payment_method)

        try:
            aggregate = PaymentAggregate.create_deposit(
                wallet_id=wallet_id,
                user_id=user_id,
                amount=amount,
                currency=currency,
                payment_method=parsed_method,
                reference_id=reference_id,
                description=description,
                payment_id=payment_id,
            )
        except (InvalidPaymentAmountError, PaymentMethodNotSupportedError) as exc:
            logger.error("Failed to create deposit payment: %s", exc)
            raise exc
        except Exception as exc:
            logger.error("Unexpected error creating deposit payment: %s", exc)
            raise PaymentDomainError("Invalid deposit parameters") from exc

        await self._create_aggregate(aggregate, "deposit")
        return aggregate.payment_id

    async def create_withdrawal(
        self,
        *,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        reference_id: Optional[UUID] = None,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> UUID:
        if not wallet_id or not user_id:
            raise ValueError("wallet_id and user_id are required")
        if not currency or not currency.strip():
            raise ValueError("Currency is required")
        if not payment_method or not payment_method.strip():
            raise ValueError("Payment method is required")

        parsed_method = self._parse_payment_method(payment_method)

        try:
            aggregate = PaymentAggregate.create_withdrawal(
                wallet_id=wallet_id,
                user_id=user_id,
                amount=amount,
                currency=currency,
                payment_method=parsed_method,
                reference_id=reference_id,
                description=description,
                payment_id=payment_id,
            )
        except (InvalidPaymentAmountError, PaymentMethodNotSupportedError) as exc:
            logger.error("Failed to create withdrawal payment: %s", exc)
            raise exc
        except Exception as exc:
            logger.error("Unexpected error creating withdrawal payment: %s", exc)
            raise PaymentDomainError("Invalid withdrawal parameters") from exc

        await self._create_aggregate(aggregate, "withdrawal")
        return aggregate.payment_id

    async def create_payment_for_booking(
        self,
        *,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        booking_id: UUID,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> UUID:
        if not wallet_id or not user_id or not booking_id:
            raise ValueError("wallet_id, user_id, and booking_id are required")
        if not currency or not currency.strip():
            raise ValueError("Currency is required")
        if not payment_method or not payment_method.strip():
            raise ValueError("Payment method is required")

        parsed_method = self._parse_payment_method(payment_method)

        try:
            aggregate = PaymentAggregate.create_payment_for_booking(
                wallet_id=wallet_id,
                user_id=user_id,
                amount=amount,
                currency=currency,
                payment_method=parsed_method,
                booking_id=booking_id,
                description=description,
                payment_id=payment_id,
            )
        except InvalidPaymentAmountError as exc:
            logger.error("Failed to create booking payment: %s", exc)
            raise exc
        except Exception as exc:
            logger.error("Unexpected error creating booking payment: %s", exc)
            raise PaymentDomainError("Invalid booking payment parameters") from exc

        await self._create_aggregate(aggregate, "booking payment")
        return aggregate.payment_id

    async def create_refund(
        self,
        *,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        original_payment_id: UUID,
        refund_id: Optional[UUID] = None,
        description: Optional[str] = None,
    ) -> UUID:
        if not wallet_id or not user_id or not original_payment_id:
            raise ValueError("wallet_id, user_id, and original_payment_id are required")
        if not currency or not currency.strip():
            raise ValueError("Currency is required")

        # Load original payment to validate it exists and can be refunded
        try:
            original_payment = await self._repo.load(original_payment_id)
        except PaymentNotFoundError:
            logger.error("Original payment %s not found for refund", original_payment_id)
            raise
        except Exception as exc:
            logger.error("Error loading original payment %s: %s", original_payment_id, exc)
            raise PaymentNotFoundError(payment_id=original_payment_id) from exc

        # Validate refund amount does not exceed original
        if amount > original_payment.amount:
            raise RefundAmountExceedsOriginalError(
                original_payment_id=original_payment_id,
                original_amount=original_payment.amount,
                refund_amount=amount,
                currency=currency,
            )

        # Note: Refunds internally use PaymentMethod.WALLET — no need to parse input method
        # But to keep interface consistent, we still accept it (though ignore it)
        # However, per your domain model, refunds always use WALLET method.
        # So we don't use the passed payment_method here.

        try:
            aggregate = PaymentAggregate.create_refund(
                wallet_id=wallet_id,
                user_id=user_id,
                amount=amount,
                currency=currency,
                original_payment_id=original_payment_id,
                refund_id=refund_id,
                description=description,
            )
        except InvalidPaymentAmountError as exc:
            logger.error("Failed to create refund payment: %s", exc)
            raise exc
        except Exception as exc:
            logger.error("Unexpected error creating refund payment: %s", exc)
            raise PaymentDomainError("Invalid refund parameters") from exc

        await self._create_aggregate(aggregate, "refund")
        return aggregate.payment_id

    # ----------------------------
    # State Transition Commands
    # ----------------------------

    async def process_payment(self, payment_id: UUID) -> None:
        if not payment_id:
            raise ValueError("payment_id is required")

        aggregate = await self._load_payment(payment_id)

        try:
            aggregate.process()
        except (PaymentAlreadyProcessedError, PaymentNotProcessableError) as exc:
            raise exc
        except Exception as exc:
            logger.error("Unexpected error processing payment %s: %s", payment_id, exc)
            raise PaymentDomainError("Failed to process payment") from exc

        await self._save_aggregate(aggregate, "process_payment")

    async def succeed_payment(self, payment_id: UUID) -> None:
        if not payment_id:
            raise ValueError("payment_id is required")

        aggregate = await self._load_payment(payment_id)

        try:
            aggregate.succeed()
        except (PaymentAlreadyProcessedError, PaymentNotProcessableError) as exc:
            raise exc
        except Exception as exc:
            logger.error("Unexpected error succeeding payment %s: %s", payment_id, exc)
            raise PaymentDomainError("Failed to succeed payment") from exc

        await self._save_aggregate(aggregate, "succeed_payment")

    async def fail_payment(self, payment_id: UUID, reason: Optional[str] = None) -> None:
        if not payment_id:
            raise ValueError("payment_id is required")

        aggregate = await self._load_payment(payment_id)

        try:
            aggregate.fail(reason=reason)
        except (PaymentAlreadyProcessedError, PaymentNotProcessableError) as exc:
            raise exc
        except Exception as exc:
            logger.error("Unexpected error failing payment %s: %s", payment_id, exc)
            raise PaymentDomainError("Failed to fail payment") from exc

        await self._save_aggregate(aggregate, f"fail_payment (reason: {reason})")

    async def cancel_payment(self, payment_id: UUID) -> None:
        if not payment_id:
            raise ValueError("payment_id is required")

        aggregate = await self._load_payment(payment_id)

        try:
            aggregate.cancel()
        except (PaymentAlreadyProcessedError, PaymentNotProcessableError) as exc:
            raise exc
        except Exception as exc:
            logger.error("Unexpected error canceling payment %s: %s", payment_id, exc)
            raise PaymentDomainError("Failed to cancel payment") from exc

        await self._save_aggregate(aggregate, "cancel_payment")

    async def mark_payment_as_refunded(self, payment_id: UUID, refund_id: UUID) -> None:
        if not payment_id or not refund_id:
            raise ValueError("payment_id and refund_id are required")

        aggregate = await self._load_payment(payment_id)

        try:
            aggregate.mark_as_refunded(refund_id=refund_id)
        except (PaymentAlreadyProcessedError, PaymentNotProcessableError) as exc:
            raise exc
        except Exception as exc:
            logger.error("Unexpected error marking payment as refunded %s: %s", payment_id, exc)
            raise PaymentDomainError("Failed to mark payment as refunded") from exc

        await self._save_aggregate(aggregate, f"mark_payment_as_refunded (refund_id: {refund_id})")

    # ----------------------------
    # Private Helpers
    # ----------------------------

    async def _load_payment(self, payment_id: UUID) -> PaymentAggregate:
        try:
            return await self._repo.load(payment_id)
        except PaymentNotFoundError:
            raise
        except Exception as exc:
            logger.error("Unexpected error loading payment %s: %s", payment_id, exc)
            raise PaymentNotFoundError(payment_id=payment_id) from exc

    async def _create_aggregate(self, aggregate: PaymentAggregate, operation: str) -> None:
        try:
            await self._repo.create(aggregate)
            logger.info("Payment created: %s (%s)", aggregate.payment_id, operation)
        except Exception as exc:
            logger.error("Failed to create payment %s after %s: %s", aggregate.payment_id, operation, exc)
            raise RuntimeError(f"Failed to persist payment after {operation}") from exc

    async def _save_aggregate(self, aggregate: PaymentAggregate, operation: str) -> None:
        try:
            await self._repo.save(aggregate)
            logger.info("Payment %s updated: %s", aggregate.payment_id, operation)
        except Exception as exc:
            logger.error("Failed to save payment %s after %s: %s", aggregate.payment_id, operation, exc)
            raise RuntimeError(f"Failed to persist payment after {operation}") from exc