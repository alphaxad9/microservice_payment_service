# tests/application/idempotency/services/test_query_service.py

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from src.domain.idempotency.models import IdempotencyKey, IdempotencyStatus, StoredResponse
from src.domain.idempotency.exceptions import IdempotencyKeyNotFoundError
from src.application.idempotency.services.idempotency_query_services import IdempotencyQueryService
from src.domain.idempotency.repository import IdempotencyKeyQueryRepository


@pytest.fixture
def mock_query_repository():
    return AsyncMock(spec=IdempotencyKeyQueryRepository)


@pytest.fixture
def query_service(mock_query_repository):
    return IdempotencyQueryService(query_repository=mock_query_repository)


@pytest.fixture
def sample_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_key() -> str:
    return "req-12345-idemp"


@pytest.fixture
def sample_fingerprint() -> str:
    return "a1b2c3d4e5f6..."  # SHA-256-like


@pytest.fixture
def expired_key(sample_key, sample_user_id, sample_fingerprint) -> IdempotencyKey:
    now = datetime.now(timezone.utc)
    return IdempotencyKey(
        key=sample_key,
        user_id=sample_user_id,
        fingerprint=sample_fingerprint,
        expires_at=now - timedelta(hours=1),
        status=IdempotencyStatus.COMPLETED,
        response=StoredResponse(status_code=201, headers={"Content-Type": "application/json"}, body={"id": "123"}),
    )


@pytest.fixture
def pending_key(sample_key, sample_user_id, sample_fingerprint) -> IdempotencyKey:
    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=24)
    return IdempotencyKey(
        key=sample_key,
        user_id=sample_user_id,
        fingerprint=sample_fingerprint,
        expires_at=future,
        status=IdempotencyStatus.PENDING,
    )


# =========================
# get_key
# =========================

@pytest.mark.asyncio
async def test_get_key_success(query_service, mock_query_repository, sample_key, sample_user_id, pending_key):
    mock_query_repository.get_by_key_and_user.return_value = pending_key

    result = await query_service.get_key(sample_key, sample_user_id)

    assert result == pending_key
    mock_query_repository.get_by_key_and_user.assert_awaited_once_with(key=sample_key, user_id=sample_user_id)


@pytest.mark.asyncio
async def test_get_key_not_found(query_service, mock_query_repository, sample_key, sample_user_id):
    mock_query_repository.get_by_key_and_user.side_effect = Exception("DB error")

    with pytest.raises(IdempotencyKeyNotFoundError) as exc_info:
        await query_service.get_key(sample_key, sample_user_id)

    assert exc_info.value.key == sample_key
    mock_query_repository.get_by_key_and_user.assert_awaited_once_with(key=sample_key, user_id=sample_user_id)


# =========================
# key_exists
# =========================

@pytest.mark.asyncio
async def test_key_exists_true(query_service, mock_query_repository, sample_key, sample_user_id):
    mock_query_repository.exists.return_value = True

    result = await query_service.key_exists(sample_key, sample_user_id)

    assert result is True
    mock_query_repository.exists.assert_awaited_once_with(key=sample_key, user_id=sample_user_id)


@pytest.mark.asyncio
async def test_key_exists_false(query_service, mock_query_repository, sample_key, sample_user_id):
    mock_query_repository.exists.return_value = False

    result = await query_service.key_exists(sample_key, sample_user_id)

    assert result is False
    mock_query_repository.exists.assert_awaited_once_with(key=sample_key, user_id=sample_user_id)


# =========================
# get_keys_by_status
# =========================

@pytest.mark.asyncio
async def test_get_keys_by_status(query_service, mock_query_repository, pending_key):
    mock_query_repository.get_by_status.return_value = [pending_key]

    result = await query_service.get_keys_by_status(IdempotencyStatus.PENDING, limit=10, offset=0)

    assert result == [pending_key]
    mock_query_repository.get_by_status.assert_awaited_once_with(
        status=IdempotencyStatus.PENDING, limit=10, offset=0
    )


# =========================
# get_expired_keys
# =========================

@pytest.mark.asyncio
async def test_get_expired_keys(query_service, mock_query_repository, expired_key):
    mock_query_repository.get_expired_keys.return_value = [expired_key]

    result = await query_service.get_expired_keys(limit=50, offset=0)

    assert result == [expired_key]
    # Ensure cutoff was passed (we can't easily assert exact time, but check call was made)
    mock_query_repository.get_expired_keys.assert_awaited()


# =========================
# get_keys_by_user
# =========================

@pytest.mark.asyncio
async def test_get_keys_by_user_success(query_service, mock_query_repository, sample_user_id, pending_key, expired_key):
    other_user_id = uuid4()
    other_key = IdempotencyKey(
        key="other-key",
        user_id=other_user_id,
        fingerprint="...",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        status=IdempotencyStatus.COMPLETED,
    )

    # Simulate repository returning mixed keys
    mock_query_repository.get_by_status.side_effect = [
        [pending_key],          # PENDING
        [expired_key, other_key],  # COMPLETED
        [],                     # FAILED
    ]

    result = await query_service.get_keys_by_user(sample_user_id, limit=10, offset=0)

    # Should only include keys belonging to sample_user_id
    assert len(result) == 2
    assert all(k.user_id == sample_user_id for k in result)
    # Sorted newest first by created_at
    assert result == sorted([pending_key, expired_key], key=lambda k: k.created_at, reverse=True)

    # Verify all three status calls were made
    assert mock_query_repository.get_by_status.call_count == 3


@pytest.mark.asyncio
async def test_get_keys_by_user_pagination(query_service, mock_query_repository, sample_user_id):
    keys = [
        IdempotencyKey(
            key=f"key-{i}",
            user_id=sample_user_id,
            fingerprint="...",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status=IdempotencyStatus.PENDING,
        )
        for i in range(5)
    ]
    # Artificially set created_at to control order
    for i, k in enumerate(keys):
        object.__setattr__(k, 'created_at', datetime.now(timezone.utc) - timedelta(seconds=i))

    mock_query_repository.get_by_status.side_effect = [
        keys,  # PENDING
        [],    # COMPLETED
        [],    # FAILED
    ]

    # Get second page (limit=2, offset=2)
    result = await query_service.get_keys_by_user(sample_user_id, limit=2, offset=2)

    assert len(result) == 2
    # Should be the 3rd and 4th newest
    expected = sorted(keys, key=lambda k: k.created_at, reverse=True)[2:4]
    assert result == expected


# =========================
# get_keys_by_fingerprint
# =========================

@pytest.mark.asyncio
async def test_get_keys_by_fingerprint(query_service, mock_query_repository, sample_fingerprint, sample_user_id, pending_key):
    mock_query_repository.get_by_fingerprint.return_value = [pending_key]

    result = await query_service.get_keys_by_fingerprint(sample_fingerprint, sample_user_id, limit=5, offset=0)

    assert result == [pending_key]
    mock_query_repository.get_by_fingerprint.assert_awaited_once_with(
        fingerprint=sample_fingerprint, user_id=sample_user_id, limit=5, offset=0
    )


# =========================
# count_keys_by_user
# =========================

@pytest.mark.asyncio
async def test_count_keys_by_user(query_service, mock_query_repository, sample_user_id):
    mock_query_repository.count_by_user.return_value = 42

    result = await query_service.count_keys_by_user(sample_user_id)

    assert result == 42
    mock_query_repository.count_by_user.assert_awaited_once_with(user_id=sample_user_id)


# =========================
# get_key_metrics
# =========================

@pytest.mark.asyncio
async def test_get_key_metrics(query_service, mock_query_repository, pending_key, expired_key):
    completed_key = IdempotencyKey(
        key="comp",
        user_id=uuid4(),
        fingerprint="...",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        status=IdempotencyStatus.COMPLETED,
        response=StoredResponse(200, {}, {}),
    )

    mock_query_repository.get_by_status.side_effect = [
        [pending_key],      # PENDING
        [completed_key],    # COMPLETED
        [expired_key],      # FAILED
    ]

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, tzinfo=timezone.utc)

    result = await query_service.get_key_metrics(start, end)

    assert result["total_keys"] == 3
    assert result["by_status"]["pending"] == 1
    assert result["by_status"]["completed"] == 1
    assert result["by_status"]["failed"] == 1
    assert result["replay_rate"] == 2 / 3
    assert result["time_range"]["start"] == start.isoformat()
    assert result["time_range"]["end"] == end.isoformat()

    # Called once per status
    assert mock_query_repository.get_by_status.call_count == 3