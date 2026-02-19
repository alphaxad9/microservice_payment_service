# tests/idempotency/repos/test_idempotency_command_repo.py

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from asgiref.sync import sync_to_async

from django.utils import timezone as django_timezone

from src.domain.idempotency.models import (
    IdempotencyKey,
    IdempotencyStatus,
    StoredResponse,
)
from src.domain.idempotency.repository import (
    IdempotencyAcquiredResult,
    IdempotencyReplayResult,
    IdempotencyConflictResult,
)
from src.domain.idempotency.exceptions import (
    IdempotencyKeyAlreadyExistsError,
    IdempotencyKeyNotFoundError,
    IdempotencyKeyExpiredError,
    IdempotencyKeyAlreadyUsedError,
    IdempotencyKeyAlreadyLockedError,
    IdempotencyResponseMissingError,
)
from src.infrastructure.repos.idempontency.idempotence_command_repo import DjangoIdempotencyKeyCommandRepository
from src.infrastructure.apps.idempontence.models import IdempotencyKey as ORMModel  # Fixed typo


@pytest.fixture
def repo():
    return DjangoIdempotencyKeyCommandRepository()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def idempotency_key_str():
    return "req_abc123"


@pytest.fixture
def fingerprint():
    return "a1b2c3d4e5f6..."  # SHA-256-like


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_success(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey.create_new(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
    )

    result = await repo.create(domain_key)

    assert result.key == idempotency_key_str
    assert result.user_id == user_id
    assert result.fingerprint == fingerprint
    assert result.status == IdempotencyStatus.PENDING

    orm_obj = await ORMModel.objects.aget(key=idempotency_key_str, user_id=user_id)
    assert orm_obj is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_create_duplicate_raises_error(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    key1 = IdempotencyKey.create_new(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
    )
    await repo.create(key1)

    key2 = IdempotencyKey.create_new(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
    )

    with pytest.raises(IdempotencyKeyAlreadyExistsError):
        await repo.create(key2)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_lock_success(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey.create_new(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
    )
    await repo.create(domain_key)

    locker_id = "worker-789"
    result = await repo.lock(idempotency_key_str, user_id, locker_id, lock_duration_seconds=30)

    assert result.locked_by == locker_id
    assert result.locked_until > now


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_lock_nonexistent_key_raises(repo, user_id, idempotency_key_str):
    with pytest.raises(IdempotencyKeyNotFoundError):
        await repo.lock(idempotency_key_str, user_id, "locker", 30)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_lock_expired_key_raises(repo, user_id, idempotency_key_str, fingerprint):
    past = django_timezone.now() - timedelta(hours=1)
    domain_key = IdempotencyKey(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=past,
        status=IdempotencyStatus.PENDING,
    )
    await repo.create(domain_key)

    with pytest.raises(IdempotencyKeyExpiredError):
        await repo.lock(idempotency_key_str, user_id, "locker", 30)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_lock_completed_key_raises(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
        status=IdempotencyStatus.COMPLETED,
        response=StoredResponse(status_code=201, headers={}, body={"id": "123"}),
    )
    await repo.create(domain_key)

    with pytest.raises(IdempotencyKeyAlreadyUsedError):
        await repo.lock(idempotency_key_str, user_id, "locker", 30)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_claim_or_replay_first_use(repo, user_id, idempotency_key_str, fingerprint):
    locker_id = "worker-1"
    result = await repo.claim_or_replay(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        locker_id=locker_id,
        lease_duration_seconds=30,
    )

    assert isinstance(result, IdempotencyAcquiredResult)
    assert result.key.key == idempotency_key_str
    assert result.key.locked_by == locker_id
    assert result.key.status == IdempotencyStatus.PENDING


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_claim_or_replay_replay_success(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    response = StoredResponse(status_code=200, headers={"X-Custom": "yes"}, body={"msg": "ok"})
    domain_key = IdempotencyKey(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
        status=IdempotencyStatus.COMPLETED,
        response=response,
    )
    await repo.create(domain_key)

    result = await repo.claim_or_replay(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        locker_id="any",
    )

    assert isinstance(result, IdempotencyReplayResult)
    assert result.response.status_code == 200
    assert result.response.body == {"msg": "ok"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_claim_or_replay_fingerprint_mismatch_on_completed_key(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
        status=IdempotencyStatus.COMPLETED,
        response=StoredResponse(status_code=200, headers={}, body={}),
    )
    await repo.create(domain_key)

    result = await repo.claim_or_replay(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint="different_fingerprint",
        locker_id="any",
    )

    assert isinstance(result, IdempotencyConflictResult)
    assert result.reason == "fingerprint_mismatch"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_claim_or_replay_missing_response_raises(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
        status=IdempotencyStatus.COMPLETED,
        response=None,
    )
    await repo.create(domain_key)

    with pytest.raises(IdempotencyResponseMissingError):
        await repo.claim_or_replay(
            key=idempotency_key_str,
            user_id=user_id,
            fingerprint=fingerprint,
            locker_id="any",
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_unlock_success(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey.create_new(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
    )
    domain_key.mark_in_progress("worker-1", 60)
    await repo.create(domain_key)

    await repo.unlock(idempotency_key_str, user_id)

    # Fetch fresh ORM object — do NOT use stale domain_key or call update()
    orm_obj = await ORMModel.objects.aget(key=idempotency_key_str, user_id=user_id)
    assert orm_obj.locked_until is None
    assert orm_obj.locked_by is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_success(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey.create_new(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
    )
    await repo.create(domain_key)

    await repo.delete(idempotency_key_str, user_id)

    with pytest.raises(ORMModel.DoesNotExist):
        await ORMModel.objects.aget(key=idempotency_key_str, user_id=user_id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_delete_expired_before(repo, user_id):
    cutoff = django_timezone.now()
    # Create expired key directly (bypass create_new validation)
    old_key = IdempotencyKey(
        key="old_key",
        user_id=user_id,
        fingerprint="fp1",
        expires_at=cutoff - timedelta(minutes=1),
        status=IdempotencyStatus.PENDING,
    )
    new_key = IdempotencyKey.create_new(
        key="new_key",
        user_id=user_id,
        fingerprint="fp2",
        expires_at=cutoff + timedelta(minutes=1),
    )
    await repo.create(old_key)
    await repo.create(new_key)

    deleted = await repo.delete_expired_before(cutoff)

    assert deleted == 1
    with pytest.raises(ORMModel.DoesNotExist):
        await ORMModel.objects.aget(key="old_key", user_id=user_id)
    # new_key should still exist
    await ORMModel.objects.aget(key="new_key", user_id=user_id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_force_unlock_expired_lock(repo, user_id, idempotency_key_str, fingerprint):
    now = django_timezone.now()
    domain_key = IdempotencyKey.create_new(
        key=idempotency_key_str,
        user_id=user_id,
        fingerprint=fingerprint,
        expires_at=now + timedelta(hours=1),
    )
    domain_key.mark_in_progress("worker-1", 1)  # 1-second lock
    await repo.create(domain_key)

    # Manually expire the lock
    orm = await ORMModel.objects.aget(key=idempotency_key_str, user_id=user_id)
    orm.locked_until = now - timedelta(seconds=1)
    await sync_to_async(orm.save)()

    await repo.force_unlock(idempotency_key_str, user_id)

    updated = await ORMModel.objects.aget(key=idempotency_key_str, user_id=user_id)
    assert updated.locked_until is None
    assert updated.locked_by is None