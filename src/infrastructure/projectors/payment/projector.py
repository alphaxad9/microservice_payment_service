# src/infrastructure/projectors/payment/projector.py

from __future__ import annotations

from typing import Callable, Dict
from uuid import UUID
from django.db import  transaction
from src.domain.shared.events import DomainEvent
from src.domain.apps.payment.events import (
    PaymentEvent,
    PaymentEventType,
    PaymentCreatedEvent,
    PaymentProcessedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    PaymentCancelledEvent,
    PaymentRefundedEvent,
)
from src.infrastructure.apps.payment.models import PaymentReadModel
from src.domain.apps.payment.models import PaymentStatus
from src.domain.shared.exceptions import ProjectionInvariantViolation


class PaymentProjector:
    """
    Pure projection logic for the payment read model.
    Idempotent, atomic, and includes defensive invariant checks.
    Does NOT know about EventStore or ProjectionState.
    """

    EventHandler = Callable[[PaymentEvent], None]

    @transaction.atomic
    def project(self, event: DomainEvent) -> None:
        """
        Dispatch to the appropriate handler only if the event is a PaymentEvent.
        Non-payment events are silently ignored (safe for multi-domain event processing).
        """
        if not isinstance(event, PaymentEvent):
            return  # ignore events from other domains

        handlers: Dict[str, PaymentProjector.EventHandler] = {
            PaymentEventType.PAYMENT_CREATED.value: self.on_payment_created,
            PaymentEventType.PAYMENT_PROCESSED.value: self.on_payment_processed,
            PaymentEventType.PAYMENT_SUCCEEDED.value: self.on_payment_succeeded,
            PaymentEventType.PAYMENT_FAILED.value: self.on_payment_failed,
            PaymentEventType.PAYMENT_CANCELLED.value: self.on_payment_cancelled,
            PaymentEventType.PAYMENT_REFUNDED.value: self.on_payment_refunded,
        }

        handler = handlers.get(event.event_type)
        if handler is not None:
            handler(event)
        # Optional: log unknown payment event types in production
        # else:
        #     logger.warning(f"Unhandled payment event type: {event.event_type}")

    # -------------------------------------------------------------------------
    # Event Handlers with defensive checks
    # -------------------------------------------------------------------------

    def on_payment_created(self, event: PaymentCreatedEvent) -> None:
        obj, created = PaymentReadModel.objects.update_or_create(
            id=event.payment_id,
            defaults={
                "wallet_id": event.wallet_id,
                "user_id": event.user_id,
                "amount": event.amount,
                "currency": event.currency.upper(),
                "payment_type": event.payment_type,
                "payment_method": event.payment_method,
                "status": PaymentStatus.PENDING.name,
                "reference_id": event.reference_id,
                "description": event.description,
            },
        )
        if not created:
            # Allow idempotent replay: tolerate duplicate creation
            pass

    def on_payment_processed(self, event: PaymentProcessedEvent) -> None:
        updated = PaymentReadModel.objects.filter(
            id=event.payment_id,
            status=PaymentStatus.PENDING.name
        ).update(
            status=PaymentStatus.PROCESSING.name
        )
        if updated == 0:
            raise ProjectionInvariantViolation(
                f"PaymentProcessedEvent applied but payment {event.payment_id} "
                f"does not exist or is not in PENDING status"
            )

    def on_payment_succeeded(self, event: PaymentSucceededEvent) -> None:
        updated = PaymentReadModel.objects.filter(
            id=event.payment_id,
            status__in=[PaymentStatus.PENDING.name, PaymentStatus.PROCESSING.name]
        ).update(
            status=PaymentStatus.SUCCEEDED.name
        )
        if updated == 0:
            raise ProjectionInvariantViolation(
                f"PaymentSucceededEvent applied but payment {event.payment_id} "
                f"does not exist or is not processable"
            )

    def on_payment_failed(self, event: PaymentFailedEvent) -> None:
        updated = PaymentReadModel.objects.filter(
            id=event.payment_id,
            status__in=[PaymentStatus.PENDING.name, PaymentStatus.PROCESSING.name]
        ).update(
            status=PaymentStatus.FAILED.name,
            description=(
                f"{event.failure_reason}"
                if event.failure_reason
                else "Payment failed"
            )
        )
        if updated == 0:
            raise ProjectionInvariantViolation(
                f"PaymentFailedEvent applied but payment {event.payment_id} "
                f"does not exist or is not processable"
            )

    def on_payment_cancelled(self, event: PaymentCancelledEvent) -> None:
        updated = PaymentReadModel.objects.filter(
            id=event.payment_id,
            status=PaymentStatus.PENDING.name
        ).update(
            status=PaymentStatus.CANCELLED.name
        )
        if updated == 0:
            raise ProjectionInvariantViolation(
                f"PaymentCancelledEvent applied but payment {event.payment_id} "
                f"does not exist or is not PENDING"
            )

    def on_payment_refunded(self, event: PaymentRefundedEvent) -> None:
        updated = PaymentReadModel.objects.filter(
            id=event.payment_id,
            status=PaymentStatus.SUCCEEDED.name
        ).update(
            status=PaymentStatus.REFUNDED.name
        )
        if updated == 0:
            raise ProjectionInvariantViolation(
                f"PaymentRefundedEvent applied but payment {event.payment_id} "
                f"does not exist or is not SUCCEEDED"
            )


class PaymentProjectionRunner:
    """
    Controls the projection lifecycle using ProjectionState.
    Supports both async outbox processing/rebuild and (optional) synchronous dev mode.
    """

    PROJECTION_NAME = "payment"
    VERSION = 1

    def __init__(self):
        self.projector = PaymentProjector()

    @transaction.atomic
    def apply(self, stored_event: "EventStore") -> None:  # type: ignore
        """
        Used during rebuild or async outbox consumer.
        Reconstructs the domain event and applies the projection.
        """
        from src.infrastructure.apps.eventstore.models import ProjectionState, EventStore

        state, _ = ProjectionState.objects.select_for_update().get_or_create(
            projection_name=self.PROJECTION_NAME,
            defaults={"version": self.VERSION},
        )

        if state.version != self.VERSION:
            return  # projection disabled (e.g., during migration)

        # Reconstruct event using payment-specific factory
        from src.domain.apps.payment.events import event_from_dict
        event = event_from_dict(
            event_type=stored_event.event_type,
            event_payload=stored_event.event_payload,
        )

        self.projector.project(event)

        state.last_event_id = stored_event.id
        state.save(update_fields=["last_event_id"])

    @transaction.atomic
    def apply_from_event(self, event: DomainEvent, aggregate_id: UUID, version: int) -> None:
        """
        Development-only synchronous projection for immediate read-after-write consistency.
        Should be disabled in production (guard in EventStoreRepository.append()).
        """
        from src.infrastructure.apps.eventstore.models import ProjectionState

        state, _ = ProjectionState.objects.select_for_update().get_or_create(
            projection_name=self.PROJECTION_NAME,
            defaults={"version": self.VERSION},
        )

        if state.version != self.VERSION:
            return

        self.projector.project(event)

        # No stored_event record yet in sync mode → cannot store meaningful last_event_id
        state.last_event_id = None
        state.save(update_fields=["last_event_id"])