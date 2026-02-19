# src/infrastructure/outbox/django_repository.py
from __future__ import annotations
from typing import List
from uuid import UUID
from django.db import IntegrityError, models
from django.utils import timezone
from asgiref.sync import sync_to_async
import time
from django.db import transaction


from src.domain.outbox.repositories import OutboxRepository
from src.domain.outbox.events import OutboxEvent
from src.domain.outbox.exceptions import (
    OutboxSaveError,
    OutboxNotFoundError
)
from src.infrastructure.apps.outbox.models import EventOutbox

import json
from django.core.serializers.json import DjangoJSONEncoder



    
class DjangoOutBoxORMRepository(OutboxRepository):
    def save(self, event: OutboxEvent, max_retries: int = 3) -> None:
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    latest_version = (
                        EventOutbox.objects
                        .select_for_update()
                        .filter(aggregate_id=event.aggregate_id)
                        .aggregate(models.Max("aggregate_version"))["aggregate_version__max"]
                        or 0
                    )
                    next_version = latest_version + 1

                    # Pre-validate JSON serializability
                    try:
                        json.dumps(event.event_payload, cls=DjangoJSONEncoder)
                    except (TypeError, ValueError) as e:
                        raise OutboxSaveError(
                            event_type=event.event_type,
                            aggregate_id=event.aggregate_id,
                            reason=f"Failed to serialize event_payload to JSON: {e}"
                        ) from e

                    EventOutbox.objects.create(
                        id=event.id,
                        event_type=event.event_type,
                        event_payload=event.event_payload,
                        aggregate_id=event.aggregate_id,
                        aggregate_type=event.aggregate_type,
                        aggregate_version=next_version,
                        trace_id=event.trace_id,
                        metadata=event.metadata,
                        created_at=event.created_at,
                        retry_count=event.retry_count,
                    )
                return
            except IntegrityError as e:
                if attempt < max_retries - 1:
                    time.sleep(0.05)
                    continue
                raise OutboxSaveError(
                    event_type=event.event_type,
                    aggregate_id=event.aggregate_id,
                    reason=f"Integrity error after {max_retries} retries: {e}"
                ) from e
    # src/infrastructure/repos/outbox/orm_repository.py

    def get_unpublished_events(self, limit: int = 100) -> List[OutboxEvent]:
        with transaction.atomic():
            # Force immediate evaluation inside the transaction
            outbox_objects = list(
                EventOutbox.objects
                .filter(processed_at__isnull=True)
                .select_for_update(skip_locked=True)
                .order_by('created_at')[:limit]
            )
        
        # Convert to domain events after exiting the transaction (safe, no DB access)
        return [
            OutboxEvent(
                id=obj.id,
                event_type=obj.event_type,
                event_payload=obj.event_payload,
                aggregate_id=obj.aggregate_id,
                aggregate_type=obj.aggregate_type,
                trace_id=obj.trace_id,
                metadata=obj.metadata or {},
                created_at=obj.created_at,
                retry_count=obj.retry_count,
            )
            for obj in outbox_objects
        ]
        
    def mark_as_published(self, outbox_id: UUID) -> None:
        now = timezone.now() 
        updated = EventOutbox.objects.filter(
        id=outbox_id,
        published_at__isnull=True
        ).update(
            published_at=now,
            processed_at=now,
        )
        
        if updated == 0:
            # Check if it exists but is already published (idempotent success)
            try:
                EventOutbox.objects.get(id=outbox_id)
                # Already published → do nothing (idempotent)
                return
            except EventOutbox.DoesNotExist:
                raise OutboxNotFoundError(outbox_id)

    def mark_as_failed(self, outbox_id: UUID, error: str) -> None:
        """
        Mark event as failed and increment retry count atomically.
        Raises OutboxNotFoundError if event is missing.
        """
        updated = EventOutbox.objects.filter(id=outbox_id).update(
            error_message=error,
            retry_count=models.F('retry_count') + 1
        )
        if updated == 0:
            raise OutboxNotFoundError(outbox_id)


    # --- Async wrappers (for use in async contexts like ASGI) ---

    @sync_to_async
    def save_async(self, event: OutboxEvent) -> None:
        return self.save(event)

    @sync_to_async
    def get_unpublished_events_async(self, limit: int = 100) -> List[OutboxEvent]:
        return self.get_unpublished_events(limit)

    @sync_to_async
    def mark_as_published_async(self, outbox_id: UUID) -> None:
        return self.mark_as_published(outbox_id)

    @sync_to_async
    def mark_as_failed_async(self, outbox_id: UUID, error: str) -> None:
        return self.mark_as_failed(outbox_id, error)
    



