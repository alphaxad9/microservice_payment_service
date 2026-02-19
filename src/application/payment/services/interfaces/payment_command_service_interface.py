# src/application/payment/services.interfaces/payment_command_service_interface.py

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from uuid import UUID


# =========================
# WRITE INTERFACE (Commands)
# =========================
class PaymentCommandServiceInterface(ABC):
    """
    Abstract interface for the write-side (command) of the payment domain.
    Defines all operations that create or mutate payment state.

    Implementations coordinate domain rules, aggregates, and the command repository.
    This interface is used by API controllers, message handlers, saga coordinators, etc.
    """

    @abstractmethod
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
        """Create a new deposit payment."""
        raise NotImplementedError

    @abstractmethod
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
        """Create a new withdrawal payment."""
        raise NotImplementedError

    @abstractmethod
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
        """Create a new payment for a booking."""
        raise NotImplementedError

    @abstractmethod
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
        """Create a refund payment linked to an original payment."""
        raise NotImplementedError

    @abstractmethod
    async def process_payment(self, payment_id: UUID) -> None:
        """Transition a pending payment to processing state."""
        raise NotImplementedError

    @abstractmethod
    async def succeed_payment(self, payment_id: UUID) -> None:
        """Mark a payment as succeeded."""
        raise NotImplementedError

    @abstractmethod
    async def fail_payment(self, payment_id: UUID, reason: Optional[str] = None) -> None:
        """Mark a payment as failed with an optional reason."""
        raise NotImplementedError

    @abstractmethod
    async def cancel_payment(self, payment_id: UUID) -> None:
        """Cancel a pending payment."""
        raise NotImplementedError

    @abstractmethod
    async def mark_payment_as_refunded(self, payment_id: UUID, refund_id: UUID) -> None:
        """
        Mark an original payment as refunded after a successful refund payment.
        """
        raise NotImplementedError