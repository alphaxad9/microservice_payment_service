# src/infrastructure/repos/payment/payment_command_repo.py

from __future__ import annotations

from uuid import UUID
from asgiref.sync import sync_to_async
from src.domain.apps.payment.models import PaymentType, PaymentMethod
from src.domain.apps.payment.repository import PaymentCommandRepository
from src.domain.apps.payment.aggregate import PaymentAggregate
from src.domain.apps.payment.events import (
    PaymentCreatedEvent,
    event_from_dict,
)
from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.infrastructure.apps.eventstore.models import EventStore
from src.infrastructure.repos.event_store_repo import EventStoreRepository


class PaymentEventSourcedRepository(PaymentCommandRepository):
    """
    Command-side repository for PaymentAggregates.
    Loads aggregates from event stream and delegates persistence to EventStoreRepository.
    """

    def __init__(self, event_store: EventStoreRepository):
        self._event_store = event_store

    async def load(self, payment_id: UUID) -> PaymentAggregate:
        # Wrap synchronous ORM query in sync_to_async
        events = await sync_to_async(list)(
            EventStore.objects.filter(
                aggregate_id=payment_id,
                aggregate_type="Payment",
            )
            .order_by("aggregate_version")
            .only("aggregate_version", "event_type", "event_payload")
        )

        if not events:
            raise PaymentNotFoundError(payment_id=str(payment_id))

        first_event = event_from_dict(
            event_type=events[0].event_type,
            event_payload=events[0].event_payload,
        )

        if not isinstance(first_event, PaymentCreatedEvent):
            raise ValueError(
                f"Expected PaymentCreatedEvent as first event, got {type(first_event).__name__}"
            )

        # Convert string enums back to enum instances
        payment_type_enum = PaymentType(first_event.payment_type)
        payment_method_enum = PaymentMethod(first_event.payment_method)

        aggregate = PaymentAggregate(
            payment_id=first_event.payment_id,
            wallet_id=first_event.wallet_id,
            user_id=first_event.user_id,
            amount=first_event.amount,
            currency=first_event.currency,
            payment_type=payment_type_enum,
            payment_method=payment_method_enum,
            reference_id=first_event.reference_id,
            description=first_event.description,
        )

        for stored_event in events[1:]:
            domain_event = event_from_dict(
                event_type=stored_event.event_type,
                event_payload=stored_event.event_payload,
            )
            aggregate.when(domain_event)

        aggregate.version = events[-1].aggregate_version
        return aggregate
    async def save(self, aggregate: PaymentAggregate) -> None:
        events = aggregate.pop_events()
        if not events:
            return

        # The expected version is the version BEFORE these new events were applied
        expected_version = aggregate.version - len(events)

        await sync_to_async(self._event_store.append)(
            aggregate_id=aggregate.payment_id,
            aggregate_type="Payment",
            expected_version=expected_version,
            events=events,
            metadata={
                "schema_version": events[0].schema_version if events else 1
            },
        )

        # Now update version to reflect successful persistence (already correct)
        aggregate.version = expected_version + len(events)  # same as before
    async def create(self, aggregate: PaymentAggregate) -> None:
        await self.save(aggregate)