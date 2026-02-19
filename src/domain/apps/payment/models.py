# src/domain/apps/payment/models.py

from uuid import UUID, uuid4
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from dataclasses import dataclass
from decimal import Decimal
from src.domain.apps.payment.exceptions import InvalidPaymentAmountError, PaymentAlreadyProcessedError, PaymentNotProcessableError

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --- Enums (self-contained) ---
class PaymentStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentType(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    PAYMENT = "payment"  # e.g., for a booking or order
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class PaymentMethod(Enum):
    """Payment methods supported in this service."""
    WALLET = "wallet"
    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"
    OTHER = "other"


# --- Read model (DTO) ---
@dataclass(frozen=True)
class PaymentView:
    """Safe, read-only representation for queries or APIs."""
    payment_id: UUID
    wallet_id: UUID
    user_id: UUID
    amount: str  # e.g., "100.00" — formatting handled by projection
    currency: str
    payment_type: str
    payment_method: str
    status: str
    reference_id: Optional[UUID]  # e.g., booking_id, transaction_id
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


# --- Aggregate root ---
class Payment:
    """
    Payment aggregate root.
    Encapsulates business rules and lifecycle.
    Does NOT store balance or external state—assumes event sourcing or integration via domain events.
    """

    def __init__(
        self,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_type: PaymentType,
        payment_method: PaymentMethod,
        reference_id: Optional[UUID] = None,
        description: Optional[str] = None,
        status: PaymentStatus = PaymentStatus.PENDING,
        payment_id: Optional[UUID] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        if amount <= Decimal("0"):
            raise InvalidPaymentAmountError(amount)

        self.payment_id = payment_id or uuid4()
        self.wallet_id = wallet_id
        self.user_id = user_id
        self.amount = amount
        self.currency = currency.upper()
        self.payment_type = payment_type
        self.payment_method = payment_method
        self.reference_id = reference_id
        self.description = description
        self.status = status
        self.created_at = created_at or _now_utc()
        self.updated_at = updated_at or _now_utc()

    # --- Factories ---
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
    ) -> "Payment":
        return cls._validate_and_create(
            wallet_id, user_id, amount, currency,
            PaymentType.DEPOSIT, payment_method,
            reference_id, description
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
    ) -> "Payment":
        return cls._validate_and_create(
            wallet_id, user_id, amount, currency,
            PaymentType.WITHDRAWAL, payment_method,
            reference_id, description
        )

    @classmethod
    def create_refund(
        cls,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        original_payment_id: UUID,
        description: Optional[str] = None,
    ) -> "Payment":
        # Refunds must use internal wallet method
        if amount <= Decimal("0"):
            raise InvalidPaymentAmountError(amount)
        return cls(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency.upper(),
            payment_type=PaymentType.REFUND,
            payment_method=PaymentMethod.WALLET,
            reference_id=original_payment_id,
            description=description or "Refund",
            status=PaymentStatus.PENDING,
        )

    @classmethod
    def _validate_and_create(
        cls,
        wallet_id: UUID,
        user_id: UUID,
        amount: Decimal,
        currency: str,
        payment_type: PaymentType,
        payment_method: PaymentMethod,
        reference_id: Optional[UUID],
        description: Optional[str],
    ) -> "Payment":
        # Enforce method compatibility if needed (e.g., no wallet for external deposits)
        # For now, keep flexible—but you can add rules per your domain
        return cls(
            wallet_id=wallet_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            payment_type=payment_type,
            payment_method=payment_method,
            reference_id=reference_id,
            description=description,
            status=PaymentStatus.PENDING,
        )

    # --- Guard clauses ---
    def _ensure_pending(self) -> None:
        if self.status != PaymentStatus.PENDING:
            raise PaymentAlreadyProcessedError(self.payment_id, self.status.value)

    def _ensure_processable(self) -> None:
        if self.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED):
            raise PaymentAlreadyProcessedError(self.payment_id, self.status.value)
        if self.status == PaymentStatus.CANCELLED:
            raise PaymentNotProcessableError(self.payment_id, "cancelled", "process")

    # --- Lifecycle and intent methods ---
    def process(self) -> None:
        """Mark as processing — actual outcome determined by external service or worker."""
        self._ensure_pending()
        self.status = PaymentStatus.PROCESSING
        self.updated_at = _now_utc()

    def succeed(self) -> None:
        """Called when payment is confirmed successful (e.g., by payment gateway or wallet)."""
        self._ensure_processable()
        self.status = PaymentStatus.SUCCEEDED
        self.updated_at = _now_utc()

    def fail(self, reason: Optional[str] = None) -> None:
        """Called when payment fails (e.g., declined card, insufficient funds)."""
        self._ensure_processable()
        self.status = PaymentStatus.FAILED
        if reason:
            self.description = f"{self.description or ''} [FAILED: {reason}]".strip()
        self.updated_at = _now_utc()

    def cancel(self) -> None:
        """User or system cancels before processing."""
        if self.status != PaymentStatus.PENDING:
            raise PaymentNotProcessableError(self.payment_id, self.status.value, "cancel")
        self.status = PaymentStatus.CANCELLED
        self.updated_at = _now_utc()

    def refund(self) -> None:
        """Mark this payment as refunded (typically done by creating a *new* refund payment)."""
        if self.status != PaymentStatus.SUCCEEDED:
            raise PaymentNotProcessableError(self.payment_id, self.status.value, "refund")
        self.status = PaymentStatus.REFUNDED
        self.updated_at = _now_utc()

    # --- Query support ---
    def to_view(self) -> PaymentView:
        return PaymentView(
            payment_id=self.payment_id,
            wallet_id=self.wallet_id,
            user_id=self.user_id,
            amount=str(self.amount),  # Projection layer should format properly
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
            f"Payment(id={self.payment_id}, wallet={self.wallet_id}, "
            f"amount={self.amount} {self.currency}, status={self.status.value})"
        )