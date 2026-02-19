# src/infrastructure/projectors/payment/registry.py

from typing import Dict
from src.infrastructure.projectors.payment.projector import PaymentProjectionRunner

PAYMENT_PROJECTION_RUNNERS: Dict[str, PaymentProjectionRunner] = {}


def register_payment_projection(name: str, runner: PaymentProjectionRunner) -> None:
    PAYMENT_PROJECTION_RUNNERS[name] = runner


# Register the default payment projection
register_payment_projection("payment", PaymentProjectionRunner())