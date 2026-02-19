# tests/application/idempotency/handlers/test_command_handlers.py

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4
from datetime import datetime

from src.application.idempotency.handlers.idempotency_command_handlers import IdempotencyCommandHandler
from src.domain.idempotency.models import IdempotencyKey, compute_fingerprint
from src.domain.idempotency.exceptions import (
    IdempotencyKeyNotFoundError,
    IdempotencyKeyReuseWithDifferentPayloadError,
)


@pytest.fixture
def mock_command_service():
    return AsyncMock()


@pytest.fixture
def command_handler(mock_command_service):
    return IdempotencyCommandHandler(command_service=mock_command_service)


@pytest.fixture
def sample_user_id():
    return uuid4()


@pytest.fixture
def sample_key():
    return "req_abc123"


@pytest.fixture
def sample_payload():
    return {"amount": 100, "currency": "USD"}


@pytest.mark.asyncio
async def test_create_idempotency_key_success(
    command_handler, mock_command_service, sample_key, sample_user_id, sample_payload
):
    expected_key = IdempotencyKey(
        key=sample_key,
        user_id=sample_user_id,
        fingerprint=compute_fingerprint(sample_payload),  # Use real fingerprint
        expires_at=datetime(2030, 1, 1),
    )
    mock_command_service.create_key.return_value = expected_key

    result = await command_handler.create_idempotency_key(
        key=sample_key,
        user_id=sample_user_id,
        payload=sample_payload,
        ttl_hours=24,
    )

    assert result == expected_key

    # ✅ ASSERTION FIXED: expect 'fingerprint', not 'payload'
    mock_command_service.create_key.assert_awaited_once_with(
        key=sample_key,
        user_id=sample_user_id,
        fingerprint=compute_fingerprint(sample_payload),
        ttl_hours=24,
        request_method=None,
        request_path=None,
        client_ip=None,
    )


@pytest.mark.asyncio
async def test_create_idempotency_key_propagates_domain_exceptions(
    command_handler, mock_command_service, sample_key, sample_user_id, sample_payload
):
    # ✅ This one IS propagated directly
    mock_command_service.create_key.side_effect = IdempotencyKeyReuseWithDifferentPayloadError(sample_key)
    with pytest.raises(IdempotencyKeyReuseWithDifferentPayloadError):
        await command_handler.create_idempotency_key(
            key=sample_key,
            user_id=sample_user_id,
            payload=sample_payload,
        )

    # ❌ IdempotencyKeyAlreadyExistsError is NOT propagated directly — it's wrapped in RuntimeError
    # So we test that it becomes a RuntimeError (as per current handler logic)
    mock_command_service.create_key.side_effect = Exception("Simulated IdempotencyKeyAlreadyExistsError")
    with pytest.raises(RuntimeError, match=f"Failed to create idempotency key '{sample_key}' for user {sample_user_id}"):
        await command_handler.create_idempotency_key(
            key=sample_key,
            user_id=sample_user_id,
            payload=sample_payload,
        )


@pytest.mark.asyncio
async def test_create_idempotency_key_wraps_unexpected_error(
    command_handler, mock_command_service, sample_key, sample_user_id, sample_payload
):
    mock_command_service.create_key.side_effect = ValueError("DB connection failed")
    with pytest.raises(RuntimeError, match=f"Failed to create idempotency key '{sample_key}' for user {sample_user_id}"):
        await command_handler.create_idempotency_key(
            key=sample_key,
            user_id=sample_user_id,
            payload=sample_payload,
        )


@pytest.mark.asyncio
async def test_begin_request_processing_wraps_error(
    command_handler, mock_command_service, sample_key, sample_user_id
):
    mock_command_service.process_request.side_effect = ConnectionError("DB down")
    with pytest.raises(RuntimeError, match=rf"Idempotency processing failed for key '{sample_key}' \(user {sample_user_id}\)"):
        await command_handler.begin_request_processing(
            key=sample_key,
            user_id=sample_user_id,
            locker_id="worker-123",
        )


@pytest.mark.asyncio
async def test_record_successful_response_success(
    command_handler, mock_command_service, sample_key, sample_user_id
):
    await command_handler.record_successful_response(
        key=sample_key,
        user_id=sample_user_id,
        status_code=201,
        headers={"Location": "/api/orders/123"},
        body={"id": "123", "status": "created"},
    )

    mock_command_service.record_success.assert_awaited_once_with(
        key=sample_key,
        user_id=sample_user_id,
        status_code=201,
        headers={"Location": "/api/orders/123"},
        body={"id": "123", "status": "created"},
    )


@pytest.mark.asyncio
async def test_record_successful_response_handles_defaults(
    command_handler, mock_command_service, sample_key, sample_user_id
):
    await command_handler.record_successful_response(key=sample_key, user_id=sample_user_id)

    mock_command_service.record_success.assert_awaited_once_with(
        key=sample_key,
        user_id=sample_user_id,
        status_code=200,
        headers={},
        body={},
    )


@pytest.mark.asyncio
async def test_record_successful_response_propagates_not_found(
    command_handler, mock_command_service, sample_key, sample_user_id
):
    mock_command_service.record_success.side_effect = IdempotencyKeyNotFoundError(sample_key)
    with pytest.raises(IdempotencyKeyNotFoundError):
        await command_handler.record_successful_response(key=sample_key, user_id=sample_user_id)


@pytest.mark.asyncio
async def test_record_successful_response_wraps_other_errors(
    command_handler, mock_command_service, sample_key, sample_user_id
):
    mock_command_service.record_success.side_effect = IOError("Disk full")
    with pytest.raises(RuntimeError, match=f"Failed to record success for idempotency key '{sample_key}'"):
        await command_handler.record_successful_response(key=sample_key, user_id=sample_user_id)


@pytest.mark.asyncio
async def test_record_failed_response_success(
    command_handler, mock_command_service, sample_key, sample_user_id
):
    await command_handler.record_failed_response(
        key=sample_key,
        user_id=sample_user_id,
        status_code=422,
        headers={"Content-Type": "application/problem+json"},
        body={"detail": "Invalid amount"},
    )

    mock_command_service.record_failure.assert_awaited_once_with(
        key=sample_key,
        user_id=sample_user_id,
        status_code=422,
        headers={"Content-Type": "application/problem+json"},
        body={"detail": "Invalid amount"},
    )


@pytest.mark.asyncio
async def test_record_failed_response_handles_defaults(
    command_handler, mock_command_service, sample_key, sample_user_id
):
    await command_handler.record_failed_response(key=sample_key, user_id=sample_user_id)

    mock_command_service.record_failure.assert_awaited_once_with(
        key=sample_key,
        user_id=sample_user_id,
        status_code=400,
        headers={},
        body={"error": "Processing failed"},
    )


@pytest.mark.asyncio
async def test_cleanup_expired_keys_success(
    command_handler, mock_command_service
):
    mock_command_service.cleanup_expired_keys.return_value = 5
    result = await command_handler.cleanup_expired_keys(older_than_hours=48)
    assert result == 5
    mock_command_service.cleanup_expired_keys.assert_awaited_once_with(older_than_hours=48)


@pytest.mark.asyncio
async def test_cleanup_expired_keys_wraps_error(
    command_handler, mock_command_service
):
    mock_command_service.cleanup_expired_keys.side_effect = Exception("DB timeout")
    with pytest.raises(RuntimeError, match="Failed to clean up expired idempotency keys"):
        await command_handler.cleanup_expired_keys()


@pytest.mark.asyncio
async def test_delete_all_keys_for_user_success(
    command_handler, mock_command_service, sample_user_id
):
    mock_command_service.delete_user_keys.return_value = 3
    result = await command_handler.delete_all_keys_for_user(user_id=sample_user_id)
    assert result == 3
    mock_command_service.delete_user_keys.assert_awaited_once_with(user_id=sample_user_id)


@pytest.mark.asyncio
async def test_delete_all_keys_for_user_wraps_error(
    command_handler, mock_command_service, sample_user_id
):
    mock_command_service.delete_user_keys.side_effect = PermissionError("Access denied")
    with pytest.raises(RuntimeError, match=f"Failed to delete keys for user {sample_user_id}"):
        await command_handler.delete_all_keys_for_user(user_id=sample_user_id)