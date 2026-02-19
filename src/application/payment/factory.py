# src/application/payment/factory.py

from __future__ import annotations
from src.application.external.services.http_client import HTTPClient
from src.application.payment.handlers.payment_command_handlers import PaymentCommandHandler
from src.application.payment.handlers.payment_query_handler import PaymentQueryHandler
from src.application.payment.services.payment_command_service import PaymentCommandService
from src.application.payment.services.payment_query_service import PaymentQueryService
from src.application.idempotency.handlers.idempotency_command_handlers import IdempotencyCommandHandler
from src.application.external.services.user_api_client import UserAPIClient
from src.infrastructure.repos.event_store_repo import EventStoreRepository
from src.infrastructure.repos.outbox.orm_repository import DjangoOutBoxORMRepository

# ------------------------------------------------------------------
# Repository Factories (Infrastructure Layer)
# ------------------------------------------------------------------

def get_payment_command_repository():
    """Factory for the write-side payment repository."""
    from src.infrastructure.repos.payment.payment_command_repo import PaymentEventSourcedRepository
    outbox_repo = DjangoOutBoxORMRepository()
    event_store = EventStoreRepository(outbox_repo)
    return PaymentEventSourcedRepository(event_store= event_store)


def get_payment_query_repository():
    """Factory for the read-side payment repository."""
    from src.infrastructure.repos.payment.payment_query_repo import DjangoPaymentQueryRepository
    return DjangoPaymentQueryRepository()


# ------------------------------------------------------------------
# Service Factories
# ------------------------------------------------------------------

def get_payment_command_service() -> PaymentCommandService:
    """Constructs the command-side payment service with required repository."""
    command_repo = get_payment_command_repository()
    return PaymentCommandService(repo=command_repo)


def get_payment_query_service() -> PaymentQueryService:
    """Constructs the query-side payment service."""
    query_repo = get_payment_query_repository()
    return PaymentQueryService(query_repo=query_repo)

def get_http_client() -> HTTPClient:
    """
    Shared HTTP client (can be session-based, with retries, auth, etc.).
    """
    return HTTPClient()
# ------------------------------------------------------------------
# External Service Factories
# ------------------------------------------------------------------

def get_user_api_client() -> UserAPIClient:
    """Factory for the external user API client."""
    # Assuming UserAPIClient has a simple constructor or uses settings internally
    return UserAPIClient(http_client=get_http_client())


# ------------------------------------------------------------------
# Handler Factories
# ------------------------------------------------------------------

def get_payment_command_handler(
    idempotency_handler: IdempotencyCommandHandler | None = None
) -> PaymentCommandHandler:
    """
    Returns a fully wired command handler for payment operations.
    
    Args:
        idempotency_handler: Optional pre-configured idempotency handler.
                           If not provided, creates one using the default factory.
    """
    from src.application.idempotency.factory import get_idempotency_command_handler
    
    command_service = get_payment_command_service()
    query_service = get_payment_query_service()
    
    if idempotency_handler is None:
        idempotency_handler = get_idempotency_command_handler()
    
    return PaymentCommandHandler(
        command_service=command_service,
        query_service=query_service,
        idempotency_commands=idempotency_handler,
    )


def get_payment_query_handler() -> PaymentQueryHandler:
    """
    Returns a fully wired query handler for payment operations with owner enrichment.
    """
    query_service = get_payment_query_service()
    user_client = get_user_api_client()
    
    return PaymentQueryHandler(
        payment_queries=query_service,
        user_client=user_client,
    )