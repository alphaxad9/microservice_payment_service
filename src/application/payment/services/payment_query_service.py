# src/application/payment/services/payment_query_service.py

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID
from typing import List, Optional

from src.domain.apps.payment.models import PaymentView
from src.domain.apps.payment.repository import PaymentQueryRepository
from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.application.payment.services.interfaces.payment_query_interface import PaymentQueryServiceInterface

logger = logging.getLogger(__name__)


class PaymentQueryService(PaymentQueryServiceInterface):
    """
    Concrete implementation of the payment query interface with proper error handling,
    input validation, and logging. Delegates to a query repository for data access.
    """

    def __init__(self, query_repo: PaymentQueryRepository):
        self._query_repo = query_repo

    def _validate_pagination(self, limit: int, offset: int) -> tuple[int, int]:
        """
        Validate and sanitize pagination parameters.
        Negative values are clamped to 0 to avoid unexpected behavior.
        """
        return max(limit, 0), max(offset, 0)

    async def get_payment(self, payment_id: UUID) -> PaymentView:
        if not payment_id:
            raise ValueError("payment_id is required")

        try:
            return await self._query_repo.by_id(payment_id)
        except PaymentNotFoundError:
            # Re-raise expected domain exception
            raise
        except Exception as exc:
            logger.error("Unexpected error fetching payment %s: %s", payment_id, exc)
            raise PaymentNotFoundError(payment_id=str(payment_id)) from exc

    async def get_payments_by_wallet(
        self, wallet_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentView]:
        if not wallet_id:
            raise ValueError("wallet_id is required")

        limit, offset = self._validate_pagination(limit, offset)

        try:
            return await self._query_repo.by_wallet_id(wallet_id, limit=limit, offset=offset)
        except PaymentNotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error fetching payments for wallet %s (limit=%d, offset=%d): %s",
                wallet_id, limit, offset, exc
            )
            raise PaymentNotFoundError(payment_id=None) from exc

    async def get_payments_by_user(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentView]:
        if not user_id:
            raise ValueError("user_id is required")

        limit, offset = self._validate_pagination(limit, offset)

        try:
            return await self._query_repo.by_user_id(user_id, limit=limit, offset=offset)
        except Exception as exc:
            logger.error(
                "Unexpected error fetching payments for user %s (limit=%d, offset=%d): %s",
                user_id, limit, offset, exc
            )
            # Note: by_user_id doesn't raise PaymentNotFoundError in repo spec,
            # so we don't re-raise it here—just log and propagate generic error
            raise

    async def get_payments_by_reference(self, reference_id: UUID) -> List[PaymentView]:
        if not reference_id:
            raise ValueError("reference_id is required")

        try:
            return await self._query_repo.by_reference_id(reference_id)
        except Exception as exc:
            logger.error("Unexpected error fetching payments for reference %s: %s", reference_id, exc)
            raise PaymentNotFoundError(reference_id=str(reference_id)) from exc

    async def get_total_amount_by_wallet(
        self, wallet_id: UUID, status: Optional[str] = None
    ) -> Decimal:
        if not wallet_id:
            raise ValueError("wallet_id is required")

        try:
            return await self._query_repo.get_total_amount_by_wallet(wallet_id, status=status)
        except Exception as exc:
            logger.error(
                "Failed to fetch total amount for wallet %s (status=%s): %s",
                wallet_id, status, exc
            )
            # Return zero on error to avoid breaking callers expecting a Decimal
            return Decimal("0")

    async def payment_exists(self, payment_id: UUID) -> bool:
        if not payment_id:
            raise ValueError("payment_id is required")

        try:
            return await self._query_repo.exists(payment_id)
        except Exception as exc:
            logger.warning("Error checking existence of payment %s: %s", payment_id, exc)
            # Conservative: if check fails, assume it doesn't exist
            return False