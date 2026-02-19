# src/domain/exceptions.py

from __future__ import annotations
from typing import Optional

class DomainError(Exception):
    """Base exception for all domain-related errors across bounded contexts."""
    pass


class DomainValueError(DomainError, ValueError):
    """Raised when a domain value is invalid (e.g., malformed ID, negative amount, invalid email)."""
    pass


class EntityNotFoundError(DomainError, LookupError):
    """Raised when an entity (user, wallet, booking, etc.) is not found."""
    def __init__(self, entity_type: str = "Entity", entity_id: str | None = None, message: str | None = None):
        if message is None:
            if entity_id:
                message = f"{entity_type} not found (ID: {entity_id})"
            else:
                message = f"{entity_type} not found"
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(message)


class EntityAlreadyExistsError(DomainError):
    """Raised when attempting to create an entity that already exists."""
    def __init__(
        self,
        entity_type: str = "Entity",
        entity_id: str | None = None,
        attributes: dict | None = None,
        message: str | None = None
    ):
        if message is None:
            if entity_id:
                message = f"{entity_type} already exists with ID: {entity_id}"
            elif attributes:
                attr_str = ", ".join(f"{k}={v}" for k, v in attributes.items())
                message = f"{entity_type} already exists with attributes: {attr_str}"
            else:
                message = f"{entity_type} already exists"
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.attributes = attributes
        super().__init__(message)


class InvalidStateTransitionError(DomainError):
    """Raised when an invalid state transition is attempted on an aggregate."""
    def __init__(
        self,
        aggregate_type: str,
        current_state: str,
        attempted_action: str,
        message: str | None = None
    ):
        if message is None:
            message = (
                f"Cannot perform '{attempted_action}' on {aggregate_type} "
                f"while in state '{current_state}'"
            )
        self.aggregate_type = aggregate_type
        self.current_state = current_state
        self.attempted_action = attempted_action
        super().__init__(message)


class PermissionDeniedError(DomainError, PermissionError):
    """Raised when an operation is not permitted for the current user or role."""
    def __init__(self, operation: str, subject: str | None = None, message: str | None = None):
        if message is None:
            if subject:
                message = f"Permission denied to perform '{operation}' on {subject}"
            else:
                message = f"Permission denied to perform '{operation}'"
        self.operation = operation
        self.subject = subject
        super().__init__(message)


class InsufficientFundsError(DomainError):
    """Raised when a wallet or account lacks sufficient balance for an operation."""
    def __init__(
        self,
        available: str | float | None = None,
        required: str | float | None = None,
        currency: str | None = None,
        wallet_id: str | None = None,
        message: str | None = None
    ):
        if message is None:
            base = "Insufficient funds"
            parts = []
            if wallet_id:
                parts.append(f"wallet {wallet_id}")
            if available is not None and required is not None:
                parts.append(f"(available: {available}, required: {required}")
                if currency:
                    parts[-1] += f" {currency})"
                else:
                    parts[-1] += ")"
            message = base + (" for " + ", ".join(parts) if parts else "")
        self.available = available
        self.required = required
        self.currency = currency
        self.wallet_id = wallet_id
        super().__init__(message)


class InvalidCurrencyError(DomainValueError):
    """Raised when a currency code is missing, empty, or unsupported."""
    def __init__(self, currency: str | None = None, message: str | None = None):
        if message is None:
            message = "Currency is required"
            if currency:
                message = f"Invalid or unsupported currency: {currency}"
        self.currency = currency
        super().__init__(message)


class ExpiredOperationError(DomainError):
    """Raised when an operation is attempted on an expired resource (e.g., booking, token)."""
    def __init__(
        self,
        resource_type: str = "Resource",
        resource_id: str | None = None,
        message: str | None = None
    ):
        if message is None:
            if resource_id:
                message = f"{resource_type} {resource_id} has expired"
            else:
                message = f"{resource_type} has expired"
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(message)


class ResourceAlreadyConsumedError(DomainError):
    """Raised when a one-time-use resource (e.g., token, voucher) is reused."""
    def __init__(
        self,
        resource_type: str = "Resource",
        resource_id: str | None = None,
        message: str | None = None
    ):
        if message is None:
            if resource_id:
                message = f"{resource_type} {resource_id} has already been used"
            else:
                message = f"{resource_type} has already been used"
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(message)


class ExternalServiceError(DomainError):
    """Raised when an external service (payment gateway, SMS, email) fails."""
    def __init__(
        self,
        service_name: str,
        operation: str | None = None,
        response: str | None = None,
        message: str | None = None
    ):
        if message is None:
            msg_parts = [f"External service '{service_name}' failed"]
            if operation:
                msg_parts.append(f" during '{operation}'")
            if response:
                msg_parts.append(f": {response}")
            message = "".join(msg_parts)
        self.service_name = service_name
        self.operation = operation
        self.response = response
        super().__init__(message)


class ProjectionInvariantViolation(DomainError):
    """
    Raised when a projection detects an invalid state transition or data inconsistency
    that violates domain invariants (e.g., applying an event to a read model in an
    unexpected state).
    
    This typically indicates either:
      - A bug in projection logic,
      - Out-of-order event processing,
      - A corrupted or stale read model,
      - Or a mismatch between event semantics and current state.
    """
    def __init__(self, message: str, payment_id: Optional[str] = None):
        self.payment_id = payment_id
        super().__init__(message)


class OptimisticConcurrencyError(Exception):
    """Raised when another process modified the aggregate since it was loaded."""
    pass