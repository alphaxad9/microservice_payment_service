# src/domain/apps/payment/repository.py

from __future__ import annotations
from abc import ABC, abstractmethod
from uuid import UUID
from decimal import Decimal
from typing import List, Optional

from src.domain.apps.payment.models import PaymentView
from src.domain.apps.payment.aggregate import PaymentAggregate


class PaymentQueryRepository(ABC):
    """
    Pure query interface for payment data.

    All methods return PaymentView (read model), NOT the aggregate.
    Used only by query services or read-side logic.

    NOTE: Command handlers MUST NOT use this interface.
    """

    @abstractmethod
    async def by_id(self, payment_id: UUID) -> PaymentView:
        """
        Retrieve a payment by its unique ID.

        Raises:
            PaymentNotFoundError: If no payment exists with the given ID.
        """
        raise NotImplementedError

    @abstractmethod
    async def by_wallet_id(self, wallet_id: UUID, limit: int = 100, offset: int = 0) -> List[PaymentView]:
        """
        Retrieve payments associated with a wallet.

        Args:
            wallet_id: The wallet ID to query.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of PaymentView instances, ordered by creation time (newest first).

        Raises:
            PaymentNotFoundError: If the wallet has no payments (optional behavior).
        """
        raise NotImplementedError

    @abstractmethod
    async def by_user_id(self, user_id: UUID, limit: int = 100, offset: int = 0) -> List[PaymentView]:
        """
        Retrieve payments initiated by a user.

        Args:
            user_id: The user ID to query.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of PaymentView instances, ordered by creation time (newest first).
        """
        raise NotImplementedError

    @abstractmethod
    async def by_reference_id(self, reference_id: UUID) -> List[PaymentView]:
        """
        Retrieve payments linked to a reference (e.g., booking, order).

        Args:
            reference_id: The reference UUID.

        Returns:
            List of matching PaymentView instances (e.g., original payment + refunds).
        """
        raise NotImplementedError

    @abstractmethod
    async def get_total_amount_by_wallet(
        self, wallet_id: UUID, status: Optional[str] = None
    ) -> Decimal:
        """
        Get total payment amount for a wallet, optionally filtered by status.

        Args:
            wallet_id: The wallet ID.
            status: Optional status filter (e.g., 'succeeded').

        Returns:
            Sum of amounts as Decimal; returns 0 if no matching payments.
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(self, payment_id: UUID) -> bool:
        """
        Check whether a payment exists.
        """
        raise NotImplementedError


class PaymentCommandRepository(ABC):
    """
    Async repository interface for loading and saving PaymentAggregates.

    Used exclusively by command handlers and application services.
    """

    @abstractmethod
    async def load(self, payment_id: UUID) -> PaymentAggregate:
        """
        Reconstruct a PaymentAggregate from its event stream or state snapshot.

        Raises:
            PaymentNotFoundError: If no payment exists with the given ID.
        """
        raise NotImplementedError

    @abstractmethod
    async def save(self, aggregate: PaymentAggregate) -> None:
        """
        Persist uncommitted events and/or updated state of the aggregate.

        Responsibilities:
          - Append new domain events to the event store (in event-sourced systems)
          - Update versioning to prevent concurrent modifications (optional but recommended)
          - Clear uncommitted events after successful persistence

        Raises:
            ConcurrentUpdateError: If optimistic concurrency check fails.
        """
        raise NotImplementedError

    @abstractmethod
    async def create(self, aggregate: PaymentAggregate) -> None:
        """
        Create a new payment (typically by storing its initial event(s)).

        This may be redundant if `save()` handles creation, but explicitly
        separating it can improve clarity in some implementations.
        """
        raise NotImplementedError