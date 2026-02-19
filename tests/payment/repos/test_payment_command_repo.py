import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4
from decimal import Decimal

from src.domain.apps.payment.models import PaymentType, PaymentMethod
from src.domain.apps.payment.aggregate import PaymentAggregate
from src.domain.apps.payment.events import PaymentCreatedEvent, PaymentSucceededEvent
from src.domain.apps.payment.exceptions import PaymentNotFoundError
from src.infrastructure.repos.payment.payment_command_repo import PaymentEventSourcedRepository
from src.infrastructure.repos.event_store_repo import EventStoreRepository


@pytest.fixture
def event_store_repo():
    return Mock(spec=EventStoreRepository)


@pytest.fixture
def payment_repo(event_store_repo):
    return PaymentEventSourcedRepository(event_store=event_store_repo)


@pytest.fixture
def sample_payment_id():
    return uuid4()


@pytest.fixture
def sample_aggregate(sample_payment_id):
    return PaymentAggregate.create_deposit(
        wallet_id=uuid4(),
        user_id=uuid4(),
        amount=Decimal("100.00"),
        currency="USD",
        payment_method=PaymentMethod.CREDIT_CARD,
        payment_id=sample_payment_id,
        description="Test deposit",
    )


@pytest.mark.asyncio
async def test_load_payment_not_found(payment_repo, sample_payment_id):
    # Arrange
    with patch("src.infrastructure.repos.payment.payment_command_repo.EventStore") as MockEventStore:
        MockEventStore.objects.filter.return_value.order_by.return_value.only.return_value = []

        # Act & Assert
        with pytest.raises(PaymentNotFoundError) as exc_info:
            await payment_repo.load(sample_payment_id)

        assert str(sample_payment_id) in str(exc_info.value)


@pytest.mark.asyncio
async def test_load_invalid_first_event_type(payment_repo, sample_payment_id):
    # Arrange
    mock_event = Mock()
    mock_event.event_type = "payment.succeeded"
    mock_event.event_payload = {
        "event_id": str(uuid4()),
        "occurred_at": "2025-01-01T00:00:00+00:00",
        "schema_version": 1,
        "payment_id": str(sample_payment_id),
        "wallet_id": str(uuid4()),
        "user_id": str(uuid4()),
        "payload": {},
    }

    with patch("src.infrastructure.repos.payment.payment_command_repo.EventStore") as MockEventStore:
        MockEventStore.objects.filter.return_value.order_by.return_value.only.return_value = [mock_event]

        # Act & Assert
        with pytest.raises(ValueError, match="Expected PaymentCreatedEvent"):
            await payment_repo.load(sample_payment_id)


@pytest.mark.asyncio
async def test_load_success(payment_repo, sample_payment_id):
    # Arrange
    wallet_id = uuid4()
    user_id = uuid4()

    created_event = PaymentCreatedEvent(
        payment_id=sample_payment_id,
        wallet_id=wallet_id,
        user_id=user_id,
        amount=Decimal("50.00"),
        currency="EUR",
        payment_type=PaymentType.WITHDRAWAL.value,
        payment_method=PaymentMethod.BANK_TRANSFER.value,
        description="Test withdrawal",
    )

    succeeded_event = PaymentSucceededEvent(
        payment_id=sample_payment_id,
        wallet_id=wallet_id,
        user_id=user_id,
    )

    # Simulate stored events in DB
    mock_events = [
        Mock(
            aggregate_version=1,
            event_type=created_event.event_type,
            event_payload=created_event.to_dict(),
        ),
        Mock(
            aggregate_version=2,
            event_type=succeeded_event.event_type,
            event_payload=succeeded_event.to_dict(),
        ),
    ]

    with patch("src.infrastructure.repos.payment.payment_command_repo.EventStore") as MockEventStore:
        MockEventStore.objects.filter.return_value.order_by.return_value.only.return_value = mock_events

        # Act
        aggregate = await payment_repo.load(sample_payment_id)

        # Assert
        assert aggregate.payment_id == sample_payment_id
        assert aggregate.wallet_id == wallet_id
        assert aggregate.user_id == user_id
        assert aggregate.amount == Decimal("50.00")
        assert aggregate.currency == "EUR"
        assert aggregate.payment_type == PaymentType.WITHDRAWAL
        assert aggregate.payment_method == PaymentMethod.BANK_TRANSFER
        assert aggregate.description == "Test withdrawal"
        assert aggregate.status.name == "SUCCEEDED"
        assert aggregate.version == 2


@pytest.mark.asyncio
async def test_save_no_events(payment_repo, sample_aggregate):
    # Arrange
    sample_aggregate.pop_events()  # clear uncommitted events

    # Act
    await payment_repo.save(sample_aggregate)

    # Assert
    payment_repo._event_store.append.assert_not_called()


@pytest.mark.asyncio
async def test_save_with_events(payment_repo):
    # Arrange: create a brand-new payment (only Created event applied)
    payment_id = uuid4()
    wallet_id = uuid4()
    user_id = uuid4()

    aggregate = PaymentAggregate.create_deposit(
        wallet_id=wallet_id,
        user_id=user_id,
        amount=Decimal("100.00"),
        currency="USD",
        payment_method=PaymentMethod.CREDIT_CARD,
        payment_id=payment_id,
    )
    # At this point: version = 1, and 1 uncommitted event (Created)

    # But typically, you'd save it first via create()
    # Then later, load it, apply a command, and save again

    # For this test, simulate a post-creation update:
    # First, assume it was already saved (so version = 1, no uncommitted events)
    aggregate.pop_events()  # clear the initial Created event (simulate it was already persisted)
    aggregate.version = 1   # now it's "clean" at version 1

    # Now apply a new command
    aggregate.succeed()  # adds Succeeded event, version becomes 2

    # Act
    await payment_repo.save(aggregate)

    # Assert
    payment_repo._event_store.append.assert_called_once()
    call_args = payment_repo._event_store.append.call_args[1]
    assert call_args["expected_version"] == 1  # last persisted version
    assert len(call_args["events"]) == 1
    assert aggregate.version == 2

@pytest.mark.asyncio
async def test_create_delegates_to_save(payment_repo, sample_aggregate):
    # Arrange
    with patch.object(payment_repo, 'save', new_callable=AsyncMock) as mock_save:
        # Act
        await payment_repo.create(sample_aggregate)

        # Assert
        mock_save.assert_awaited_once_with(sample_aggregate)