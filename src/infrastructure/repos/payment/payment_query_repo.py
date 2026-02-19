# src/infrastructure/repos/payment/payment_query_repo.py

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum

from src.domain.apps.payment.repository import PaymentQueryRepository
from src.domain.apps.payment.models import PaymentView
from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.infrastructure.apps.payment.models import PaymentReadModel
from src.infrastructure.apps.payment.mappers import PaymentReadModelMapper


class DjangoPaymentQueryRepository(PaymentQueryRepository):
    """
    Read-side repository (CQRS query side) for payments.
    Returns only PaymentView DTOs — never aggregates or domain entities.
    """

    mapper = PaymentReadModelMapper

    async def by_id(self, payment_id: UUID) -> PaymentView:
        try:
            read_model = await PaymentReadModel.objects.aget(id=payment_id)
            return self.mapper.to_view(read_model)
        except ObjectDoesNotExist:
            raise PaymentNotFoundError(payment_id=payment_id)

    async def by_wallet_id(
        self, wallet_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentView]:
        if limit < 0 or offset < 0:
            raise ValueError("Pagination parameters 'limit' and 'offset' must be non-negative.")
        if limit == 0:
            return []

        queryset = (
            PaymentReadModel.objects
            .filter(wallet_id=wallet_id)
            .order_by('-created_at')
        )
        paginated_qs = queryset[offset : offset + limit]
        read_models = [rm async for rm in paginated_qs]
        return [self.mapper.to_view(rm) for rm in read_models]

    async def by_user_id(
        self, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> List[PaymentView]:
        if limit < 0 or offset < 0:
            raise ValueError("Pagination parameters 'limit' and 'offset' must be non-negative.")
        if limit == 0:
            return []

        queryset = (
            PaymentReadModel.objects
            .filter(user_id=user_id)
            .order_by('-created_at')
        )
        paginated_qs = queryset[offset : offset + limit]
        read_models = [rm async for rm in paginated_qs]
        return [self.mapper.to_view(rm) for rm in read_models]

    async def by_reference_id(self, reference_id: UUID) -> List[PaymentView]:
        queryset = (
            PaymentReadModel.objects
            .filter(reference_id=reference_id)
            .order_by('-created_at')
        )
        read_models = [rm async for rm in queryset]
        return [self.mapper.to_view(rm) for rm in read_models]

    async def get_total_amount_by_wallet(
        self, wallet_id: UUID, status: Optional[str] = None
    ) -> Decimal:
        queryset = PaymentReadModel.objects.filter(wallet_id=wallet_id)
        if status is not None:
            queryset = queryset.filter(status=status)

        try:
            result = await queryset.aaggregate(total=Sum('amount'))
        except Exception as e:
            # Optional: log the error here (e.g., using structlog or logging)
            # For now, let it bubble unless you want a domain-safe fallback
            raise e

        total: Decimal | None = result['total']
        return total if total is not None else Decimal('0')

    async def exists(self, payment_id: UUID) -> bool:
        try:
            return await PaymentReadModel.objects.filter(id=payment_id).aexists()
        except Exception as e:
            # Again, usually safe to let this bubble, but included for completeness
            raise e