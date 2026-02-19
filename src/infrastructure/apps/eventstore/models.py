import uuid
from django.db import models
from django.utils import timezone


class EventStore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    aggregate_id = models.UUIDField(db_index=True)
    aggregate_type = models.CharField(max_length=100)
    aggregate_version = models.PositiveIntegerField()
    event_type = models.CharField(max_length=255)
    event_payload = models.JSONField()
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "event_store"
        ordering = ["aggregate_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["aggregate_id", "aggregate_version"],
                name="unique_aggregate_event_version",
            )
        ]
        indexes = [
            models.Index(fields=["aggregate_id", "aggregate_type"]),
            models.Index(fields=["created_at"]),
        ]


class ProjectionState(models.Model):
    """
    Tracks the state of each projection for versioning and rebuild safety.
    """
    projection_name = models.CharField(max_length=100, unique=True)
    last_event_id = models.UUIDField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projection_state"

    def __str__(self):
        return f"{self.projection_name} (v{self.version}) @ {self.last_event_id}"