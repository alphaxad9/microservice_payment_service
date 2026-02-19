# tests/application/payment/handlers/test_payment_query_handler.py

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4
from decimal import Decimal
from datetime import datetime, timezone

from src.application.payment.handlers.payment_query_handler import PaymentQueryHandler
from src.application.payment.services.interfaces.payment_query_interface import PaymentQueryServiceInterface
from src.application.external.services.user_api_client import UserAPIClient
from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.domain.apps.payment.models import PaymentView
from src.application.payment.handlers.dtos import PaymentResponseDTO
from src.application.external.user_view import UserView


@pytest.fixture
def mock_payment_query_service() -> PaymentQueryServiceInterface:
    return AsyncMock(spec=PaymentQueryServiceInterface)


@pytest.fixture
def mock_user_client() -> UserAPIClient:
    return Mock(spec=UserAPIClient)


@pytest.fixture
def payment_handler(
    mock_payment_query_service: PaymentQueryServiceInterface,
    mock_user_client: UserAPIClient,
) -> PaymentQueryHandler:
    return PaymentQueryHandler(
        payment_queries=mock_payment_query_service,
        user_client=mock_user_client,
    )


@pytest.fixture
def sample_payment_view() -> PaymentView:
    return PaymentView(
        payment_id=uuid4(),
        wallet_id=uuid4(),
        user_id=uuid4(),
        amount="100.00",
        currency="USD",
        payment_type="payment",
        payment_method="credit_card",
        status="succeeded",
        reference_id=uuid4(),
        description="Test payment",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_user_view() -> UserView:
    return UserView(
        user_id=uuid4(),
        username="testuser",
    )


@pytest.mark.asyncio
async def test_get_payment_with_owner_success(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
    mock_user_client: Mock,
    sample_payment_view: PaymentView,
    sample_user_view: UserView,
):
    # Arrange
    mock_payment_query_service.get_payment.return_value = sample_payment_view
    mock_user_client.get_user_by_id.return_value = sample_user_view

    # Act
    result = await payment_handler.get_payment_with_owner(sample_payment_view.payment_id)

    # Assert
    assert isinstance(result, PaymentResponseDTO)
    assert result.payment == sample_payment_view
    assert result.owner == sample_user_view
    mock_payment_query_service.get_payment.assert_awaited_once_with(sample_payment_view.payment_id)
    mock_user_client.get_user_by_id.assert_called_once_with(sample_payment_view.user_id)


@pytest.mark.asyncio
async def test_get_payment_with_owner_user_client_fails(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
    mock_user_client: Mock,
    sample_payment_view: PaymentView,
):
    # Arrange
    mock_payment_query_service.get_payment.return_value = sample_payment_view
    mock_user_client.get_user_by_id.side_effect = Exception("User service down")

    # Act
    result = await payment_handler.get_payment_with_owner(sample_payment_view.payment_id)

    # Assert
    assert isinstance(result, PaymentResponseDTO)
    assert result.payment == sample_payment_view
    assert result.owner is None
    mock_payment_query_service.get_payment.assert_awaited_once_with(sample_payment_view.payment_id)
    mock_user_client.get_user_by_id.assert_called_once_with(sample_payment_view.user_id)


@pytest.mark.asyncio
async def test_get_payment_with_owner_payment_not_found(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
    sample_payment_view: PaymentView,
):
    # Arrange
    payment_id = sample_payment_view.payment_id
    mock_payment_query_service.get_payment.side_effect = PaymentNotFoundError(payment_id=str(payment_id))

    # Act & Assert
    with pytest.raises(PaymentNotFoundError):
        await payment_handler.get_payment_with_owner(payment_id)

    mock_payment_query_service.get_payment.assert_awaited_once_with(payment_id)


@pytest.mark.asyncio
async def test_get_payment_with_owner_unexpected_error(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
    sample_payment_view: PaymentView,
):
    # Arrange
    payment_id = sample_payment_view.payment_id
    mock_payment_query_service.get_payment.side_effect = RuntimeError("DB connection lost")

    # Act & Assert
    with pytest.raises(PaymentNotFoundError) as exc_info:
        await payment_handler.get_payment_with_owner(payment_id)

    assert str(payment_id) in str(exc_info.value)
    assert "DB connection lost" in str(exc_info.value.__cause__)
    mock_payment_query_service.get_payment.assert_awaited_once_with(payment_id)


@pytest.mark.asyncio
async def test_get_payments_by_wallet_with_owner_success(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
    mock_user_client: Mock,
    sample_payment_view: PaymentView,
    sample_user_view: UserView,
):
    # Arrange
    wallet_id = uuid4()
    mock_payment_query_service.get_payments_by_wallet.return_value = [sample_payment_view]
    mock_user_client.get_user_by_id.return_value = sample_user_view

    # Act
    results = await payment_handler.get_payments_by_wallet_with_owner(wallet_id, limit=10, offset=0)

    # Assert
    assert len(results) == 1
    assert isinstance(results[0], PaymentResponseDTO)
    assert results[0].payment == sample_payment_view
    assert results[0].owner == sample_user_view
    mock_payment_query_service.get_payments_by_wallet.assert_awaited_once_with(wallet_id, 10, 0)
    mock_user_client.get_user_by_id.assert_called_once_with(sample_payment_view.user_id)


@pytest.mark.asyncio
async def test_get_payments_by_user_with_owner_graceful_degradation(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
    mock_user_client: Mock,
    sample_payment_view: PaymentView,
):
    # Arrange
    user_id = uuid4()
    another_payment = PaymentView(
        payment_id=uuid4(),
        wallet_id=uuid4(),
        user_id=user_id,
        amount="50.00",
        currency="USD",
        payment_type="deposit",
        payment_method="wallet",
        status="pending",
        reference_id=None,
        description="Another test",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_payment_query_service.get_payments_by_user.return_value = [sample_payment_view, another_payment]
    mock_user_client.get_user_by_id.side_effect = [Exception("Fail first"), Mock()]

    # Act
    results = await payment_handler.get_payments_by_user_with_owner(user_id)

    # Assert
    assert len(results) == 2
    assert results[0].owner is None  # First failed
    assert results[1].owner is not None  # Second succeeded (mock object)
    mock_payment_query_service.get_payments_by_user.assert_awaited_once_with(user_id, 100, 0)
    assert mock_user_client.get_user_by_id.call_count == 2


@pytest.mark.asyncio
async def test_get_payments_by_reference_success(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
    sample_payment_view: PaymentView,
):
    # Arrange
    ref_id = uuid4()
    mock_payment_query_service.get_payments_by_reference.return_value = [sample_payment_view]

    # Act
    results = await payment_handler.get_payments_by_reference(ref_id)

    # Assert
    assert results == [sample_payment_view]
    mock_payment_query_service.get_payments_by_reference.assert_awaited_once_with(ref_id)


@pytest.mark.asyncio
async def test_get_total_amount_by_wallet_success(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
):
    # Arrange
    wallet_id = uuid4()
    expected_amount = Decimal("250.75")
    mock_payment_query_service.get_total_amount_by_wallet.return_value = expected_amount

    # Act
    result = await payment_handler.get_total_amount_by_wallet(wallet_id, status="succeeded")

    # Assert
    assert result == expected_amount
    mock_payment_query_service.get_total_amount_by_wallet.assert_awaited_once_with(wallet_id, "succeeded")


@pytest.mark.asyncio
async def test_payment_exists_true(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
):
    # Arrange
    payment_id = uuid4()
    mock_payment_query_service.payment_exists.return_value = True

    # Act
    result = await payment_handler.payment_exists(payment_id)

    # Assert
    assert result is True
    mock_payment_query_service.payment_exists.assert_awaited_once_with(payment_id)


@pytest.mark.asyncio
async def test_payment_exists_false_on_exception(
    payment_handler: PaymentQueryHandler,
    mock_payment_query_service: AsyncMock,
):
    # Arrange
    payment_id = uuid4()
    mock_payment_query_service.payment_exists.side_effect = Exception("Network error")

    # Act
    result = await payment_handler.payment_exists(payment_id)

    # Assert
    assert result is False
    mock_payment_query_service.payment_exists.assert_awaited_once_with(payment_id)