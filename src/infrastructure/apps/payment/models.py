# src/infrastructure/apps/payment/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid
from decimal import Decimal

from src.domain.apps.payment.models import PaymentStatus, PaymentType, PaymentMethod


class PaymentReadModel(models.Model):
    """
    Read-optimized model for payments.
    Used for querying and displaying payment data in the query side (CQRS).
    Populated via projection of domain events from the write side (event sourcing).
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Unique payment identifier')
    )

    wallet_id = models.UUIDField(
        _('wallet ID'),
        help_text=_('UUID of the associated wallet')
    )

    user_id = models.UUIDField(
        _('user ID'),
        help_text=_('UUID of the user who initiated the payment')
    )

    amount = models.DecimalField(
        _('amount'),
        max_digits=19,
        decimal_places=4,
        help_text=_('Payment amount (always positive)')
    )

    currency = models.CharField(
        _('currency'),
        max_length=3,
        default='USD',
        help_text=_('ISO 4217 currency code (e.g., USD, EUR) in uppercase')
    )

    payment_type = models.CharField(
        _('payment type'),
        max_length=20,
        choices=[(ptype.name, ptype.value) for ptype in PaymentType],
        help_text=_('Type of payment: deposit, withdrawal, payment, refund, or adjustment')
    )

    payment_method = models.CharField(
        _('payment method'),
        max_length=20,
        choices=[(method.name, method.value) for method in PaymentMethod],
        help_text=_('Method used for the payment')
    )

    status = models.CharField(
        _('status'),
        max_length=20,
        choices=[(status.name, status.value) for status in PaymentStatus],
        default=PaymentStatus.PENDING.name,
        help_text=_('Current lifecycle status of the payment')
    )

    reference_id = models.UUIDField(
        _('reference ID'),
        null=True,
        blank=True,
        help_text=_('Optional reference to related entity (e.g., booking_id, original payment_id)')
    )

    description = models.TextField(
        _('description'),
        null=True,
        blank=True,
        help_text=_('Human-readable description or failure reason')
    )

    created_at = models.DateTimeField(
        _('created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('updated at'),
        auto_now=True
    )

    class Meta:
        db_table = 'payment_read_model'
        verbose_name = _('payment read model')
        verbose_name_plural = _('payment read models')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal('0')),
                name='check_payment_amount_positive'
            ),
        ]
        indexes = [
            models.Index(fields=['wallet_id'], name='idx_payment_read_wallet'),
            models.Index(fields=['user_id'], name='idx_payment_read_user'),
            models.Index(fields=['status'], name='idx_payment_read_status'),
            models.Index(fields=['payment_type'], name='idx_payment_read_type'),
            models.Index(fields=['reference_id'], name='idx_payment_read_reference'),
            models.Index(fields=['created_at'], name='idx_payment_read_created'),
        ]

    def __str__(self) -> str:
        return (
            f"Payment {self.id} ({self.payment_type}) "
            f"- {self.amount} {self.currency} ({self.status})"
        )