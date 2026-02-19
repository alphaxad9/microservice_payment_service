# src/domain/apps/payment/aggregate.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, List

from src.domain.apps.payment.models import (
    PaymentStatus,
    PaymentType,
    PaymentMethod,
    PaymentView,
)
from src.domain.apps.payment.events import (
    PaymentEvent,
    PaymentCreatedEvent,
    PaymentProcessedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    PaymentCancelledEvent,
    PaymentRefundedEvent,
)
from src.domain.apps.payment.exceptions import (
    PaymentAlreadyProcessedError,
    PaymentNotProcessableError,
    InvalidPaymentAmountError,
    PaymentMethodNotSupportedError,
)

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PaymentAggregate:
    # --- Identity & Core Immutable Fields ---
    payment_id: UUID
    wallet_id: UUID
    user_id: UUID
    amount: Decimal
    currency: str
    payment_type: PaymentType
    payment_method: PaymentMethod

    # --- Mutable State ---
    status: PaymentStatus = PaymentStatus.PENDING
    reference_id: Optional[UUID] = None
    description: Optional[str] = None

    # --- Metadata ---
    created_at: datetime = field(default_factory=_now_utc)
    updated_at: datetime = field(default_factory=_now_utc)
    version: int = 0

    # --- Event sourcing infrastructure ---
    _uncommitted_events: List[PaymentEvent] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.amount <= Decimal("0"):
            raise InvalidPaymentAmountError(self.amount)
        self.currency = self.currency.upper()

    # ---------- FACTORY METHODS ----------
    @classmethod
    def create_deposit(
        cls,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: PaymentMethod,
        reference_id: Optional[UUID] = None,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> "PaymentAggregate":
        if payment_method == PaymentMethod.WALLET:
            raise PaymentMethodNotSupportedError(
                method="wallet", operation="external deposit"
            )
        return cls._create_payment(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_type=PaymentType.DEPOSIT,
            payment_method=payment_method,
            reference_id=reference_id,
            description=description or "Deposit",
            payment_id=payment_id,
        )

    @classmethod
    def create_withdrawal(
        cls,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: PaymentMethod,
        reference_id: Optional[UUID] = None,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> "PaymentAggregate":
        if payment_method == PaymentMethod.WALLET:
            raise PaymentMethodNotSupportedError(
                method="wallet", operation="external withdrawal"
            )
        return cls._create_payment(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_type=PaymentType.WITHDRAWAL,
            payment_method=payment_method,
            reference_id=reference_id,
            description=description or "Withdrawal",
            payment_id=payment_id,
        )

    @classmethod
    def create_payment_for_booking(
        cls,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_method: PaymentMethod,
        booking_id: UUID,
        description: Optional[str] = None,
        payment_id: Optional[UUID] = None,
    ) -> "PaymentAggregate":
        return cls._create_payment(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_type=PaymentType.PAYMENT,
            payment_method=payment_method,
            reference_id=booking_id,
            description=description or "Booking payment",
            payment_id=payment_id,
        )

    @classmethod
    def create_refund(
        cls,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        original_payment_id: UUID,
        refund_id: Optional[UUID] = None,
        description: Optional[str] = None,
    ) -> "PaymentAggregate":
        if amount <= Decimal("0"):
            raise InvalidPaymentAmountError(amount)

        # Refunds are internal and must use WALLET method — no external choice allowed
        payment_method = PaymentMethod.WALLET

        agg = cls(
            payment_id=refund_id or uuid4(),
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency.upper(),
            payment_type=PaymentType.REFUND,
            payment_method=payment_method,
            reference_id=original_payment_id,
            description=description or "Refund",
            status=PaymentStatus.PENDING,
        )

        agg._apply(
            PaymentCreatedEvent(
                payment_id=agg.payment_id,
                wallet_id=agg.wallet_id,
                user_id=agg.user_id,
                amount=agg.amount,
                currency=agg.currency,
                payment_type=agg.payment_type.value,
                payment_method=agg.payment_method.value,
                reference_id=agg.reference_id,
                description=agg.description,
            )
        )
        return agg

    @classmethod
    def _create_payment(
        cls,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_type: PaymentType,
        payment_method: PaymentMethod,
        reference_id: Optional[UUID],
        description: Optional[str],
        payment_id: Optional[UUID] = None,
    ) -> "PaymentAggregate":
        agg = cls(
            payment_id=payment_id or uuid4(),
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency.upper(),
            payment_type=payment_type,
            payment_method=payment_method,
            reference_id=reference_id,
            description=description,
            status=PaymentStatus.PENDING,
        )

        agg._apply(
            PaymentCreatedEvent(
                payment_id=agg.payment_id,
                wallet_id=agg.wallet_id,
                user_id=agg.user_id,
                amount=agg.amount,
                currency=agg.currency,
                payment_type=agg.payment_type.value,
                payment_method=agg.payment_method.value,
                reference_id=agg.reference_id,
                description=agg.description,
            )
        )
        return agg

    # ---------- INTERNAL EVENT SOURCING ----------
    def _apply(self, event: PaymentEvent) -> None:
        """Apply event to state and record as uncommitted."""
        self.when(event)
        self._uncommitted_events.append(event)
        self.version += 1

    def when(self, event: PaymentEvent) -> None:
        """Dispatch to specific event handler."""
        handler_name = f"when_{event.__class__.__name__}"
        handler = getattr(self, handler_name, None)
        if handler is None:
            raise NotImplementedError(f"No handler for event {event.__class__.__name__}")
        handler(event)
        # Update timestamp from event if available, else now
        self.updated_at = getattr(event, "occurred_at", _now_utc())

    # ---------- EVENT HANDLERS ----------
    def when_PaymentCreatedEvent(self, event: PaymentCreatedEvent) -> None:
        self.created_at = event.occurred_at
        # Core fields are immutable; rehydration is idempotent

    def when_PaymentProcessedEvent(self, event: PaymentProcessedEvent) -> None:
        self.status = PaymentStatus.PROCESSING

    def when_PaymentSucceededEvent(self, event: PaymentSucceededEvent) -> None:
        self.status = PaymentStatus.SUCCEEDED

    def when_PaymentFailedEvent(self, event: PaymentFailedEvent) -> None:
        self.status = PaymentStatus.FAILED
        if event.failure_reason:
            self.description = f"{self.description or ''} [FAILED: {event.failure_reason}]".strip()

    def when_PaymentCancelledEvent(self, event: PaymentCancelledEvent) -> None:
        self.status = PaymentStatus.CANCELLED

    def when_PaymentRefundedEvent(self, event: PaymentRefundedEvent) -> None:
        self.status = PaymentStatus.REFUNDED

    # ---------- GUARD CLAUSES ----------
    def _ensure_pending(self) -> None:
        if self.status != PaymentStatus.PENDING:
            raise PaymentAlreadyProcessedError(self.payment_id, self.status.value)

    def _ensure_processable(self) -> None:
        if self.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED):
            raise PaymentAlreadyProcessedError(self.payment_id, self.status.value)
        if self.status == PaymentStatus.CANCELLED:
            raise PaymentNotProcessableError(
                payment_id=self.payment_id,
                status="cancelled",
                attempted_action="process"
            )

    def _ensure_succeeded(self) -> None:
        if self.status != PaymentStatus.SUCCEEDED:
            raise PaymentNotProcessableError(
                payment_id=self.payment_id,
                status=self.status.value,
                attempted_action="refund"
            )

    # ---------- COMMAND METHODS ----------
    def process(self) -> None:
        self._ensure_pending()
        self._apply(PaymentProcessedEvent(
            payment_id=self.payment_id,
            wallet_id=self.wallet_id,
            user_id=self.user_id,
        ))

    def succeed(self) -> None:
        self._ensure_processable()
        self._apply(PaymentSucceededEvent(
            payment_id=self.payment_id,
            wallet_id=self.wallet_id,
            user_id=self.user_id,
        ))

    def fail(self, reason: Optional[str] = None) -> None:
        self._ensure_processable()
        self._apply(PaymentFailedEvent(
            payment_id=self.payment_id,
            wallet_id=self.wallet_id,
            user_id=self.user_id,
            failure_reason=reason,
        ))

    def cancel(self) -> None:
        self._ensure_pending()
        self._apply(PaymentCancelledEvent(
            payment_id=self.payment_id,
            wallet_id=self.wallet_id,
            user_id=self.user_id,
        ))

    def mark_as_refunded(self, refund_id: UUID) -> None:
        """
        Mark this original payment as refunded (not to be confused with creating a refund payment).
        Typically called after a refund payment succeeds.
        """
        self._ensure_succeeded()
        self._apply(PaymentRefundedEvent(
            payment_id=self.payment_id,
            wallet_id=self.wallet_id,
            user_id=self.user_id,
            refunded_amount=self.amount,
            currency=self.currency,
            refund_id=refund_id,
        ))

    # ---------- EVENT SOURCING UTILITIES ----------
    def pop_events(self) -> List[PaymentEvent]:
        events = list(self._uncommitted_events)
        self._uncommitted_events.clear()
        return events

    def has_uncommitted_events(self) -> bool:
        return len(self._uncommitted_events) > 0

    # ---------- QUERY SUPPORT ----------
    def to_view(self) -> PaymentView:
        return PaymentView(
            payment_id=self.payment_id,
            wallet_id=self.wallet_id,
            user_id=self.user_id,
            amount=str(self.amount),
            currency=self.currency,
            payment_type=self.payment_type.value,
            payment_method=self.payment_method.value,
            status=self.status.value,
            reference_id=self.reference_id,
            description=self.description,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def __repr__(self) -> str:
        return (
            f"PaymentAggregate(id={self.payment_id}, wallet={self.wallet_id}, "
            f"amount={self.amount} {self.currency}, status={self.status.value}, "
            f"version={self.version})"
        )