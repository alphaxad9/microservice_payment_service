from src.application.external.user_view import UserView
from src.domain.apps.payment.models import PaymentView
from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentResponseDTO:
    payment: PaymentView
    owner: UserView | None = None