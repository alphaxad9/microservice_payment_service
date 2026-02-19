# tests/application/idempotency/handlers/test_query_handler.py
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from src.application.idempotency.handlers.idempotency_query_handlers import IdempotencyQueryHandler
from src.domain.idempotency.models import IdempotencyKey, IdempotencyStatus, StoredResponse
from src.domain.idempotency.exceptions import IdempotencyKeyNotFoundError


@pytest.fixture
def mock_query_service():
    return AsyncMock()


@pytest.fixture
def query_handler(mock_query_service):
    return IdempotencyQueryHandler(idempotency_queries=mock_query_service)


@pytest.fixture
def sample_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_key_str() -> str:
    return "req-12345"


@pytest.fixture
def sample_fingerprint() -> str:
    return "a1b2c3d4e5" * 6  # 60-char fake SHA-256-like string


@pytest.fixture
def sample_idempotency_key(sample_key_str, sample_user_id, sample_fingerprint) -> IdempotencyKey:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=10)
    return IdempotencyKey(
        key=sample_key_str,
        user_id=sample_user_id,
        fingerprint=sample_fingerprint,
        expires_at=expires_at,
        status=IdempotencyStatus.PENDING,
    )


class TestIdempotencyQueryHandler:

    @pytest.mark.asyncio
    async def test_get_key_success(self, query_handler, mock_query_service, sample_idempotency_key, sample_key_str, sample_user_id):
        mock_query_service.get_key.return_value = sample_idempotency_key

        result = await query_handler.get_key(key=sample_key_str, user_id=sample_user_id)

        assert result == sample_idempotency_key
        mock_query_service.get_key.assert_awaited_once_with(key=sample_key_str, user_id=sample_user_id)

    @pytest.mark.asyncio
    async def test_get_key_not_found(self, query_handler, mock_query_service, sample_key_str, sample_user_id):
        mock_query_service.get_key.side_effect = IdempotencyKeyNotFoundError(key=sample_key_str)

        with pytest.raises(IdempotencyKeyNotFoundError):
            await query_handler.get_key(key=sample_key_str, user_id=sample_user_id)

        mock_query_service.get_key.assert_awaited_once_with(key=sample_key_str, user_id=sample_user_id)

    @pytest.mark.asyncio
    async def test_get_key_unexpected_error_wrapped(self, query_handler, mock_query_service, sample_key_str, sample_user_id):
        mock_query_service.get_key.side_effect = RuntimeError("DB timeout")

        with pytest.raises(IdempotencyKeyNotFoundError) as exc_info:
            await query_handler.get_key(key=sample_key_str, user_id=sample_user_id)

        assert f"Failed to retrieve idempotency key '{sample_key_str}' for user {sample_user_id}" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        mock_query_service.get_key.assert_awaited_once_with(key=sample_key_str, user_id=sample_user_id)

    @pytest.mark.asyncio
    async def test_key_exists_true(self, query_handler, mock_query_service, sample_key_str, sample_user_id):
        mock_query_service.key_exists.return_value = True

        result = await query_handler.key_exists(key=sample_key_str, user_id=sample_user_id)

        assert result is True
        mock_query_service.key_exists.assert_awaited_once_with(key=sample_key_str, user_id=sample_user_id)

    @pytest.mark.asyncio
    async def test_key_exists_false_on_exception(self, query_handler, mock_query_service, sample_key_str, sample_user_id):
        mock_query_service.key_exists.side_effect = Exception("Network error")

        result = await query_handler.key_exists(key=sample_key_str, user_id=sample_user_id)

        assert result is False
        mock_query_service.key_exists.assert_awaited_once_with(key=sample_key_str, user_id=sample_user_id)

    @pytest.mark.asyncio
    async def test_get_keys_by_user_success(self, query_handler, mock_query_service, sample_user_id, sample_idempotency_key):
        mock_query_service.get_keys_by_user.return_value = [sample_idempotency_key]

        result = await query_handler.get_keys_by_user(user_id=sample_user_id, limit=10, offset=0)

        assert result == [sample_idempotency_key]
        mock_query_service.get_keys_by_user.assert_awaited_once_with(user_id=sample_user_id, limit=10, offset=0)

    @pytest.mark.asyncio
    async def test_get_keys_by_user_raises_runtime_error_on_failure(
        self, query_handler, mock_query_service, sample_user_id
    ):
        mock_query_service.get_keys_by_user.side_effect = ValueError("Invalid query")

        with pytest.raises(RuntimeError) as exc_info:
            await query_handler.get_keys_by_user(user_id=sample_user_id)

        assert f"Failed to retrieve idempotency keys for user {sample_user_id}" in str(exc_info.value)
        mock_query_service.get_keys_by_user.assert_awaited_once_with(user_id=sample_user_id, limit=100, offset=0)

    @pytest.mark.asyncio
    async def test_get_keys_by_status_success(self, query_handler, mock_query_service):
        mock_query_service.get_keys_by_status.return_value = []

        result = await query_handler.get_keys_by_status(status=IdempotencyStatus.COMPLETED, limit=50, offset=10)

        assert result == []
        mock_query_service.get_keys_by_status.assert_awaited_once_with(status=IdempotencyStatus.COMPLETED, limit=50, offset=10)

    @pytest.mark.asyncio
    async def test_get_expired_keys_success(self, query_handler, mock_query_service):
        mock_query_service.get_expired_keys.return_value = []

        result = await query_handler.get_expired_keys(limit=200, offset=0)

        assert result == []
        mock_query_service.get_expired_keys.assert_awaited_once_with(limit=200, offset=0)

    @pytest.mark.asyncio
    async def test_get_keys_by_fingerprint_success(
        self, query_handler, mock_query_service, sample_fingerprint, sample_user_id
    ):
        mock_query_service.get_keys_by_fingerprint.return_value = []

        result = await query_handler.get_keys_by_fingerprint(
            fingerprint=sample_fingerprint, user_id=sample_user_id, limit=10, offset=5
        )

        assert result == []
        mock_query_service.get_keys_by_fingerprint.assert_awaited_once_with(
            fingerprint=sample_fingerprint, user_id=sample_user_id, limit=10, offset=5
        )

    @pytest.mark.asyncio
    async def test_count_keys_by_user_success(self, query_handler, mock_query_service, sample_user_id):
        mock_query_service.count_keys_by_user.return_value = 42

        result = await query_handler.count_keys_by_user(user_id=sample_user_id)

        assert result == 42
        mock_query_service.count_keys_by_user.assert_awaited_once_with(user_id=sample_user_id)

    @pytest.mark.asyncio
    async def test_get_key_metrics_success(self, query_handler, mock_query_service):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        expected_metrics = {"total_keys": 100, "by_status": {"PENDING": 20, "COMPLETED": 80}}

        mock_query_service.get_key_metrics.return_value = expected_metrics

        result = await query_handler.get_key_metrics(start_date=start, end_date=end)

        assert result == expected_metrics
        mock_query_service.get_key_metrics.assert_awaited_once_with(start_date=start, end_date=end)

    @pytest.mark.asyncio
    async def test_get_key_metrics_raises_runtime_error_on_failure(self, query_handler, mock_query_service):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_query_service.get_key_metrics.side_effect = ConnectionError("DB down")

        with pytest.raises(RuntimeError, match="Failed to compute idempotency key metrics"):
            await query_handler.get_key_metrics(start_date=start, end_date=end)

        mock_query_service.get_key_metrics.assert_awaited_once_with(start_date=start, end_date=end)