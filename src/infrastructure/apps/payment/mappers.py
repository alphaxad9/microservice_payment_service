# src/infrastructure/apps/payment/mappers.py

from __future__ import annotations

from decimal import Decimal
from src.domain.apps.payment.models import PaymentView
from src.infrastructure.apps.payment.models import PaymentReadModel


class PaymentReadModelMapper:
    @staticmethod
    def to_view(read_model: PaymentReadModel) -> PaymentView:
        # Normalize amount to remove trailing zeros (e.g., '100.5000' → '100.5')
        normalized_amount = read_model.amount.normalize()
        return PaymentView(
            payment_id=read_model.id,
            wallet_id=read_model.wallet_id,
            user_id=read_model.user_id,
            amount=str(normalized_amount),
            currency=read_model.currency,
            payment_type=read_model.payment_type,
            payment_method=read_model.payment_method,
            status=read_model.status,
            reference_id=read_model.reference_id,
            description=read_model.description,
            created_at=read_model.created_at,
            updated_at=read_model.updated_at,
        )