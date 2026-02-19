# tests/application/payment/services/test_payment_query_service.py

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.application.payment.services.payment_query_service import PaymentQueryService
from src.domain.apps.payment.models import PaymentView
from src.domain.apps.payment.exceptions import PaymentNotFoundError


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def payment_view():
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
        created_at=MagicMock(),
        updated_at=MagicMock(),
    )


@pytest.fixture
def service(mock_repo):
    return PaymentQueryService(query_repo=mock_repo)


class TestPaymentQueryService:

    @pytest.mark.asyncio
    async def test_get_payment_success(self, service, mock_repo, payment_view):
        # Arrange
        payment_id = uuid4()
        mock_repo.by_id.return_value = payment_view

        # Act
        result = await service.get_payment(payment_id)

        # Assert
        assert result == payment_view
        mock_repo.by_id.assert_awaited_once_with(payment_id)

    @pytest.mark.asyncio
    async def test_get_payment_not_found(self, service, mock_repo):
        # Arrange
        payment_id = uuid4()
        mock_repo.by_id.side_effect = PaymentNotFoundError(payment_id=payment_id)

        # Act & Assert
        with pytest.raises(PaymentNotFoundError):
            await service.get_payment(payment_id)

        mock_repo.by_id.assert_awaited_once_with(payment_id)

    @pytest.mark.asyncio
    async def test_get_payment_unexpected_error(self, service, mock_repo):
        # Arrange
        payment_id = uuid4()
        mock_repo.by_id.side_effect = Exception("DB timeout")

        # Act & Assert
        with pytest.raises(PaymentNotFoundError) as exc_info:
            await service.get_payment(payment_id)

        assert str(payment_id) in str(exc_info.value)
        mock_repo.by_id.assert_awaited_once_with(payment_id)

    @pytest.mark.asyncio
    async def test_get_payment_empty_id_raises_value_error(self, service):
        # Act & Assert
        with pytest.raises(ValueError, match="payment_id is required"):
            await service.get_payment(None)

    @pytest.mark.asyncio
    async def test_get_payments_by_wallet_success(self, service, mock_repo, payment_view):
        # Arrange
        wallet_id = uuid4()
        mock_repo.by_wallet_id.return_value = [payment_view]

        # Act
        result = await service.get_payments_by_wallet(wallet_id, limit=10, offset=0)

        # Assert
        assert result == [payment_view]
        mock_repo.by_wallet_id.assert_awaited_once_with(wallet_id, limit=10, offset=0)

    @pytest.mark.asyncio
    async def test_get_payments_by_wallet_not_found(self, service, mock_repo):
        # Arrange
        wallet_id = uuid4()
        mock_repo.by_wallet_id.side_effect = PaymentNotFoundError(payment_id=None)

        # Act & Assert
        with pytest.raises(PaymentNotFoundError):
            await service.get_payments_by_wallet(wallet_id)

        mock_repo.by_wallet_id.assert_awaited_once_with(wallet_id, limit=100, offset=0)

    @pytest.mark.asyncio
    async def test_get_payments_by_wallet_unexpected_error(self, service, mock_repo):
        # Arrange
        wallet_id = uuid4()
        mock_repo.by_wallet_id.side_effect = Exception("DB connection lost")

        # Act & Assert
        with pytest.raises(PaymentNotFoundError):
            await service.get_payments_by_wallet(wallet_id)

        mock_repo.by_wallet_id.assert_awaited_once_with(wallet_id, limit=100, offset=0)

    @pytest.mark.asyncio
    async def test_get_payments_by_wallet_empty_id_raises_value_error(self, service):
        # Act & Assert
        with pytest.raises(ValueError, match="wallet_id is required"):
            await service.get_payments_by_wallet(None)

    @pytest.mark.asyncio
    async def test_get_payments_by_user_success(self, service, mock_repo, payment_view):
        # Arrange
        user_id = uuid4()
        mock_repo.by_user_id.return_value = [payment_view]

        # Act
        result = await service.get_payments_by_user(user_id, limit=5, offset=20)

        # Assert
        assert result == [payment_view]
        mock_repo.by_user_id.assert_awaited_once_with(user_id, limit=5, offset=20)

    @pytest.mark.asyncio
    async def test_get_payments_by_user_unexpected_error(self, service, mock_repo):
        # Arrange
        user_id = uuid4()
        mock_repo.by_user_id.side_effect = Exception("Serialization error")

        # Act & Assert
        with pytest.raises(Exception, match="Serialization error"):
            await service.get_payments_by_user(user_id)

        mock_repo.by_user_id.assert_awaited_once_with(user_id, limit=100, offset=0)

    @pytest.mark.asyncio
    async def test_get_payments_by_user_empty_id_raises_value_error(self, service):
        # Act & Assert
        with pytest.raises(ValueError, match="user_id is required"):
            await service.get_payments_by_user(None)

    @pytest.mark.asyncio
    async def test_get_payments_by_reference_success(self, service, mock_repo, payment_view):
        # Arrange
        ref_id = uuid4()
        mock_repo.by_reference_id.return_value = [payment_view, payment_view]

        # Act
        result = await service.get_payments_by_reference(ref_id)

        # Assert
        assert result == [payment_view, payment_view]
        mock_repo.by_reference_id.assert_awaited_once_with(ref_id)

    @pytest.mark.asyncio
    async def test_get_payments_by_reference_error(self, service, mock_repo):
        # Arrange
        ref_id = uuid4()
        mock_repo.by_reference_id.side_effect = RuntimeError("Invalid query")

        # Act & Assert
        with pytest.raises(PaymentNotFoundError) as exc_info:
            await service.get_payments_by_reference(ref_id)

        assert str(ref_id) in str(exc_info.value.reference_id)
        mock_repo.by_reference_id.assert_awaited_once_with(ref_id)

    @pytest.mark.asyncio
    async def test_get_payments_by_reference_empty_id_raises_value_error(self, service):
        # Act & Assert
        with pytest.raises(ValueError, match="reference_id is required"):
            await service.get_payments_by_reference(None)

    @pytest.mark.asyncio
    async def test_get_total_amount_by_wallet_success(self, service, mock_repo):
        # Arrange
        wallet_id = uuid4()
        total = Decimal("250.75")
        mock_repo.get_total_amount_by_wallet.return_value = total

        # Act
        result = await service.get_total_amount_by_wallet(wallet_id, status="succeeded")

        # Assert
        assert result == total
        mock_repo.get_total_amount_by_wallet.assert_awaited_once_with(wallet_id, status="succeeded")

    @pytest.mark.asyncio
    async def test_get_total_amount_by_wallet_on_error_returns_zero(self, service, mock_repo):
        # Arrange
        wallet_id = uuid4()
        mock_repo.get_total_amount_by_wallet.side_effect = ConnectionError("DB down")

        # Act
        result = await service.get_total_amount_by_wallet(wallet_id)

        # Assert
        assert result == Decimal("0")
        mock_repo.get_total_amount_by_wallet.assert_awaited_once_with(wallet_id, status=None)

    @pytest.mark.asyncio
    async def test_get_total_amount_by_wallet_empty_id_raises_value_error(self, service):
        # Act & Assert
        with pytest.raises(ValueError, match="wallet_id is required"):
            await service.get_total_amount_by_wallet(None)

    @pytest.mark.asyncio
    async def test_payment_exists_true(self, service, mock_repo):
        # Arrange
        payment_id = uuid4()
        mock_repo.exists.return_value = True

        # Act
        result = await service.payment_exists(payment_id)

        # Assert
        assert result is True
        mock_repo.exists.assert_awaited_once_with(payment_id)

    @pytest.mark.asyncio
    async def test_payment_exists_false_on_error(self, service, mock_repo):
        # Arrange
        payment_id = uuid4()
        mock_repo.exists.side_effect = Exception("Cache unavailable")

        # Act
        result = await service.payment_exists(payment_id)

        # Assert
        assert result is False
        mock_repo.exists.assert_awaited_once_with(payment_id)

    @pytest.mark.asyncio
    async def test_payment_exists_empty_id_raises_value_error(self, service):
        # Act & Assert
        with pytest.raises(ValueError, match="payment_id is required"):
            await service.payment_exists(None)

    def test_validate_pagination_clamps_negative_values(self, service):
        # Act
        limit, offset = service._validate_pagination(-10, -5)

        # Assert
        assert limit == 0
        assert offset == 0

    def test_validate_pagination_keeps_positive_values(self, service):
        # Act
        limit, offset = service._validate_pagination(50, 100)

        # Assert
        assert limit == 50
        assert offset == 100