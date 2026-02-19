# src/infrastructure/apps/idempotency/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid

from src.domain.idempotency.models import IdempotencyStatus


class IdempotencyKey(models.Model):
    """
    Django ORM model mirroring the domain IdempotencyKey aggregate.
    """
    idempotency_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('idempotency ID')
    )
    key = models.CharField(
        _('idempotency key'),
        max_length=255,
        help_text=_('Client-provided unique idempotency key')
    )
    user_id = models.UUIDField(
        _('user ID'),
        help_text=_('UUID of the user initiating the request')
    )
    fingerprint = models.CharField(
        _('request fingerprint'),
        max_length=64,  # SHA-256 hex digest
        help_text=_('Canonical SHA-256 hash of the request payload')
    )
    expires_at = models.DateTimeField(
        _('expires at'),
        help_text=_('Timestamp after which this key is considered expired')
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=[(status.name, status.value) for status in IdempotencyStatus],
        default=IdempotencyStatus.PENDING.name,
        help_text=_('Current lifecycle state of the idempotency key')
    )
    response_data = models.JSONField(
        _('response data'),
        null=True,
        blank=True,
        help_text=_('Serialized StoredResponse: {status_code, headers, body}')
    )
    request_id = models.UUIDField(_('request ID'), null=True, blank=True)
    correlation_id = models.UUIDField(_('correlation ID'), null=True, blank=True)
    locked_until = models.DateTimeField(_('locked until'), null=True, blank=True)
    locked_by = models.CharField(_('locked by'), max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    # Optional debugging fields
    request_method = models.CharField(_('request method'), max_length=10, null=True, blank=True)
    request_path = models.CharField(_('request path'), max_length=255, null=True, blank=True)
    client_ip = models.GenericIPAddressField(_('client IP'), null=True, blank=True)

    class Meta:
        db_table = 'idempotency_keys'
        verbose_name = _('idempotency key')
        verbose_name_plural = _('idempotency keys')
        constraints = [
            models.UniqueConstraint(
                fields=['key', 'user_id'],
                name='unique_key_per_user'
            ),
            models.UniqueConstraint(
                fields=['key', 'user_id', 'fingerprint'],
                name='unique_key_user_fingerprint'
            ),
            # Only PENDING keys can have locks; terminal states must be unlocked
            models.CheckConstraint(
                condition=(
                    models.Q(status=IdempotencyStatus.PENDING.name) |
                    models.Q(locked_until__isnull=True, locked_by__isnull=True)
                ),
                name='no_locks_on_terminal_states'
            ),
        ]
        indexes = [
            models.Index(fields=['key', 'user_id'], name='idx_key_user'),
            models.Index(fields=['user_id', 'status'], name='idx_user_status'),
            models.Index(fields=['fingerprint'], name='idx_fingerprint'),
            models.Index(fields=['expires_at'], name='idx_expires_at'),
            models.Index(fields=['locked_until'], name='idx_locked_until'),
            models.Index(fields=['created_at'], name='idx_created_at'),
        ]

    def __str__(self) -> str:
        return (
            f"IdempotencyKey(id={self.idempotency_id}, key='{self.key[:20]}...', "
            f"user={self.user_id}, status={self.status})"
        )