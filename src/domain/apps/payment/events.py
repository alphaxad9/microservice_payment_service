# src/domain/apps/payment/events.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Type, Optional
from uuid import UUID, uuid4

# Shared domain event base (assumed to exist in shared kernel)
from src.domain.shared.events import DomainEvent


# ------------------------
# Payment Event Type Enum
# ------------------------
class PaymentEventType(Enum):
    """Enumeration of all payment domain event types."""
    PAYMENT_CREATED = "payment.created"
    PAYMENT_PROCESSED = "payment.processed"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_CANCELLED = "payment.cancelled"
    PAYMENT_REFUNDED = "payment.refunded"


# ------------------------
# Base Payment Event (Abstract)
# ------------------------
@dataclass(frozen=True, kw_only=True)
class PaymentEvent(DomainEvent, ABC):
    """
    Base class for all payment domain events.
    Inherits common fields from DomainEvent and adds payment context.
    """
    payment_id: UUID
    wallet_id: UUID
    user_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, UUID):
            raise TypeError("payment_id must be a UUID")
        if not isinstance(self.wallet_id, UUID):
            raise TypeError("wallet_id must be a UUID")
        if not isinstance(self.user_id, UUID):
            raise TypeError("user_id must be a UUID")

    @property
    @abstractmethod
    def event_type(self) -> str:
        """Concrete subclasses return PaymentEventType.value."""
        raise NotImplementedError()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "payment_id": str(self.payment_id),
            "wallet_id": str(self.wallet_id),
            "user_id": str(self.user_id),
        })
        return base

    @classmethod
    def base_from_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        occurred_at = (
            datetime.fromisoformat(data["occurred_at"])
            if "occurred_at" in data
            else datetime.now(timezone.utc)
        )

        return {
            "event_id": UUID(data.get("event_id", str(uuid4()))),
            "occurred_at": occurred_at,
            "schema_version": data.get("schema_version", 1),
            "payment_id": UUID(data["payment_id"]),
            "wallet_id": UUID(data["wallet_id"]),
            "user_id": UUID(data["user_id"]),
        }


# ------------------------
# Concrete Payment Events
# ------------------------

@dataclass(frozen=True, kw_only=True)
class PaymentCreatedEvent(PaymentEvent):
    amount: Decimal
    currency: str
    payment_type: str
    payment_method: str
    reference_id: Optional[UUID] = None
    description: Optional[str] = None

    @property
    def event_type(self) -> str:
        return PaymentEventType.PAYMENT_CREATED.value

    def payload(self) -> Dict[str, Any]:
        return {
            "amount": str(self.amount),
            "currency": self.currency,
            "payment_type": self.payment_type,
            "payment_method": self.payment_method,
            "reference_id": str(self.reference_id) if self.reference_id else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentCreatedEvent":
        base = cls.base_from_dict(data)
        payload = data.get("payload", {})
        base["amount"] = Decimal(payload.get("amount", "0"))
        base["currency"] = payload.get("currency", "USD")
        base["payment_type"] = payload.get("payment_type", "payment")
        base["payment_method"] = payload.get("payment_method", "other")
        ref_id = payload.get("reference_id")
        base["reference_id"] = UUID(ref_id) if ref_id else None
        base["description"] = payload.get("description")
        return cls(**base)


@dataclass(frozen=True, kw_only=True)
class PaymentProcessedEvent(PaymentEvent):
    @property
    def event_type(self) -> str:
        return PaymentEventType.PAYMENT_PROCESSED.value

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentProcessedEvent":
        base = cls.base_from_dict(data)
        return cls(**base)


@dataclass(frozen=True, kw_only=True)
class PaymentSucceededEvent(PaymentEvent):
    @property
    def event_type(self) -> str:
        return PaymentEventType.PAYMENT_SUCCEEDED.value

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentSucceededEvent":
        base = cls.base_from_dict(data)
        return cls(**base)


@dataclass(frozen=True, kw_only=True)
class PaymentFailedEvent(PaymentEvent):
    failure_reason: Optional[str] = None

    @property
    def event_type(self) -> str:
        return PaymentEventType.PAYMENT_FAILED.value

    def payload(self) -> Dict[str, Any]:
        return {
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentFailedEvent":
        base = cls.base_from_dict(data)
        payload = data.get("payload", {})
        base["failure_reason"] = payload.get("failure_reason")
        return cls(**base)


@dataclass(frozen=True, kw_only=True)
class PaymentCancelledEvent(PaymentEvent):
    @property
    def event_type(self) -> str:
        return PaymentEventType.PAYMENT_CANCELLED.value

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentCancelledEvent":
        base = cls.base_from_dict(data)
        return cls(**base)


@dataclass(frozen=True, kw_only=True)
class PaymentRefundedEvent(PaymentEvent):
    refunded_amount: Decimal
    currency: str
    refund_id: UUID  # ID of the new refund payment

    @property
    def event_type(self) -> str:
        return PaymentEventType.PAYMENT_REFUNDED.value

    def payload(self) -> Dict[str, Any]:
        return {
            "refunded_amount": str(self.refunded_amount),
            "currency": self.currency,
            "refund_id": str(self.refund_id),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentRefundedEvent":
        base = cls.base_from_dict(data)
        payload = data.get("payload", {})
        base["refunded_amount"] = Decimal(payload.get("refunded_amount", "0"))
        base["currency"] = payload.get("currency", "USD")
        base["refund_id"] = UUID(payload["refund_id"])
        return cls(**base)


# ---------------------------------------------------------
# Event Type → Class Registry
# ---------------------------------------------------------
def normalize_payment_event_type(event_type: str) -> str:
    """
    Normalize event type string to canonical PaymentEventType.value.
    Supports:
      - canonical: "payment.created"
      - enum name: "PAYMENT_CREATED"
      - class name: "PaymentCreatedEvent"
    """
    # Already canonical
    if event_type in PAYMENT_EVENT_REGISTRY:
        return event_type

    # From enum name (e.g., "PAYMENT_CREATED")
    try:
        return PaymentEventType[event_type].value
    except KeyError:
        pass

    # From class name (e.g., "PaymentCreatedEvent" → "PAYMENT_CREATED")
    try:
        class_name = event_type
        if class_name.endswith("Event"):
            class_name = class_name[:-5]
        enum_name = "".join(
            ["_" + c if c.isupper() else c for c in class_name]
        ).upper().lstrip("_")
        return PaymentEventType[enum_name].value
    except KeyError:
        pass

    raise ValueError(f"Unknown payment event type: {event_type}")


PAYMENT_EVENT_REGISTRY: Dict[str, Type[PaymentEvent]] = {
    PaymentEventType.PAYMENT_CREATED.value: PaymentCreatedEvent,
    PaymentEventType.PAYMENT_PROCESSED.value: PaymentProcessedEvent,
    PaymentEventType.PAYMENT_SUCCEEDED.value: PaymentSucceededEvent,
    PaymentEventType.PAYMENT_FAILED.value: PaymentFailedEvent,
    PaymentEventType.PAYMENT_CANCELLED.value: PaymentCancelledEvent,
    PaymentEventType.PAYMENT_REFUNDED.value: PaymentRefundedEvent,
}


# ---------------------------------------------------------
# Event Reconstruction Helper
# ---------------------------------------------------------
def event_from_dict(
    *,
    event_type: str,
    event_payload: Dict[str, Any],
) -> PaymentEvent:
    normalized_type = normalize_payment_event_type(event_type)
    event_cls = PAYMENT_EVENT_REGISTRY.get(normalized_type)
    if not event_cls:
        raise ValueError(f"Unknown payment event type: {event_type}")
    return event_cls.from_dict(event_payload)