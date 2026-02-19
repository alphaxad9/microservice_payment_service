# tests/infrastructure/idempotency/test_async_repository.py

import pytest
from datetime import timedelta
from uuid import UUID, uuid4

from django.utils import timezone as django_timezone

from src.domain.idempotency.models import IdempotencyStatus
from src.domain.idempotency.exceptions import IdempotencyKeyNotFoundError
from src.infrastructure.repos.idempontency.idempotence_query_repo import DjangoIdempotencyKeyQueryRepository
from src.infrastructure.apps.idempontence.models import IdempotencyKey as IdempotencyKeyModel


@pytest.fixture
def user_id() -> UUID:
    return uuid4()


@pytest.fixture
def idempotency_key_str() -> str:
    return "req-12345"


@pytest.fixture
def fingerprint() -> str:
    return "a" * 64  # valid SHA-256 hex digest


@pytest.fixture
def future_expires_at():
    return django_timezone.now() + timedelta(hours=1)


@pytest.fixture
def past_expires_at():
    return django_timezone.now() - timedelta(hours=1)


@pytest.fixture
def repo():
    return DjangoIdempotencyKeyQueryRepository()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestDjangoIdempotencyKeyQueryRepository:

    async def test_get_by_key_and_user_success(
        self, repo, user_id, idempotency_key_str, fingerprint, future_expires_at
    ):
        # Arrange
        await IdempotencyKeyModel.objects.acreate(
            key=idempotency_key_str,
            user_id=user_id,
            fingerprint=fingerprint,
            expires_at=future_expires_at,
            status=IdempotencyStatus.PENDING.name,
        )

        # Act
        domain_key = await repo.get_by_key_and_user(idempotency_key_str, user_id)

        # Assert
        assert domain_key.key == idempotency_key_str
        assert domain_key.user_id == user_id
        assert domain_key.fingerprint == fingerprint
        assert domain_key.status == IdempotencyStatus.PENDING

    async def test_get_by_key_and_user_not_found_raises(
        self, repo, user_id, idempotency_key_str
    ):
        # Act & Assert
        with pytest.raises(IdempotencyKeyNotFoundError) as exc_info:
            await repo.get_by_key_and_user(idempotency_key_str, user_id)
        assert exc_info.value.key == idempotency_key_str

    async def test_get_used_key_response_returns_none_when_no_match(
        self, repo, user_id, idempotency_key_str
    ):
        result = await repo.get_used_key_response(idempotency_key_str, user_id)
        assert result is None

    async def test_get_used_key_response_returns_data_for_completed_key(
        self, repo, user_id, idempotency_key_str, fingerprint, future_expires_at
    ):
        response_data = {
            "status_code": 201,
            "headers": {"Content-Type": "application/json"},
            "body": {"id": "123", "message": "Created"},
        }
        await IdempotencyKeyModel.objects.acreate(
            key=idempotency_key_str,
            user_id=user_id,
            fingerprint=fingerprint,
            expires_at=future_expires_at,
            status=IdempotencyStatus.COMPLETED.name,
            response_data=response_data,
        )

        result = await repo.get_used_key_response(idempotency_key_str, user_id)

        # ✅ Include 'headers' in expected result
        assert result == {
            "status_code": 201,
            "headers": {"Content-Type": "application/json"},
            "body": {"id": "123", "message": "Created"},
        }

    async def test_get_used_key_response_ignores_pending_keys(
        self, repo, user_id, idempotency_key_str, fingerprint, future_expires_at
    ):
        response_data = {"status_code": 201, "body": {}}
        await IdempotencyKeyModel.objects.acreate(
            key=idempotency_key_str,
            user_id=user_id,
            fingerprint=fingerprint,
            expires_at=future_expires_at,
            status=IdempotencyStatus.PENDING.name,
            response_data=response_data,
        )

        result = await repo.get_used_key_response(idempotency_key_str, user_id)
        assert result is None

    async def test_exists_true_when_key_exists(
        self, repo, user_id, idempotency_key_str, fingerprint, future_expires_at
    ):
        await IdempotencyKeyModel.objects.acreate(
            key=idempotency_key_str,
            user_id=user_id,
            fingerprint=fingerprint,
            expires_at=future_expires_at,
        )
        exists = await repo.exists(idempotency_key_str, user_id)
        assert exists is True

    async def test_exists_false_when_key_missing(
        self, repo, user_id, idempotency_key_str
    ):
        exists = await repo.exists(idempotency_key_str, user_id)
        assert exists is False

    async def test_get_by_status_pagination(
        self, repo, user_id, fingerprint, future_expires_at
    ):
        # Create 5 keys
        for i in range(5):
            await IdempotencyKeyModel.objects.acreate(
                key=f"key-{i}",
                user_id=user_id,
                fingerprint=fingerprint,
                expires_at=future_expires_at,
                status=IdempotencyStatus.COMPLETED.name,
            )

        results = await repo.get_by_status(IdempotencyStatus.COMPLETED, limit=2, offset=1)

        assert len(results) == 2
        # Ordered by created_at DESC → most recent first
        assert results[0].key == "key-3"
        assert results[1].key == "key-2"

    async def test_get_expired_keys(
        self, repo, user_id, fingerprint, past_expires_at
    ):
        await IdempotencyKeyModel.objects.acreate(
            key="expired-key",
            user_id=user_id,
            fingerprint=fingerprint,
            expires_at=past_expires_at,
            status=IdempotencyStatus.PENDING.name,
        )
        cutoff = django_timezone.now()

        results = await repo.get_expired_keys(cutoff, limit=10)

        assert len(results) == 1
        assert results[0].key == "expired-key"

    async def test_get_by_fingerprint(
        self, repo, user_id, idempotency_key_str, fingerprint, future_expires_at
    ):
        await IdempotencyKeyModel.objects.acreate(
            key=idempotency_key_str,
            user_id=user_id,
            fingerprint=fingerprint,
            expires_at=future_expires_at,
        )

        results = await repo.get_by_fingerprint(fingerprint, user_id, limit=10)

        assert len(results) == 1
        assert results[0].fingerprint == fingerprint

    async def test_count_by_user(
        self, repo, user_id, fingerprint, future_expires_at
    ):
        for i in range(3):
            await IdempotencyKeyModel.objects.acreate(
                key=f"count-key-{i}",
                user_id=user_id,
                fingerprint=fingerprint,
                expires_at=future_expires_at,
            )
        other_user = uuid4()
        await IdempotencyKeyModel.objects.acreate(
            key="other",
            user_id=other_user,
            fingerprint=fingerprint,
            expires_at=future_expires_at,
        )

        count = await repo.count_by_user(user_id)
        assert count == 3