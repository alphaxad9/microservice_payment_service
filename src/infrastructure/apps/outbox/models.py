import uuid
from django.db import models
from django.utils import timezone

class EventOutbox(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core event data
    event_type = models.CharField(max_length=255, db_index=True)
    event_payload = models.JSONField()
    
    # DDD / Tracing
    aggregate_id = models.UUIDField(db_index=True)
    aggregate_type = models.CharField(max_length=100, db_index=True)
    aggregate_version = models.PositiveIntegerField() 
    # Observability
    trace_id = models.UUIDField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timing
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Resilience
    retry_count = models.PositiveSmallIntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)
    class Meta:
        db_table = "event_outbox"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=['aggregate_id', 'aggregate_version'],
                name='unique_aggregate_version'
            )
        ]

        indexes = [
            models.Index(
                fields=['processed_at', 'created_at'],
                name='outbox_polling_idx'
            )
        ]

    def __str__(self) -> str:
        status = "✅" if self.processed_at else "⏳"
        return f"{status} {self.event_type} ({self.aggregate_type}:{self.aggregate_id})"