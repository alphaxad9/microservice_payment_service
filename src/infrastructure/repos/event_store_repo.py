# src/infrastructure/repos/event_store_repo.py

from __future__ import annotations
from django.db import transaction, IntegrityError
from typing import List, Dict, Any
from uuid import UUID
from django.conf import settings
from src.domain.shared.events import DomainEvent
from src.domain.shared.exceptions import OptimisticConcurrencyError
from src.infrastructure.apps.eventstore.models import EventStore
from src.domain.outbox.events import OutboxEvent
from src.domain.outbox.repositories import OutboxRepository


class EventStoreRepository:
    """
    Persists domain events to the EventStore, publishes to Outbox,
    and performs synchronous projection into WalletReadModel
    for immediate read-after-write consistency during development.
    """

    def __init__(self, outbox_repo: OutboxRepository):
        self._outbox = outbox_repo

    @transaction.atomic
    def append(
        self,
        *,
        aggregate_id: UUID,
        aggregate_type: str,
        expected_version: int,
        events: List[DomainEvent],
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        if not events:
            return

        metadata = metadata or {}
        current_version = expected_version

        for event in events:
            current_version += 1

            try:
                EventStore.objects.create(
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    aggregate_version=current_version,
                    event_type=event.event_type,
                    event_payload=event.to_dict(),
                    metadata=metadata,
                )
            except IntegrityError:
                raise OptimisticConcurrencyError(
                    f"Concurrent modification detected for aggregate {aggregate_id} "
                    f"(expected version {expected_version}, conflict at {current_version})"
                ) from None

            # Always publish to outbox
            self._outbox.save(
                OutboxEvent(
                    event_type=event.event_type,
                    event_payload=event.to_dict(),
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    metadata=metadata,
                )
            )

            if settings.DEBUG:
                from src.infrastructure.projectors.payment.projector import PaymentProjectionRunner
                runner = PaymentProjectionRunner()
                runner.apply_from_event(event, aggregate_id, current_version)