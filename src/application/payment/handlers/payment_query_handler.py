# src/application/payment/handlers/payment_query_handler.py
from __future__ import annotations

from decimal import Decimal
from uuid import UUID
from typing import List

from src.application.payment.services.interfaces.payment_query_interface import PaymentQueryServiceInterface
from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.domain.apps.payment.models import PaymentView
from .dtos import PaymentResponseDTO
from src.application.external.services.user_api_client import UserAPIClient


class PaymentQueryHandler:
    """
    Application-level query handler that orchestrates read-side queries for payments.
    Handles both simple passthrough queries and enriched queries that require
    owner user data from external services (e.g., UserAPIClient or equivalent).
    """

    def __init__(
        self,
        payment_queries: PaymentQueryServiceInterface,
        user_client: UserAPIClient,  # Expected to have a `get_user_by_id` method returning UserView
    ):
        self._payments = payment_queries
        self._users = user_client

    async def get_payment_with_owner(self, payment_id: UUID) -> PaymentResponseDTO:
        try:
            payment = await self._payments.get_payment(payment_id)
        except PaymentNotFoundError:
            raise
        except Exception as exc:
            raise PaymentNotFoundError(payment_id=str(payment_id)) from exc

        owner = None
        try:
            owner = self._users.get_user_by_id(payment.user_id)
        except Exception:
            # External service failure – degrade gracefully
            pass

        return PaymentResponseDTO(payment=payment, owner=owner)

    async def get_payments_by_wallet_with_owner(
        self, wallet_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentResponseDTO]:
        try:
            payments = await self._payments.get_payments_by_wallet(wallet_id, limit, offset)
        except Exception as exc:
            raise PaymentNotFoundError(message=f"Error retrieving payments for wallet {wallet_id}") from exc

        dtos: List[PaymentResponseDTO] = []
        for payment in payments:
            owner = None
            try:
                owner = self._users.get_user_by_id(payment.user_id)
            except Exception:
                pass  # Graceful degradation per payment
            dtos.append(PaymentResponseDTO(payment=payment, owner=owner))

        return dtos

    async def get_payments_by_user_with_owner(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentResponseDTO]:
        try:
            payments = await self._payments.get_payments_by_user(user_id, limit, offset)
        except Exception as exc:
            raise PaymentNotFoundError() from exc

        dtos: List[PaymentResponseDTO]  = []
        for payment in payments:
            owner = None
            try:
                owner = self._users.get_user_by_id(payment.user_id)
            except Exception:
                pass
            dtos.append(PaymentResponseDTO(payment=payment, owner=owner))

        return dtos

    async def get_payments_by_reference(self, reference_id: UUID) -> List[PaymentView]:
        try:
            return await self._payments.get_payments_by_reference(reference_id)
        except Exception as exc:
            raise PaymentNotFoundError(reference_id=str(reference_id)) from exc

    async def get_total_amount_by_wallet(
        self, wallet_id: UUID, status: str | None = None
    ) -> Decimal:
        try:
            return await self._payments.get_total_amount_by_wallet(wallet_id, status)
        except Exception as exc:
            raise PaymentNotFoundError(
                message=f"Unable to retrieve total amount for wallet {wallet_id}"
            ) from exc

    async def payment_exists(self, payment_id: UUID) -> bool:
        try:
            return await self._payments.payment_exists(payment_id)
        except Exception:
            return False