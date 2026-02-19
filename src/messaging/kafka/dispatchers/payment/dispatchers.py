# src/messaging/payment/dispatchers.py

import logging
from typing import Callable, Awaitable, Any

from src.domain.apps.payment.events import (
    PaymentCreatedEvent,
    PaymentProcessedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    PaymentCancelledEvent,
    PaymentRefundedEvent,
    PaymentEventType,
)
from src.messaging.event_bus import event_bus

logger = logging.getLogger(__name__)

# Handler registry: event_type.value -> async dispatcher function
PAYMENT_EVENT_HANDLERS: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}


def register_payment_handler(event_type: PaymentEventType):
    """Decorator to register a dispatcher function for a given PaymentEventType."""
    def decorator(func: Callable[[dict[str, Any]], Awaitable[None]]):
        PAYMENT_EVENT_HANDLERS[event_type.value] = func
        return func
    return decorator


@register_payment_handler(PaymentEventType.PAYMENT_CREATED)
async def handle_payment_created(data: dict[str, Any]) -> None:
    event = PaymentCreatedEvent.from_dict(data)
    await event_bus.publish(event)
    logger.info(
        "💳 PaymentCreated dispatched: payment_id=%s, wallet_id=%s, amount=%s %s",
        event.payment_id,
        event.wallet_id,
        event.amount,
        event.currency,
    )


@register_payment_handler(PaymentEventType.PAYMENT_PROCESSED)
async def handle_payment_processed(data: dict[str, Any]) -> None:
    event = PaymentProcessedEvent.from_dict(data)
    await event_bus.publish(event)
    logger.info(
        "🔄 PaymentProcessed dispatched: payment_id=%s, wallet_id=%s",
        event.payment_id,
        event.wallet_id,
    )


@register_payment_handler(PaymentEventType.PAYMENT_SUCCEEDED)
async def handle_payment_succeeded(data: dict[str, Any]) -> None:
    event = PaymentSucceededEvent.from_dict(data)
    await event_bus.publish(event)
    logger.info(
        "✅ PaymentSucceeded dispatched: payment_id=%s, wallet_id=%s",
        event.payment_id,
        event.wallet_id,
    )


@register_payment_handler(PaymentEventType.PAYMENT_FAILED)
async def handle_payment_failed(data: dict[str, Any]) -> None:
    event = PaymentFailedEvent.from_dict(data)
    await event_bus.publish(event)
    logger.info(
        "❌ PaymentFailed dispatched: payment_id=%s, wallet_id=%s, reason=%s",
        event.payment_id,
        event.wallet_id,
        event.failure_reason or "unknown",
    )


@register_payment_handler(PaymentEventType.PAYMENT_CANCELLED)
async def handle_payment_cancelled(data: dict[str, Any]) -> None:
    event = PaymentCancelledEvent.from_dict(data)
    await event_bus.publish(event)
    logger.info(
        "🚫 PaymentCancelled dispatched: payment_id=%s, wallet_id=%s",
        event.payment_id,
        event.wallet_id,
    )


@register_payment_handler(PaymentEventType.PAYMENT_REFUNDED)
async def handle_payment_refunded(data: dict[str, Any]) -> None:
    event = PaymentRefundedEvent.from_dict(data)
    await event_bus.publish(event)
    logger.info(
        "↩️ PaymentRefunded dispatched: payment_id=%s, wallet_id=%s, refunded_amount=%s %s",
        event.payment_id,
        event.wallet_id,
        event.refunded_amount,
        event.currency,
    )