# tests/payment/services/test_payment_command_service.py

import pytest
from unittest.mock import AsyncMock
from decimal import Decimal
from uuid import UUID, uuid4

from src.domain.apps.payment.aggregate import PaymentAggregate
from src.domain.apps.payment.models import PaymentMethod, PaymentStatus
from src.domain.apps.payment.exceptions import (
    PaymentNotFoundError,
    InvalidPaymentAmountError,
    PaymentMethodNotSupportedError,
    RefundAmountExceedsOriginalError,
    PaymentAlreadyProcessedError,
)
from src.application.payment.services.payment_command_service import PaymentCommandService


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return PaymentCommandService(repo=mock_repo)


@pytest.fixture
def valid_payment_data():
    return {
        "wallet_id": uuid4(),
        "user_id": uuid4(),
        "amount": Decimal("100.00"),
        "currency": "USD",
        # ⚠️ Use lowercase to match enum values
        "payment_method": "credit_card",
        "booking_id": uuid4(),
        "reference_id": uuid4(),
    }


# ========================
# CREATE DEPOSIT
# ========================

@pytest.mark.asyncio
async def test_create_deposit_success(service, mock_repo, valid_payment_data):
    payment_id = uuid4()
    mock_repo.create = AsyncMock()

    result = await service.create_deposit(
        wallet_id=valid_payment_data["wallet_id"],
        user_id=valid_payment_data["user_id"],
        amount=valid_payment_data["amount"],
        currency=valid_payment_data["currency"],
        payment_method=valid_payment_data["payment_method"],  # now 'credit_card'
        reference_id=valid_payment_data["reference_id"],
        description="Test deposit",
        payment_id=payment_id,
    )

    assert isinstance(result, UUID)
    mock_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_deposit_invalid_method(service, valid_payment_data):
    with pytest.raises(ValueError, match="Invalid payment method"):
        await service.create_deposit(
            wallet_id=valid_payment_data["wallet_id"],
            user_id=valid_payment_data["user_id"],
            amount=valid_payment_data["amount"],
            currency=valid_payment_data["currency"],
            payment_method="INVALID_METHOD",
        )


@pytest.mark.asyncio
async def test_create_deposit_negative_amount(service, valid_payment_data):
    with pytest.raises(InvalidPaymentAmountError):
        await service.create_deposit(
            wallet_id=valid_payment_data["wallet_id"],
            user_id=valid_payment_data["user_id"],
            amount=Decimal("-10.00"),
            currency=valid_payment_data["currency"],
            payment_method=valid_payment_data["payment_method"],
        )


# ========================
# CREATE WITHDRAWAL
# ========================

@pytest.mark.asyncio
async def test_create_withdrawal_wallet_method_rejected(service, valid_payment_data):
    # Note: 'wallet' is valid enum value, but domain forbids it for withdrawal
    with pytest.raises(PaymentMethodNotSupportedError):
        await service.create_withdrawal(
            wallet_id=valid_payment_data["wallet_id"],
            user_id=valid_payment_data["user_id"],
            amount=valid_payment_data["amount"],
            currency=valid_payment_data["currency"],
            payment_method="wallet",  # lowercase!
        )


# ========================
# CREATE PAYMENT FOR BOOKING
# ========================

@pytest.mark.asyncio
async def test_create_payment_for_booking_success(service, mock_repo, valid_payment_data):
    payment_id = uuid4()
    mock_repo.create = AsyncMock()

    result = await service.create_payment_for_booking(
        wallet_id=valid_payment_data["wallet_id"],
        user_id=valid_payment_data["user_id"],
        amount=valid_payment_data["amount"],
        currency=valid_payment_data["currency"],
        payment_method=valid_payment_data["payment_method"],
        booking_id=valid_payment_data["booking_id"],
        payment_id=payment_id,
    )

    assert result == payment_id
    mock_repo.create.assert_awaited_once()


# ========================
# CREATE REFUND
# ========================

@pytest.mark.asyncio
async def test_create_refund_success(service, mock_repo, valid_payment_data):
    original_payment_id = uuid4()
    refund_id = uuid4()
    original_payment = PaymentAggregate(
        payment_id=original_payment_id,
        wallet_id=valid_payment_data["wallet_id"],
        user_id=valid_payment_data["user_id"],
        amount=Decimal("200.00"),
        currency="USD",
        payment_type="PAYMENT",
        payment_method=PaymentMethod.CREDIT_CARD,
        status=PaymentStatus.SUCCEEDED,
    )
    mock_repo.load = AsyncMock(return_value=original_payment)
    mock_repo.create = AsyncMock()

    result = await service.create_refund(
        wallet_id=valid_payment_data["wallet_id"],
        user_id=valid_payment_data["user_id"],
        amount=Decimal("50.00"),
        currency="USD",
        original_payment_id=original_payment_id,
        refund_id=refund_id,
    )

    assert result == refund_id
    mock_repo.load.assert_awaited_once_with(original_payment_id)
    mock_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_refund_exceeds_original(service, mock_repo, valid_payment_data):
    original_payment_id = uuid4()
    original_payment = PaymentAggregate(
        payment_id=original_payment_id,
        wallet_id=valid_payment_data["wallet_id"],
        user_id=valid_payment_data["user_id"],
        amount=Decimal("100.00"),
        currency="USD",
        payment_type="PAYMENT",
        payment_method=PaymentMethod.CREDIT_CARD,
        status=PaymentStatus.SUCCEEDED,
    )
    mock_repo.load = AsyncMock(return_value=original_payment)

    with pytest.raises(RefundAmountExceedsOriginalError):
        await service.create_refund(
            wallet_id=valid_payment_data["wallet_id"],
            user_id=valid_payment_data["user_id"],
            amount=Decimal("150.00"),
            currency="USD",
            original_payment_id=original_payment_id,
        )


@pytest.mark.asyncio
async def test_create_refund_original_not_found(service, mock_repo, valid_payment_data):
    mock_repo.load.side_effect = PaymentNotFoundError(payment_id=uuid4())

    with pytest.raises(PaymentNotFoundError):
        await service.create_refund(
            wallet_id=valid_payment_data["wallet_id"],
            user_id=valid_payment_data["user_id"],
            amount=Decimal("50.00"),
            currency="USD",
            original_payment_id=uuid4(),
        )


# ========================
# STATE TRANSITIONS
# ========================

@pytest.mark.asyncio
async def test_succeed_payment_success(service, mock_repo, valid_payment_data):
    payment_id = uuid4()
    aggregate = PaymentAggregate(
        payment_id=payment_id,
        wallet_id=valid_payment_data["wallet_id"],
        user_id=valid_payment_data["user_id"],
        amount=Decimal("100.00"),
        currency="USD",
        payment_type="PAYMENT",
        payment_method=PaymentMethod.CREDIT_CARD,
        status=PaymentStatus.PENDING,
    )
    mock_repo.load = AsyncMock(return_value=aggregate)
    mock_repo.save = AsyncMock()

    await service.succeed_payment(payment_id)

    mock_repo.load.assert_awaited_once_with(payment_id)
    mock_repo.save.assert_awaited_once()
    assert aggregate.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_succeed_already_succeeded_payment(service, mock_repo, valid_payment_data):
    payment_id = uuid4()
    aggregate = PaymentAggregate(
        payment_id=payment_id,
        wallet_id=valid_payment_data["wallet_id"],
        user_id=valid_payment_data["user_id"],
        amount=Decimal("100.00"),
        currency="USD",
        payment_type="PAYMENT",
        payment_method=PaymentMethod.CREDIT_CARD,
        status=PaymentStatus.SUCCEEDED,
    )
    mock_repo.load = AsyncMock(return_value=aggregate)

    with pytest.raises(PaymentAlreadyProcessedError):
        await service.succeed_payment(payment_id)


# ========================
# VALIDATION ERRORS
# ========================

@pytest.mark.asyncio
async def test_create_deposit_missing_user_id(service, valid_payment_data):
    # ✅ Match the exact error message
    with pytest.raises(ValueError, match="wallet_id and user_id are required"):
        await service.create_deposit(
            wallet_id=valid_payment_data["wallet_id"],
            user_id=None,
            amount=valid_payment_data["amount"],
            currency=valid_payment_data["currency"],
            payment_method=valid_payment_data["payment_method"],
        )


@pytest.mark.asyncio
async def test_process_payment_missing_id(service):
    with pytest.raises(ValueError, match="payment_id is required"):
        await service.process_payment(None)


# ========================
# REPOSITORY ERROR HANDLING
# ========================

@pytest.mark.asyncio
async def test_create_deposit_repo_failure(service, mock_repo, valid_payment_data):
    mock_repo.create.side_effect = Exception("DB down")

    with pytest.raises(RuntimeError, match="Failed to persist payment after deposit"):
        await service.create_deposit(
            wallet_id=valid_payment_data["wallet_id"],
            user_id=valid_payment_data["user_id"],
            amount=valid_payment_data["amount"],
            currency=valid_payment_data["currency"],
            payment_method=valid_payment_data["payment_method"],
        )