# src/application/payment/services.interfaces/payment_query_service_interface.py

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from uuid import UUID
from typing import List, Optional

from src.domain.apps.payment.models import PaymentView


# =========================
# READ INTERFACE (Queries)
# =========================
class PaymentQueryServiceInterface(ABC):
    """
    Abstract interface for the read-side of the payment domain.
    Defines all query operations that can be performed on payment data.

    Implementations should use denormalized read models (e.g., PaymentView)
    for optimal performance. This interface is used by API layers, background jobs,
    dashboards, etc.

    NOTE: This interface must remain free of any command/mutation logic.
    """

    @abstractmethod
    async def get_payment(self, payment_id: UUID) -> PaymentView:
        """
        Retrieve a payment by its unique ID.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_payments_by_wallet(
        self, wallet_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentView]:
        """
        Retrieve payments associated with a wallet, paginated.
        Results are ordered by creation time (newest first).
        """
        raise NotImplementedError

    @abstractmethod
    async def get_payments_by_user(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentView]:
        """
        Retrieve payments initiated by a user, paginated.
        Results are ordered by creation time (newest first).
        """
        raise NotImplementedError

    @abstractmethod
    async def get_payments_by_reference(self, reference_id: UUID) -> List[PaymentView]:
        """
        Retrieve all payments linked to a reference ID (e.g., booking, order).
        Useful for fetching original payments and related refunds.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_total_amount_by_wallet(
        self, wallet_id: UUID, status: Optional[str] = None
    ) -> Decimal:
        """
        Calculate the total amount of payments for a wallet.
        Optionally filter by payment status (e.g., 'succeeded').
        Returns Decimal('0') if no matching payments exist.
        """
        raise NotImplementedError

    @abstractmethod
    async def payment_exists(self, payment_id: UUID) -> bool:
        """
        Check whether a payment with the given ID exists.
        """
        raise NotImplementedError