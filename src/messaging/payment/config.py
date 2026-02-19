# src/messaging/payment/config.py

from __future__ import annotations

from src.domain.apps.payment.events import (
    PaymentCreatedEvent,
    PaymentProcessedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    PaymentCancelledEvent,
    PaymentRefundedEvent,
)
from src.messaging.payment.event_handlers import (
    PaymentEventHandlerContext,
    PaymentCreatedHandler,
    PaymentProcessedHandler,
    PaymentSucceededHandler,
    PaymentFailedHandler,
    PaymentCancelledHandler,
    PaymentRefundedHandler,
)
from src.messaging.event_bus import event_bus  # global event bus instance


def configure_payment_event_bus() -> None:
    """
    Configures the global payment event bus with all logging-only handlers.
    
    Call this once during application startup (e.g., in FastAPI lifespan or Django AppConfig).
    """
    # Build shared handler context (currently empty, as handlers only log)
    ctx = PaymentEventHandlerContext()

    # Instantiate handlers
    payment_created_handler = PaymentCreatedHandler(ctx=ctx)
    payment_processed_handler = PaymentProcessedHandler(ctx=ctx)
    payment_succeeded_handler = PaymentSucceededHandler(ctx=ctx)
    payment_failed_handler = PaymentFailedHandler(ctx=ctx)
    payment_cancelled_handler = PaymentCancelledHandler(ctx=ctx)
    payment_refunded_handler = PaymentRefundedHandler(ctx=ctx)

    # Subscribe handlers to their respective events
    event_bus.subscribe(PaymentCreatedEvent, payment_created_handler.handle)
    event_bus.subscribe(PaymentProcessedEvent, payment_processed_handler.handle)
    event_bus.subscribe(PaymentSucceededEvent, payment_succeeded_handler.handle)
    event_bus.subscribe(PaymentFailedEvent, payment_failed_handler.handle)
    event_bus.subscribe(PaymentCancelledEvent, payment_cancelled_handler.handle)
    event_bus.subscribe(PaymentRefundedEvent, payment_refunded_handler.handle)