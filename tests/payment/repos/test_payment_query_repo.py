# tests/repos/test_payment_query_repo.py

import pytest
import pytest_asyncio  # <-- ADD THIS
from decimal import Decimal
from uuid import UUID, uuid4

from asgiref.sync import sync_to_async
from django.core.exceptions import ObjectDoesNotExist

from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.domain.apps.payment.models import PaymentStatus, PaymentType, PaymentMethod
from src.infrastructure.apps.payment.models import PaymentReadModel
from src.infrastructure.repos.payment.payment_query_repo import DjangoPaymentQueryRepository


@pytest.fixture
def repo():
    return DjangoPaymentQueryRepository()


# ✅ Use @pytest_asyncio.fixture for async fixtures
@pytest_asyncio.fixture
async def create_payment_read_model():
    """Async factory fixture to create PaymentReadModel instances safely."""
    @sync_to_async
    def _create(**kwargs):
        defaults = {
            'wallet_id': uuid4(),
            'user_id': uuid4(),
            'amount': Decimal('100.50'),
            'currency': 'USD',
            'payment_type': PaymentType.PAYMENT.name,
            'payment_method': PaymentMethod.CREDIT_CARD.name,
            'status': PaymentStatus.SUCCEEDED.name,
            'reference_id': None,
            'description': None,
        }
        defaults.update(kwargs)
        return PaymentReadModel.objects.create(**defaults)
    return _create


# --- All your test functions remain unchanged ---
# (they already use `await create_payment_read_model(...)` correctly)

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_id_success(repo, create_payment_read_model):
    payment = await create_payment_read_model()
    result = await repo.by_id(payment.id)
    assert result.payment_id == payment.id
    assert result.amount == str(payment.amount.normalize())
    assert result.status == payment.status


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_id_not_found(repo):
    non_existent_id = uuid4()
    with pytest.raises(PaymentNotFoundError) as exc_info:
        await repo.by_id(non_existent_id)
    assert exc_info.value.payment_id == str(non_existent_id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_wallet_id_success(repo, create_payment_read_model):
    wallet_id = uuid4()
    p1 = await create_payment_read_model(wallet_id=wallet_id, amount=Decimal('50.00'))
    p2 = await create_payment_read_model(wallet_id=wallet_id, amount=Decimal('30.00'))

    results = await repo.by_wallet_id(wallet_id)

    assert len(results) == 2
    result_ids = {r.payment_id for r in results}
    expected_ids = {p1.id, p2.id}
    assert result_ids == expected_ids


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_wallet_id_pagination(repo, create_payment_read_model):
    wallet_id = uuid4()
    payments = []
    for i in range(5):
        p = await create_payment_read_model(
            wallet_id=wallet_id,
            amount=Decimal(f'{i + 1}.00')
        )
        payments.append(p)

    page1 = await repo.by_wallet_id(wallet_id, limit=2, offset=0)
    assert len(page1) == 2

    page2 = await repo.by_wallet_id(wallet_id, limit=2, offset=2)
    assert len(page2) == 2

    all_seen = {p.payment_id for p in page1} | {p.payment_id for p in page2}
    assert len(all_seen) == 4

    empty = await repo.by_wallet_id(wallet_id, limit=2, offset=10)
    assert empty == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_wallet_id_limit_zero(repo, create_payment_read_model):
    wallet_id = uuid4()
    await create_payment_read_model(wallet_id=wallet_id)
    results = await repo.by_wallet_id(wallet_id, limit=0)
    assert results == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_wallet_id_invalid_pagination(repo):
    wallet_id = uuid4()
    with pytest.raises(ValueError, match="non-negative"):
        await repo.by_wallet_id(wallet_id, limit=-1, offset=0)

    with pytest.raises(ValueError, match="non-negative"):
        await repo.by_wallet_id(wallet_id, limit=10, offset=-5)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_user_id_success(repo, create_payment_read_model):
    user_id = uuid4()
    p1 = await create_payment_read_model(user_id=user_id)
    p2 = await create_payment_read_model(user_id=user_id)

    results = await repo.by_user_id(user_id)
    assert len(results) == 2
    result_ids = {r.payment_id for r in results}
    assert result_ids == {p1.id, p2.id}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_reference_id_success(repo, create_payment_read_model):
    ref_id = uuid4()
    p1 = await create_payment_read_model(reference_id=ref_id)
    p2 = await create_payment_read_model(reference_id=ref_id)

    results = await repo.by_reference_id(ref_id)
    assert len(results) == 2
    result_ids = {r.payment_id for r in results}
    assert result_ids == {p1.id, p2.id}


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_by_reference_id_no_results(repo):
    ref_id = uuid4()
    results = await repo.by_reference_id(ref_id)
    assert results == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_total_amount_by_wallet(repo, create_payment_read_model):
    wallet_id = uuid4()
    await create_payment_read_model(wallet_id=wallet_id, amount=Decimal('10.00'))
    await create_payment_read_model(wallet_id=wallet_id, amount=Decimal('20.50'))
    await create_payment_read_model(
        wallet_id=wallet_id,
        amount=Decimal('5.25'),
        status=PaymentStatus.FAILED.name
    )

    total = await repo.get_total_amount_by_wallet(wallet_id)
    assert total == Decimal('35.75')

    succeeded_total = await repo.get_total_amount_by_wallet(
        wallet_id, status=PaymentStatus.SUCCEEDED.name
    )
    assert succeeded_total == Decimal('30.50')


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_total_amount_by_wallet_no_payments(repo):
    wallet_id = uuid4()
    total = await repo.get_total_amount_by_wallet(wallet_id)
    assert total == Decimal('0')


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_exists_true(repo, create_payment_read_model):
    payment = await create_payment_read_model()
    exists = await repo.exists(payment.id)
    assert exists is True


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_exists_false(repo):
    exists = await repo.exists(uuid4())
    assert exists is False