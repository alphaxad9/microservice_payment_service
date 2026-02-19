# src/domain/apps/payment/exceptions.py

from __future__ import annotations
from decimal import Decimal
from typing import Optional
from uuid import UUID


class PaymentDomainError(Exception):
    """Base exception for all payment-related domain errors."""
    pass


class PaymentAlreadyProcessedError(PaymentDomainError):
    """
    Raised when an operation is attempted on a payment that has already been finalized
    (e.g., trying to succeed a failed or refunded payment).
    """
    def __init__(
        self,
        payment_id: UUID | str,
        current_status: str,
        message: Optional[str] = None
    ):
        if isinstance(payment_id, UUID):
            payment_id = str(payment_id)
        if message is None:
            message = (
                f"Payment {payment_id} is already {current_status} "
                f"and cannot be processed again."
            )
        self.payment_id = payment_id
        self.current_status = current_status
        super().__init__(message)


class PaymentNotProcessableError(PaymentDomainError):
    """
    Raised when an action (e.g., cancel, refund) is attempted in an invalid state.
    """
    def __init__(
        self,
        payment_id: UUID | str,
        status: str,
        attempted_action: str,
        message: Optional[str] = None
    ):
        if isinstance(payment_id, UUID):
            payment_id = str(payment_id)
        if message is None:
            message = (
                f"Cannot {attempted_action} payment {payment_id} "
                f"because it is in status '{status}'."
            )
        self.payment_id = payment_id
        self.status = status
        self.attempted_action = attempted_action
        super().__init__(message)


class InvalidPaymentAmountError(PaymentDomainError, ValueError):
    """
    Raised when a payment amount is zero or negative.
    """
    def __init__(
        self,
        amount: Decimal | str,
        message: Optional[str] = None
    ):
        if isinstance(amount, Decimal):
            amount_str = str(amount)
        else:
            amount_str = amount
        if message is None:
            message = f"Payment amount must be positive. Got: {amount_str}"
        self.amount = amount
        super().__init__(message)


class PaymentMethodNotSupportedError(PaymentDomainError, ValueError):
    """
    Raised when an unsupported payment method is used for a specific operation
    (e.g., using PayPal for a refund).
    """
    def __init__(
        self,
        method: str,
        operation: str,
        message: Optional[str] = None
    ):
        if message is None:
            message = f"Payment method '{method}' is not supported for {operation}."
        self.method = method
        self.operation = operation
        super().__init__(message)


class PaymentNotFoundError(PaymentDomainError, LookupError):
    """
    Raised when a payment is not found by ID or reference.
    """
    def __init__(
        self,
        payment_id: UUID | str | None = None,
        reference_id: UUID | str | None = None,
        message: Optional[str] = None
    ):
        if isinstance(payment_id, UUID):
            payment_id = str(payment_id)
        if isinstance(reference_id, UUID):
            reference_id = str(reference_id)

        if message is None:
            if payment_id:
                message = f"Payment not found (ID: {payment_id})"
            elif reference_id:
                message = f"No payment found for reference (ID: {reference_id})"
            else:
                message = "Payment not found"
        self.payment_id = payment_id
        self.reference_id = reference_id
        super().__init__(message)


class PaymentCurrencyMismatchError(PaymentDomainError, ValueError):
    """
    Raised when a payment operation involves a currency different from the payment's declared currency.
    """
    def __init__(
        self,
        payment_id: UUID | str,
        payment_currency: str,
        operation_currency: str,
        message: Optional[str] = None
    ):
        if isinstance(payment_id, UUID):
            payment_id = str(payment_id)
        if message is None:
            message = (
                f"Currency mismatch for payment {payment_id}: "
                f"payment currency is '{payment_currency}', "
                f"but operation used '{operation_currency}'."
            )
        self.payment_id = payment_id
        self.payment_currency = payment_currency
        self.operation_currency = operation_currency
        super().__init__(message)


class RefundAmountExceedsOriginalError(PaymentDomainError, ValueError):
    """
    Raised when a refund amount exceeds the original payment amount.
    """
    def __init__(
        self,
        original_payment_id: UUID | str,
        original_amount: Decimal | str,
        refund_amount: Decimal | str,
        currency: str,
        message: Optional[str] = None
    ):
        if isinstance(original_payment_id, UUID):
            original_payment_id = str(original_payment_id)
        if isinstance(original_amount, Decimal):
            original_amount = str(original_amount)
        if isinstance(refund_amount, Decimal):
            refund_amount = str(refund_amount)

        if message is None:
            message = (
                f"Refund amount {refund_amount} {currency} exceeds original payment "
                f"amount {original_amount} {currency} for payment {original_payment_id}."
            )
        self.original_payment_id = original_payment_id
        self.original_amount = original_amount
        self.refund_amount = refund_amount
        self.currency = currency
        super().__init__(message)