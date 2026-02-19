# tests/domain/idempotency/services/test_idempotency_command_service.py

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.application.idempotency.services.idempotency_command_service import IdempotencyCommandService
from src.domain.idempotency.models import (
    IdempotencyKey,
    IdempotencyStatus,
    StoredResponse,
    compute_fingerprint,
)
from src.domain.idempotency.exceptions import (
    InvalidIdempotencyKeyFormatError,
    IdempotencyKeyTooLongError,
    IdempotencyKeyExpiredError,
    IdempotencyKeyAlreadyUsedError,
    IdempotencyKeyInProgressError,
    IdempotencyKeyReuseWithDifferentPayloadError,
    IdempotencyKeyExpirationInPastError,
)
from src.domain.idempotency.repository import (
    IdempotencyReplayResult,
    IdempotencyAcquiredResult,
    IdempotencyConflictResult,
)


@pytest.fixture
def user_id() -> uuid4:
    return uuid4()


@pytest.fixture
def mock_command_repo():
    return AsyncMock()


@pytest.fixture
def mock_query_repo():
    repo = AsyncMock()
    repo.get_replay_response.return_value = None
    return repo


@pytest.fixture
def service(mock_command_repo, mock_query_repo):
    return IdempotencyCommandService(
        command_repo=mock_command_repo,
        query_repo=mock_query_repo,
    )


@pytest.fixture
def valid_payload():
    return {"amount": 1000, "currency": "USD"}


@pytest.fixture
def valid_key() -> str:
    return "idempotency-test-key-123"


@pytest.mark.asyncio
async def test_create_key_success(service, user_id, valid_key, valid_payload, mock_command_repo):
    # Arrange
    created_key = None
    fingerprint = compute_fingerprint(valid_payload)

    async def capture_created(key_obj):
        nonlocal created_key
        created_key = key_obj
        return key_obj

    mock_command_repo.create.side_effect = capture_created

    # Act
    result = await service.create_key(
        key=valid_key,
        user_id=user_id,
        fingerprint=fingerprint,
    )

    # Assert
    assert result is created_key
    assert result.key == valid_key
    assert result.user_id == user_id
    assert result.fingerprint == fingerprint
    assert result.status == IdempotencyStatus.PENDING
    assert not result.is_expired()
    assert result.expires_at > datetime.now(timezone.utc)

    mock_command_repo.create.assert_called_once()
    passed_key: IdempotencyKey = mock_command_repo.create.call_args[0][0]
    assert passed_key.key == valid_key
    assert passed_key.user_id == user_id
    assert passed_key.fingerprint == fingerprint
    assert passed_key.status == IdempotencyStatus.PENDING


@pytest.mark.asyncio
async def test_create_key_race_condition_same_payload(service, user_id, valid_key, valid_payload, mock_command_repo, mock_query_repo):
    fingerprint = compute_fingerprint(valid_payload)
    existing_key = IdempotencyKey.create_new(
        key=valid_key,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )

    mock_command_repo.create.side_effect = Exception("Unique violation")
    mock_query_repo.get_by_key_and_user.return_value = existing_key

    result = await service.create_key(
        key=valid_key,
        user_id=user_id,
        fingerprint=fingerprint,
    )

    assert result == existing_key
    mock_query_repo.get_by_key_and_user.assert_called_once_with(key=valid_key, user_id=user_id)


@pytest.mark.asyncio
async def test_create_key_race_condition_different_payload_raises(service, user_id, valid_key, valid_payload, mock_command_repo, mock_query_repo):
    different_payload = {"amount": 999}
    existing_fingerprint = compute_fingerprint(different_payload)
    call_fingerprint = compute_fingerprint(valid_payload)

    existing_key = IdempotencyKey.create_new(
        key=valid_key,
        user_id=user_id,
        fingerprint=existing_fingerprint,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )

    mock_command_repo.create.side_effect = Exception("Unique violation")
    mock_query_repo.get_by_key_and_user.return_value = existing_key

    with pytest.raises(IdempotencyKeyReuseWithDifferentPayloadError):
        await service.create_key(
            key=valid_key,
            user_id=user_id,
            fingerprint=call_fingerprint,
        )

    mock_query_repo.get_by_key_and_user.assert_called_once()


@pytest.mark.asyncio
async def test_create_key_invalid_format(service, user_id, valid_payload):
    fingerprint = compute_fingerprint(valid_payload)
    with pytest.raises(InvalidIdempotencyKeyFormatError):
        await service.create_key(key="", user_id=user_id, fingerprint=fingerprint)

    with pytest.raises(InvalidIdempotencyKeyFormatError):
        await service.create_key(key="   ", user_id=user_id, fingerprint=fingerprint)


@pytest.mark.asyncio
async def test_create_key_too_long(service, user_id, valid_payload):
    long_key = "a" * 256
    fingerprint = compute_fingerprint(valid_payload)
    with pytest.raises(IdempotencyKeyTooLongError):
        await service.create_key(key=long_key, user_id=user_id, fingerprint=fingerprint)


@pytest.mark.asyncio
async def test_process_request_replay_fast_path(service, user_id, valid_key, mock_query_repo):
    stored_response = StoredResponse(
        status_code=201,
        headers={"Location": "/payments/123"},
        body={"id": "pay_123"},
    )
    mock_query_repo.get_replay_response.return_value = stored_response

    result = await service.process_request(
        key=valid_key,
        user_id=user_id,
        locker_id="worker-1",
        fingerprint="",  # optional during transition; can be empty
    )

    assert result == {
        "status_code": 201,
        "headers": {"Location": "/payments/123"},
        "body": {"id": "pay_123"},
    }
    mock_query_repo.get_replay_response.assert_called_once_with(key=valid_key, user_id=user_id)


@pytest.mark.asyncio
async def test_process_request_acquired(service, user_id, valid_key, mock_command_repo):
    mock_command_repo.claim_or_replay.return_value = IdempotencyAcquiredResult(key=MagicMock())

    result = await service.process_request(
        key=valid_key,
        user_id=user_id,
        locker_id="worker-1",
        fingerprint=compute_fingerprint({"test": "data"}),
    )

    assert result is None
    mock_command_repo.claim_or_replay.assert_called_once()


@pytest.mark.asyncio
async def test_process_request_in_progress_raises(service, user_id, valid_key, mock_command_repo):
    mock_command_repo.claim_or_replay.return_value = IdempotencyConflictResult(reason="already_locked")

    with pytest.raises(IdempotencyKeyInProgressError):
        await service.process_request(
            key=valid_key,
            user_id=user_id,
            locker_id="worker-1",
            fingerprint=compute_fingerprint({"x": 1}),
        )


@pytest.mark.asyncio
async def test_process_request_replay_from_claim_race(service, user_id, valid_key, mock_command_repo):
    stored_response = StoredResponse(status_code=200, headers={}, body={"success": True})
    mock_command_repo.claim_or_replay.return_value = IdempotencyReplayResult(response=stored_response)

    result = await service.process_request(
        key=valid_key,
        user_id=user_id,
        locker_id="worker-1",
        fingerprint=compute_fingerprint({"y": 2}),
    )

    assert result == {
        "status_code": 200,
        "headers": {},
        "body": {"success": True},
    }


@pytest.mark.asyncio
async def test_record_success(service, user_id, valid_key, mock_query_repo, mock_command_repo):
    pending_key = MagicMock()
    pending_key.is_expired.return_value = False
    pending_key.is_pending.return_value = True
    pending_key.record_success = MagicMock()
    mock_query_repo.get_by_key_and_user.return_value = pending_key

    await service.record_success(
        key=valid_key,
        user_id=user_id,
        status_code=201,
        headers={"Location": "/x"},
        body={"id": "123"},
    )

    pending_key.record_success.assert_called_once_with(
        status_code=201, headers={"Location": "/x"}, body={"id": "123"}
    )
    mock_command_repo.update.assert_called_once_with(pending_key)


@pytest.mark.asyncio
async def test_record_success_expired_raises(service, user_id, valid_key, mock_query_repo):
    expired_key = MagicMock()
    expired_key.is_expired.return_value = True
    mock_query_repo.get_by_key_and_user.return_value = expired_key

    with pytest.raises(IdempotencyKeyExpiredError):
        await service.record_success(key=valid_key, user_id=user_id, status_code=200, headers={}, body={})


@pytest.mark.asyncio
async def test_record_success_already_used_raises(service, user_id, valid_key, mock_query_repo):
    completed_key = MagicMock()
    completed_key.is_expired.return_value = False
    completed_key.is_pending.return_value = False
    mock_query_repo.get_by_key_and_user.return_value = completed_key

    with pytest.raises(IdempotencyKeyAlreadyUsedError):
        await service.record_success(key=valid_key, user_id=user_id, status_code=200, headers={}, body={})


@pytest.mark.asyncio
async def test_record_failure_similar_to_success(service, user_id, valid_key, mock_query_repo, mock_command_repo):
    pending_key = MagicMock()
    pending_key.is_expired.return_value = False
    pending_key.is_pending.return_value = True
    pending_key.record_failure = MagicMock()
    mock_query_repo.get_by_key_and_user.return_value = pending_key

    await service.record_failure(
        key=valid_key,
        user_id=user_id,
        status_code=400,
        headers={},
        body={"error": "invalid"},
    )

    pending_key.record_failure.assert_called_once()
    mock_command_repo.update.assert_called_once_with(pending_key)


@pytest.mark.asyncio
async def test_cleanup_expired_keys(service, mock_command_repo):
    mock_command_repo.delete_expired_before.return_value = 42

    deleted = await service.cleanup_expired_keys(older_than_hours=48)

    assert deleted == 42
    mock_command_repo.delete_expired_before.assert_called_once()
    cutoff = mock_command_repo.delete_expired_before.call_args[1]["cutoff"]
    assert isinstance(cutoff, datetime)


@pytest.mark.asyncio
async def test_delete_user_keys(service, user_id, mock_command_repo):
    mock_command_repo.delete_by_user.return_value = 15

    deleted = await service.delete_user_keys(user_id=user_id)

    assert deleted == 15
    mock_command_repo.delete_by_user.assert_called_once_with(user_id=user_id)