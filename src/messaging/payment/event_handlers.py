# src/domain/apps/payment/event_handlers.py

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Generic domain event base (global)
from src.domain.shared.events import DomainEvent

# Payment-specific events (for isinstance checks and logging)
from src.domain.apps.payment.events import (
    PaymentCreatedEvent,
    PaymentProcessedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    PaymentCancelledEvent,
    PaymentRefundedEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class PaymentEventHandlerContext:
    """
    Context shared by all payment event handlers.
    Currently empty—handlers only log—but can be extended with dependencies
    (e.g., repositories, notification services, analytics clients) if needed later.
    """
    pass


class BasePaymentEventHandler(ABC):
    """
    Abstract base for all payment event handlers.
    Accepts DomainEvent to comply with global event bus contract.
    Concrete handlers filter by type using isinstance().
    """
    def __init__(self, ctx: PaymentEventHandlerContext) -> None:
        self.ctx = ctx

    @abstractmethod
    async def handle(self, event: DomainEvent) -> None:
        """
        Handle a domain event.
        Implementations must first check if the event is of the expected type.
        """
        raise NotImplementedError()


class PaymentCreatedHandler(BasePaymentEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, PaymentCreatedEvent):
            return
        logger.info(
            "[💳 Payment Event Handler] Received PaymentCreatedEvent: "
            "payment_id=%s, wallet_id=%s, user_id=%s, amount=%s %s, method=%s",
            event.payment_id,
            event.wallet_id,
            event.user_id,
            event.amount,
            event.currency,
            event.payment_method,
        )


class PaymentProcessedHandler(BasePaymentEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, PaymentProcessedEvent):
            return
        logger.info(
            "[💳 Payment Event Handler] Received PaymentProcessedEvent: "
            "payment_id=%s, wallet_id=%s, user_id=%s",
            event.payment_id,
            event.wallet_id,
            event.user_id,
        )


class PaymentSucceededHandler(BasePaymentEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, PaymentSucceededEvent):
            return
        logger.info(
            "[✅ Payment Event Handler] Received PaymentSucceededEvent: "
            "payment_id=%s, wallet_id=%s, user_id=%s",
            event.payment_id,
            event.wallet_id,
            event.user_id,
        )


class PaymentFailedHandler(BasePaymentEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, PaymentFailedEvent):
            return
        logger.info(
            "[❌ Payment Event Handler] Received PaymentFailedEvent: "
            "payment_id=%s, wallet_id=%s, user_id=%s, reason=%s",
            event.payment_id,
            event.wallet_id,
            event.user_id,
            event.failure_reason or "unknown",
        )


class PaymentCancelledHandler(BasePaymentEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, PaymentCancelledEvent):
            return
        logger.info(
            "[🚫 Payment Event Handler] Received PaymentCancelledEvent: "
            "payment_id=%s, wallet_id=%s, user_id=%s",
            event.payment_id,
            event.wallet_id,
            event.user_id,
        )


class PaymentRefundedHandler(BasePaymentEventHandler):
    async def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, PaymentRefundedEvent):
            return
        logger.info(
            "[↩️ Payment Event Handler] Received PaymentRefundedEvent: "
            "payment_id=%s, wallet_id=%s, user_id=%s, refunded_amount=%s %s, refund_id=%s",
            event.payment_id,
            event.wallet_id,
            event.user_id,
            event.refunded_amount,
            event.currency,
            event.refund_id,
        )