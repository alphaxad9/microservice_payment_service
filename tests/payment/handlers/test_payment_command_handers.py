# tests/application/payment/handlers/test_payment_command_handlers.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from uuid import UUID, uuid4
from datetime import datetime

from src.application.payment.handlers.payment_command_handlers import (
    PaymentCommandHandler,
    IdempotentPaymentExecutor,
)
from src.domain.apps.payment.models import PaymentView
from src.domain.apps.payment.exceptions import PaymentDomainError
from src.domain.idempotency.exceptions import (
    IdempotencyKeyReuseWithDifferentPayloadError,
    IdempotencyKeyInProgressError,
)


@pytest.fixture
def mock_command_service():
    return AsyncMock()


@pytest.fixture
def mock_query_service():
    return AsyncMock()


@pytest.fixture
def mock_idempotency_handler():
    return AsyncMock()


@pytest.fixture
def payment_view() -> PaymentView:
    now = datetime.now().isoformat()
    return PaymentView(
        payment_id=uuid4(),
        wallet_id=uuid4(),
        user_id=uuid4(),
        amount=Decimal("100.00"),
        currency="USD",
        status="pending",
        payment_method="card",
        description="Test payment",
        payment_type="deposit",
        reference_id=None,
        created_at=now,
        updated_at=now,
    )


# ── IdempotentPaymentExecutor Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_idempotent_executor_first_execution_success(
    mock_idempotency_handler, payment_view
):
    executor = IdempotentPaymentExecutor(mock_idempotency_handler)

    idempotency_key = "idemp-12345"
    user_id = uuid4()
    payload = {"amount": "100.00", "currency": "USD"}

    async def mock_execute() -> UUID:
        return payment_view.payment_id

    mock_fetch = AsyncMock(return_value=payment_view)

    # First time → begin_request_processing returns None (no previous result)
    mock_idempotency_handler.begin_request_processing.return_value = None

    result = await executor.execute_payment_creation(
        idempotency_key=idempotency_key,
        user_id=user_id,
        payload=payload,
        execute_command=mock_execute,
        fetch_view=mock_fetch,
    )

    assert result == payment_view

    mock_idempotency_handler.begin_request_processing.assert_awaited_once()
    mock_idempotency_handler.record_successful_response.assert_awaited_once_with(
        key=idempotency_key,
        user_id=user_id,
        body={
            "payment_id": str(payment_view.payment_id),
            "status": payment_view.status,
            "amount": str(payment_view.amount),
            "currency": payment_view.currency,
        },
    )


@pytest.mark.asyncio
async def test_idempotent_executor_replay_success(
    mock_idempotency_handler, payment_view
):
    executor = IdempotentPaymentExecutor(mock_idempotency_handler)

    idempotency_key = "idemp-12345"
    user_id = uuid4()
    payload = {"amount": "100.00", "currency": "USD"}

    stored = {
        "body": {
            "payment_id": str(payment_view.payment_id),
            "status": "succeeded",
            "amount": "100.00",
            "currency": "USD",
        }
    }

    mock_idempotency_handler.begin_request_processing.return_value = stored
    mock_fetch = AsyncMock(return_value=payment_view)

    result = await executor.execute_payment_creation(
        idempotency_key=idempotency_key,
        user_id=user_id,
        payload=payload,
        execute_command=AsyncMock(),  # should NOT be called
        fetch_view=mock_fetch,
    )

    assert result == payment_view
    mock_fetch.assert_awaited_once_with(payment_view.payment_id)
    mock_idempotency_handler.record_successful_response.assert_not_awaited()
    mock_idempotency_handler.record_failed_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_idempotent_executor_replay_error(
    mock_idempotency_handler, payment_view
):
    executor = IdempotentPaymentExecutor(mock_idempotency_handler)

    idempotency_key = "idemp-err-999"
    user_id = uuid4()
    payload = {"amount": "100.00", "currency": "USD"}

    stored = {"body": {"error": "Not enough balance"}}

    mock_idempotency_handler.begin_request_processing.return_value = stored

    with pytest.raises(PaymentDomainError, match="Not enough balance"):
        await executor.execute_payment_creation(
            idempotency_key=idempotency_key,
            user_id=user_id,
            payload=payload,
            execute_command=AsyncMock(),
            fetch_view=AsyncMock(),
        )

@pytest.mark.asyncio
async def test_idempotent_executor_failure_is_recorded(
    mock_idempotency_handler, payment_view
):
    executor = IdempotentPaymentExecutor(mock_idempotency_handler)

    idempotency_key = "fail-001"
    user_id = uuid4()

    mock_idempotency_handler.begin_request_processing.return_value = None

    async def failing_cmd():
        raise ValueError("Payment gateway timeout")

    with pytest.raises(ValueError, match="Payment gateway timeout"):
        await executor.execute_payment_creation(
            idempotency_key=idempotency_key,
            user_id=user_id,
            payload={},
            execute_command=failing_cmd,
            fetch_view=AsyncMock(),
        )

    mock_idempotency_handler.record_failed_response.assert_awaited_once()


# ── PaymentCommandHandler high-level tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_create_payment_for_booking_real_error_propagation(
    mock_command_service, mock_query_service, mock_idempotency_handler, payment_view
):
    handler = PaymentCommandHandler(
        command_service=mock_command_service,
        query_service=mock_query_service,
        idempotency_commands=mock_idempotency_handler,
    )

    mock_idempotency_handler.begin_request_processing.return_value = None

    original_exception = RuntimeError("Stripe internal server error 500")

    mock_command_service.create_payment_for_booking.side_effect = original_exception

    with pytest.raises(RuntimeError, match="Stripe internal server error 500"):
        await handler.create_payment_for_booking(
            idempotency_key="booking-777",
            wallet_id=uuid4(),
            user_id=uuid4(),
            amount=Decimal("250.00"),
            currency="USD",
            payment_method="card",
            booking_id=uuid4(),
        )

    # Important: original exception should NOT be wrapped!
    mock_idempotency_handler.record_failed_response.assert_awaited_once()












@pytest.mark.asyncio
async def test_idempotent_executor_in_progress_error(mock_idempotency_handler):
    executor = IdempotentPaymentExecutor(mock_idempotency_handler)
    key = "idemp-lock-2026-01-10"

    mock_idempotency_handler.begin_request_processing.side_effect = IdempotencyKeyInProgressError(key=key)

    with pytest.raises(PaymentDomainError) as exc_info:
        await executor.execute_payment_creation(
            idempotency_key=key,
            user_id=uuid4(),
            payload={},
            execute_command=AsyncMock(),
            fetch_view=AsyncMock(),
        )

    assert "already being processed" in str(exc_info.value)
    assert "retry" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_idempotent_executor_payload_conflict(mock_idempotency_handler):
    executor = IdempotentPaymentExecutor(mock_idempotency_handler)
    key = "idemp-mismatch-xyz"

    mock_idempotency_handler.begin_request_processing.side_effect = IdempotencyKeyReuseWithDifferentPayloadError(key=key)

    with pytest.raises(PaymentDomainError) as exc_info:
        await executor.execute_payment_creation(
            idempotency_key=key,
            user_id=uuid4(),
            payload={"type": "deposit"},
            execute_command=AsyncMock(),
            fetch_view=AsyncMock(),
        )

    assert "Idempotency conflict" in str(exc_info.value)
    assert "do not match" in str(exc_info.value)